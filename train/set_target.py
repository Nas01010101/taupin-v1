"""Switch the shipped abstain threshold to another validation target already in threshold_sweep.

labels.json and the at-threshold fields of metrics.json are rewritten from the stored sweep, so the
sealed test split is not read again. With --data-root it also scores, with onnxruntime CPU on this
machine, the audited OOD images and the images the audit removed, at the old and the new threshold.

    python train/set_target.py --target 0.98 --data-root ~/scratch/taupin-data \
        --attr-pre ~/scratch/taupin-data/attribution_ood648.csv
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from evalutil import load_rgb, preprocess, softmax

AT = ("coverage_at_threshold", "accuracy_at_threshold")


def answered(prob, y, thr, k):
    """Counts for class k: images, answered, answered and right. k=None: all images, y ignored."""
    top, pred = prob.max(1), prob.argmax(1)
    m = np.ones(len(prob), bool) if k is None else y == k
    out = {"n": int(m.sum()), "answered": int((m & (top >= thr)).sum())}
    if k is not None:
        out["answered_right"] = int((m & (top >= thr) & (pred == k)).sum())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, help="a key of threshold_sweep, e.g. 0.98")
    ap.add_argument("--model-dir", type=Path, default=Path(__file__).parent.parent / "model")
    ap.add_argument("--audit", type=Path, default=Path(__file__).parent.parent / "data/ood_audit.csv")
    ap.add_argument("--data-root", type=Path)
    ap.add_argument("--attr-pre", type=Path, help="attribution csv from before the OOD audit")
    a = ap.parse_args()
    mp, lp = a.model_dir / "metrics.json", a.model_dir / "labels.json"
    m, lab = json.load(open(mp)), json.load(open(lp))
    old, s = m["abstain_below"], m["threshold_sweep"][a.target]
    m.update(abstain_below=s["abstain_below"], abstain_target_accuracy=float(a.target),
             target_met_on_val=s["target_met_on_val"])
    for split in ("val", "test", "ood"):
        for k in AT:
            m["model"][split][k] = s[split][k]
            m["model"][split]["ci95"].pop(k, None)   # intervals were for the old threshold
    lab["abstain_below"] = s["abstain_below"]

    if a.data_root:
        import onnxruntime as ort
        classes = m["classes"]
        gone = {r["photo_id"] for r in csv.DictReader(open(a.audit))}
        rows = [r for r in csv.DictReader(open(a.attr_pre)) if r["split"] == "ood" and r["class"] in classes]
        assert gone <= {r["photo_id"] for r in rows}, "audit ids missing from the pre-audit csv"
        sess = ort.InferenceSession(str(a.model_dir / "taupin.onnx"), providers=["CPUExecutionProvider"])
        X = np.stack([preprocess(load_rgb(a.data_root / r["file"]), lab["input_size"]) for r in rows])
        L = np.concatenate([sess.run(["logits"], {"image": X[i:i + 32]})[0] for i in range(0, len(X), 32)])
        prob = softmax(L, lab["temperature"])
        y = np.array([classes.index(r["class"]) for r in rows])
        out = np.array([r["photo_id"] in gone for r in rows])
        ww = classes.index("wireworm")
        m["abstain_check"] = {
            "note": "onnxruntime CPU on arm64; removed = images the OOD audit took out",
            **{name: {"abstain_below": thr, "removed": answered(prob[out], y[out], thr, None),
                      "ood_wireworm": answered(prob[~out], y[~out], thr, ww)}
               for name, thr in (("previous", old), ("shipped", s["abstain_below"]))}}
        print(json.dumps(m["abstain_check"], indent=1))
    json.dump(m, open(mp, "w"), indent=1)
    json.dump(lab, open(lp, "w"), indent=1)
    print("abstain_below", old, "->", s["abstain_below"])


if __name__ == "__main__":
    main()
