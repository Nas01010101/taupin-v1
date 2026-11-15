"""Fine-tune a timm backbone on the train split; select the checkpoint by validation macro-F1.

Test and OOD rows are never read here.

    python train.py --data-root ~/scratch/taupin/data --attr attribution.csv --out runs/v1
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import timm
from timm.optim import create_optimizer_v2
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision.transforms import v2 as T

from classes import CLASS_IDS
from data import ImageRows, labels, read_rows
from evalutil import MEAN, STD, macro_f1


def train_tf(size):
    return T.Compose([
        T.RandomResizedCrop(size, scale=(0.3, 1.0), ratio=(0.75, 1.33), antialias=True),
        T.RandomHorizontalFlip(), T.RandomVerticalFlip(),
        T.RandomApply([T.RandomRotation(30)], p=0.3),
        T.ColorJitter(0.35, 0.35, 0.3, 0.04), T.RandomGrayscale(0.05),
        T.RandomApply([T.GaussianBlur(5, (0.1, 2.0))], p=0.2),
        T.ToImage(), T.ToDtype(torch.float32, scale=True), T.Normalize(MEAN, STD),
    ])


@torch.no_grad()
def predict(model, loader, dev):
    model.eval()
    out = []
    for x, _ in loader:
        with torch.autocast("cuda", dtype=torch.float16):
            out.append(model(x.to(dev, non_blocking=True)).float().cpu())
    return torch.cat(out).numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--attr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arch", default="efficientnet_b0.ra_in1k")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--wd", type=float, default=0.05)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--freeze", action="store_true", help="linear probe: train only the head")
    ap.add_argument("--layer-decay", type=float, default=1.0, help="<1 uses timm layer-wise lr decay")
    a = ap.parse_args()
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = "cuda"
    tr = read_rows(a.attr, {"train"}, CLASS_IDS)
    va = read_rows(a.attr, {"val"}, CLASS_IDS)
    ytr, yva = labels(tr, CLASS_IDS), labels(va, CLASS_IDS)
    n = len(CLASS_IDS)
    freq = np.maximum(np.bincount(ytr, minlength=n), 1)
    w = torch.tensor((freq.max() / freq) ** 0.5, dtype=torch.float32, device=dev)
    dl_tr = DataLoader(ImageRows(tr, a.data_root, CLASS_IDS, train_tf(a.size)), batch_size=a.bs,
                       shuffle=True, num_workers=8, pin_memory=True, drop_last=True, persistent_workers=True)
    dl_va = DataLoader(ImageRows(va, a.data_root, CLASS_IDS, size=a.size), batch_size=128,
                       num_workers=8, pin_memory=True)
    kw = {"img_size": a.size, "drop_path_rate": 0.1} if "vit" in a.arch else {}
    model = timm.create_model(a.arch, pretrained=True, num_classes=n, **kw).to(dev)
    head = model.get_classifier()
    head_ids = {id(p) for p in head.parameters()}
    body = [p for p in model.parameters() if id(p) not in head_ids]
    if a.freeze:
        for p in body:
            p.requires_grad = False
        opt = torch.optim.AdamW([{"params": head.parameters(), "lr": a.lr}], weight_decay=a.wd)
    elif a.layer_decay < 1:
        opt = create_optimizer_v2(model, "adamw", lr=a.lr, weight_decay=a.wd, layer_decay=a.layer_decay)
    else:
        opt = torch.optim.AdamW([{"params": body, "lr": a.lr * 0.3}, {"params": head.parameters(), "lr": a.lr}],
                                weight_decay=a.wd)
    groups = opt.param_groups
    for g in groups:  # OneCycle needs each group's own peak lr
        g["lr"] = g["lr"] * g.get("lr_scale", 1.0)
    steps = a.epochs * len(dl_tr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[g["lr"] for g in groups], total_steps=steps,
                                                pct_start=0.1)
    scaler = torch.amp.GradScaler()
    loss_fn = nn.CrossEntropyLoss(weight=w, label_smoothing=0.1)
    best, hist = -1, []
    for ep in range(a.epochs):
        model.train()
        t0, tot = time.time(), 0.0
        for x, y in dl_tr:
            x, y = x.to(dev, non_blocking=True), y.to(dev, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_fn(model(x), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item()
        lv = predict(model, dl_va, dev)
        f1 = macro_f1(yva, lv.argmax(1), n)
        acc = float((lv.argmax(1) == yva).mean())
        hist.append({"epoch": ep, "loss": tot / len(dl_tr), "val_macro_f1": f1, "val_acc": acc,
                     "sec": time.time() - t0})
        print(json.dumps(hist[-1]), flush=True)
        if f1 > best:
            best = f1
            torch.save({"arch": a.arch, "kw": {"img_size": a.size} if "vit" in a.arch else {}, "classes": CLASS_IDS, "state": model.state_dict(), "size": a.size,
                        "epoch": ep, "val_macro_f1": f1, "args": vars(a)}, out / "best.pt")
            np.save(out / "val_logits.npy", lv)
    json.dump({"history": hist, "best_val_macro_f1": best, "n_train": len(tr), "n_val": len(va),
               "args": vars(a)}, open(out / "train_log.json", "w"), indent=1)


if __name__ == "__main__":
    main()
