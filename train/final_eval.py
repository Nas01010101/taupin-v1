"""Export to ONNX, verify it against PyTorch, calibrate on val, evaluate test and OOD once.

Metrics are computed from onnxruntime CPU logits with the reference preprocessing in
evalutil.preprocess, i.e. from the file the app ships. Temperature and abstain threshold are fit
on validation only.

    python final_eval.py --ckpt runs/v1/best.pt --data-root D --attr data/attribution.csv \
        --clip runs/clip_b32 --model-dir model --final
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import timm
import torch

from data import labels, read_rows
from evalutil import MEAN, STD, fit_temperature, headline, load_rgb, pick_threshold, preprocess, report, softmax

NAMES = {"wireworm": ("Wireworm (click beetle larva)", True),
         "click_beetle": ("Click beetle (adult)", True),
         "corn_rootworm": ("Corn rootworm beetle (adult)", True),
         "white_grub": ("White grub (scarab larva)", True),
         "ground_beetle": ("Ground beetle (beneficial)", False),
         "millipede": ("Millipede (not an insect)", False),
         "earthworm": ("Earthworm (beneficial)", False),
         "other": ("Other soil animal or object", False)}


def arrays(rows, root, size):
    return np.stack([preprocess(load_rgb(Path(root) / r["file"]), size) for r in rows])


def ort_logits(sess, X, bs=32):
    return np.concatenate([sess.run(["logits"], {"image": X[i:i + bs]})[0] for i in range(0, len(X), bs)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--attr", required=True)
    ap.add_argument("--clip", nargs="*", default=[], help="dirs with {val,test,ood}_logits.npy")
    ap.add_argument("--model-dir", required=True)
    # 0.90 is the spec floor; v1 validation accuracy was already 0.905 with no abstention, so a
    # 0.90 target gives threshold 0 and no "send to the lab" path. 0.95 keeps a real abstain path.
    ap.add_argument("--target", type=float, default=0.95)
    ap.add_argument("--sweep", type=float, nargs="*", default=[0.90, 0.95, 0.98])
    ap.add_argument("--version", default="v1")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--quantize", action="store_true")
    a = ap.parse_args()
    ck = torch.load(a.ckpt, map_location="cpu", weights_only=False)
    classes, size = ck["classes"], ck["size"]
    model = timm.create_model(ck["arch"], pretrained=False, num_classes=len(classes), **ck.get("kw", {}))
    model.load_state_dict(ck["state"])
    model.eval()
    md = Path(a.model_dir)
    md.mkdir(parents=True, exist_ok=True)
    onnx_path = md / "taupin.onnx"
    fp32_path = Path(a.ckpt).parent / "taupin_fp32.onnx" if a.quantize else onnx_path
    torch.onnx.export(model, torch.randn(1, 3, size, size), str(fp32_path), input_names=["image"],
                      output_names=["logits"], dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17, dynamo=False)
    if a.quantize:  # int8 weights for MatMul only; activations quantized at run time
        from onnxruntime.quantization import QuantType, quantize_dynamic
        quantize_dynamic(str(fp32_path), str(onnx_path), weight_type=QuantType.QInt8,
                         op_types_to_quantize=["MatMul"])
    m = onnx.load(str(onnx_path))
    onnx.checker.check_model(m)
    ops = sorted({n.op_type for n in m.graph.node})
    opset = max(o.version for o in m.opset_import if o.domain in ("", "ai.onnx"))
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    sess32 = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    attr_dir = Path(a.attr).parent
    rows, X, y, L, Lt, L32 = {}, {}, {}, {}, {}, {}
    for s in ["val", "ood", "test"]:
        rows[s] = read_rows(a.attr, {s}, classes, final=a.final, seal_file=attr_dir / "test_seal.txt",
                            log_file=attr_dir / "test_access.log", who=f"final_eval {a.version}")
        X[s] = arrays(rows[s], a.data_root, size)
        y[s] = labels(rows[s], classes)
        L[s] = ort_logits(sess, X[s])
        L32[s] = ort_logits(sess32, X[s]) if a.quantize else L[s]
        with torch.no_grad():
            Lt[s] = np.concatenate([model(torch.from_numpy(X[s][i:i + 64])).numpy()
                                    for i in range(0, len(X[s]), 64)])
        print(s, len(y[s]), "ort acc", float((L[s].argmax(1) == y[s]).mean()), flush=True)
    diff = max(float(np.abs(L32[s] - Lt[s]).max()) for s in L)  # fp32 ONNX vs PyTorch
    agree = min(float((L32[s].argmax(1) == Lt[s].argmax(1)).mean()) for s in L)
    qdiff = max(float(np.abs(L[s] - L32[s]).max()) for s in L)  # shipped (int8) vs fp32 ONNX
    qagree = min(float((L[s].argmax(1) == L32[s].argmax(1)).mean()) for s in L)
    T = fit_temperature(L["val"], y["val"])
    thr, met = pick_threshold(softmax(L["val"], T), y["val"], a.target)
    res = {"model": {s: report(L[s], y[s], T, thr, classes) for s in ["val", "test", "ood"]}}
    # OOD by photo type: museum or lab specimens versus field observations
    spec = np.array([r.get("quality", "") in ("PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "MATERIAL_CITATION")
                     for r in rows["ood"]])
    res["model"]["ood_subsets"] = {k: report(L["ood"][m], y["ood"][m], T, thr, classes)
                                   for k, m in [("specimen", spec), ("field_or_other", ~spec)] if m.sum() >= 20}
    sweep = {}
    for tg in a.sweep:  # reported for transparency; only --target is shipped
        pv = softmax(L["val"], T)
        t_, m_ = pick_threshold(pv, y["val"], tg)
        sweep[str(tg)] = {"abstain_below": t_, "target_met_on_val": m_,
                          **{s: headline(softmax(L[s], T), y[s], t_, len(classes)) for s in ["val", "test", "ood"]}}
    res["threshold_sweep"] = sweep
    base = {}
    for cdir in a.clip:
        cfg = json.load(open(Path(cdir) / "clip_config.json"))
        CL = {s: np.load(Path(cdir) / f"{s}_logits.npy") for s in ["val", "test", "ood"]}
        Tc = fit_temperature(CL["val"], y["val"])
        thc, metc = pick_threshold(softmax(CL["val"], Tc), y["val"], a.target)
        base[f"{cfg['model']}/{cfg['pretrained']}"] = {
            "temperature": Tc, "abstain_below": thc, "target_met_on_val": metc,
            **{s: report(CL[s], y[s], Tc, thc, classes) for s in ["val", "test", "ood"]},
            "ood_subsets": {k: report(CL["ood"][m], y["ood"][m], Tc, thc, classes)
                            for k, m in [("specimen", spec), ("field_or_other", ~spec)] if m.sum() >= 20}}
    counts = {s: {c: int((y[s] == k).sum()) for k, c in enumerate(classes)} for s in y}
    tr = read_rows(a.attr, {"train"}, classes)
    counts["train"] = {c: sum(r["class"] == c for r in tr) for c in classes}
    ood_src = {}
    for r in rows["ood"]:
        ood_src[r["source"]] = ood_src.get(r["source"], 0) + 1
    metrics = {"version": a.version, "arch": ck["arch"], "input_size": size, "classes": classes,
               "temperature": T, "abstain_below": thr, "abstain_target_accuracy": a.target,
               "target_met_on_val": met, "selected_epoch": ck["epoch"],
               "counts_per_split": counts, "ood_sources": ood_src,
               "onnx": {"opset": opset, "bytes": os.path.getsize(onnx_path), "ops": ops,
                        "quantized_int8_matmul": a.quantize,
                        "max_abs_logit_diff_vs_torch": diff, "top1_agreement_vs_torch": agree,
                        "max_abs_logit_diff_int8_vs_fp32": qdiff, "top1_agreement_int8_vs_fp32": qagree,
                        "ort_version": ort.__version__},
               **res, "clip_zero_shot": base}
    json.dump(metrics, open(md / "metrics.json", "w"), indent=1)
    labels_json = {"classes": [{"id": c, "name": NAMES[c][0], "pest": NAMES[c][1]} for c in classes],
                   "input_size": size, "mean": MEAN, "std": STD, "temperature": float(T),
                   "abstain_below": float(thr), "version": a.version}
    json.dump(labels_json, open(md / "labels.json", "w"), indent=1)
    for s in L:  # kept next to the checkpoint for later analysis, not shipped
        np.save(Path(a.ckpt).parent / f"{s}_ort_logits.npy", L[s])
    print(json.dumps({"T": T, "thr": thr, "diff": diff, "agree": agree,
                      "test": {k: res["model"]["test"][k] for k in ["accuracy", "macro_f1", "coverage_at_threshold", "accuracy_at_threshold"]},
                      "ood": {k: res["model"]["ood"][k] for k in ["accuracy", "macro_f1", "coverage_at_threshold", "accuracy_at_threshold"]}},
                     indent=1))


if __name__ == "__main__":
    main()
