"""Score an already-calibrated ONNX model on the OOD split with its own temperature and threshold.

Used to put v1 on the extended OOD set without re-reading test or re-fitting anything.

    python rescore_ood.py --model-dir ../model_v1 --data-root ../data --attr ../meta/attribution.csv
"""
import argparse
import json
from pathlib import Path

import onnxruntime as ort

from data import labels, read_rows
from evalutil import report
from final_eval import arrays, ort_logits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--attr", required=True)
    a = ap.parse_args()
    lab = json.load(open(a.model_dir / "labels.json"))
    classes = [c["id"] for c in lab["classes"]]
    rows = read_rows(a.attr, {"ood"}, classes)
    sess = ort.InferenceSession(str(a.model_dir / "taupin.onnx"), providers=["CPUExecutionProvider"])
    L = ort_logits(sess, arrays(rows, a.data_root, lab["input_size"]))
    r = report(L, labels(rows, classes), lab["temperature"], lab["abstain_below"], classes)
    json.dump({"version": lab["version"], "ood": r}, open(a.model_dir / "ood_rescored.json", "w"), indent=1)
    print(json.dumps({k: r[k] for k in ["n", "accuracy", "macro_f1", "coverage_at_threshold",
                                        "accuracy_at_threshold"]}))


if __name__ == "__main__":
    main()
