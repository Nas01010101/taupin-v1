"""Copy 3 CC0/CC-BY test-split photos per class into data/samples/<class>/ (each <= 200 KB) and
write model/reference_outputs.json with the expected logits for two of them.

Samples come from the held-out test split so the demo never shows a training image. The
reference logits are computed by onnxruntime on the sample file exactly as saved, with the
reference preprocessing, so the browser test can compare against them.

    uv run --no-project --with pillow --with numpy --with onnxruntime python train/make_samples.py \
        --root ~/scratch/taupin-data --data data --model model
"""
import argparse
import csv
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from evalutil import load_rgb, preprocess, softmax

OPEN = {"cc0", "cc-by", "CC0", "CC BY 4.0", "http://creativecommons.org/publicdomain/zero/1.0/",
        "http://creativecommons.org/licenses/by/4.0/"}


def shrink(path, limit=200_000):
    im = load_rgb(path)
    for side, q in [(640, 85), (512, 82), (448, 78), (384, 75), (320, 70)]:
        s = side / max(im.size)
        im2 = im.resize((round(im.width * s), round(im.height * s)), Image.BILINEAR) if s < 1 else im
        buf = io.BytesIO()
        im2.save(buf, "JPEG", quality=q)
        if buf.tell() <= limit:
            return buf.getvalue()
    raise ValueError(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--dump-inputs", type=Path)
    a = ap.parse_args()
    import onnxruntime as ort
    lab = json.load(open(a.model / "labels.json"))
    classes = [c["id"] for c in lab["classes"]]
    sess = ort.InferenceSession(str(a.model / "taupin.onnx"), providers=["CPUExecutionProvider"])
    attr = a.data / "attribution.csv"
    rows = list(csv.DictReader(attr.open()))
    fields = list(rows[0].keys())
    out_rows, ref = [], []
    for c in classes:
        d = a.data / "samples" / c
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.jpg"):
            old.unlink()
        cand = [r for r in rows if r["split"] == "test" and r["class"] == c and r["licence"] in OPEN]
        picked = 0
        for r in cand:
            if picked == 3:
                break
            try:
                data = shrink(a.root / r["file"])
            except Exception:
                continue
            name = f"{r['photo_id']}.jpg"
            (d / name).write_bytes(data)
            out_rows.append({**r, "split": "sample", "file": f"data/samples/{c}/{name}"})
            picked += 1
        print(c, picked)
    # expected outputs for the first sample of the first two pest classes
    dumped = []
    for r in out_rows[:1] + out_rows[3:4]:
        x = preprocess(load_rgb(a.data.parent / r["file"]), lab["input_size"], lab["mean"], lab["std"])[None]
        dumped.append(x)
        z = sess.run(["logits"], {"image": x})[0][0]
        p = softmax(z[None], lab["temperature"])[0]
        ref.append({"file": r["file"], "true_class": r["class"], "logits": [float(v) for v in z],
                    "probs_after_temperature": [float(v) for v in p],
                    "top1": classes[int(p.argmax())], "input_first_pixel_rgb": [float(v) for v in x[0, :, 0, 0]],
                    "input_mean_per_channel": [float(v) for v in x[0].mean((1, 2))]})
    if a.dump_inputs:  # float32 tensors for train/check_ortweb.mjs
        np.concatenate(dumped).astype(np.float32).tofile(a.dump_inputs)
    json.dump({"classes": classes, "temperature": lab["temperature"], "input_size": lab["input_size"],
               "mean": lab["mean"], "std": lab["std"], "version": lab["version"],
               "tolerance_note": ("identical input tensors give logits within about 1e-4; a different resize "
                                  "or crop in the browser shows up as differences well above 1e-2"),
               "samples": ref}, open(a.model / "reference_outputs.json", "w"), indent=1)
    keep = [r for r in rows if r["split"] != "sample"]
    with attr.open("w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(keep + out_rows)


if __name__ == "__main__":
    main()
