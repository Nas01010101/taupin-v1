"""Zero-shot open_clip baseline on val, test and OOD (same rows as the fine-tuned model).

Logits are the model's scaled cosine similarities against prompt-ensembled class embeddings.
Reading test is logged through the seal like any other evaluation.

    python clip_baseline.py --data-root D --attr attribution.csv --out runs/clip_b32 \
        --model ViT-B-32 --pretrained laion2b_s34b_b79k
"""
import argparse
import json
from pathlib import Path

import numpy as np
import open_clip
import torch

from classes import CLASS_IDS
from data import labels, read_rows
from evalutil import load_rgb

PROMPTS = {
    "wireworm": ["a wireworm", "a click beetle larva", "a thin shiny yellow-brown wireworm larva in soil"],
    "click_beetle": ["a click beetle", "an adult click beetle (Elateridae)", "an elongated brown click beetle"],
    "corn_rootworm": ["a corn rootworm beetle", "a western corn rootworm beetle (Diabrotica virgifera)",
                      "a northern corn rootworm beetle (Diabrotica barberi)"],
    "white_grub": ["a white grub", "a C-shaped white scarab beetle larva", "a June beetle grub in soil"],
    "ground_beetle": ["a ground beetle", "a carabid beetle", "a black ground beetle (Carabidae)"],
    "millipede": ["a millipede", "a millipede (Diplopoda) curled in soil", "a many-legged millipede"],
    "earthworm": ["an earthworm", "an earthworm in soil", "a pink earthworm (Lumbricidae)"],
    "other": ["a centipede", "a woodlouse", "a caterpillar", "a fly larva", "an ant", "a spider",
              "a slug", "a plant", "a mushroom", "an insect", "a small animal in soil"],
}
TEMPLATES = ["a photo of {}.", "a close-up photo of {}.", "a field photo of {} found in soil."]


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--attr", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="ViT-B-32")
    ap.add_argument("--pretrained", default="laion2b_s34b_b79k", help='"" for hf-hub models such as BioCLIP')
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model, _, pre = open_clip.create_model_and_transforms(a.model, pretrained=a.pretrained or None,
                                                            device="cuda")
    tok = open_clip.get_tokenizer(a.model)
    model.eval()
    W = []
    for c in CLASS_IDS:
        txt = [t.format(p) for p in PROMPTS[c] for t in TEMPLATES]
        e = model.encode_text(tok(txt).cuda()).float()
        e = e / e.norm(dim=-1, keepdim=True)
        W.append(e.mean(0) / e.mean(0).norm())
    W = torch.stack(W)
    scale = model.logit_scale.exp().item()
    attr_dir = Path(a.attr).parent
    splits = ["val", "ood"] + (["test"] if a.final else [])
    for s in splits:
        rows = read_rows(a.attr, {s}, CLASS_IDS, final=a.final, seal_file=attr_dir / "test_seal.txt",
                         log_file=attr_dir / "test_access.log", who=f"clip_baseline {a.model}")
        logits = []
        for i in range(0, len(rows), 64):
            x = torch.stack([pre(load_rgb(Path(a.data_root) / r["file"])) for r in rows[i:i + 64]]).cuda()
            f = model.encode_image(x).float()
            f = f / f.norm(dim=-1, keepdim=True)
            logits.append((scale * f @ W.T).cpu().numpy())
        L = np.concatenate(logits)
        np.save(out / f"{s}_logits.npy", L)
        y = labels(rows, CLASS_IDS)
        print(s, len(rows), "acc", float((L.argmax(1) == y).mean()), flush=True)
    json.dump({"model": a.model, "pretrained": a.pretrained, "prompts": PROMPTS, "templates": TEMPLATES},
              open(out / "clip_config.json", "w"), indent=1)


if __name__ == "__main__":
    main()
