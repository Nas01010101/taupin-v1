"""Insect photo classification with the ONNX model, mirroring web/js/classify.js step for step.

Preprocess (model/labels.json contract): resize so the short side is S with a triangle
(antialiased bilinear) filter, the same kernel as PIL BILINEAR and torchvision Resize; centre
crop S x S; scale to 0..1; normalise with mean/std. The resize is written out here instead of
calling PIL so the browser and this CLI compute the same numbers.
Then softmax(logits / temperature); a top-1 probability below `abstain_below` means "unclear".
Needs the `classify` extra (numpy, pillow, onnxruntime).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

UNCLEAR = "unclear: send to the lab"


def round_half_even(x: float) -> int:
    return int(round(x))   # Python rounds half to even, as torchvision CenterCrop does


def target_size(w: int, h: int, s: int) -> tuple[int, int]:
    """(new_w, new_h) with the short side equal to s; the long side is truncated, as torchvision."""
    if w <= h:
        return s, int(s * h / w)
    return int(s * w / h), s


def resize_weights(in_size: int, out_size: int, start: int, count: int):
    """Rows of the triangle-filter matrix for output pixels start..start+count-1, shape (count, in_size)."""
    import numpy as np
    scale = in_size / out_size
    fs = max(scale, 1.0)
    m = np.zeros((count, in_size), dtype=np.float64)
    for k in range(count):
        center = (start + k + 0.5) * scale
        lo = max(math.floor(center - fs + 0.5), 0)
        hi = min(math.floor(center + fs + 0.5), in_size)
        xs = np.arange(lo, hi)
        w = np.clip(1.0 - np.abs((xs + 0.5 - center) / fs), 0.0, None)
        total = w.sum()
        m[k, lo:hi] = w / total if total > 0 else 0.0
    return m


def preprocess(rgb, labels: dict):
    """uint8 array (H, W, 3) -> float32 (1, 3, S, S) normalised tensor."""
    import numpy as np
    s = int(labels["input_size"])
    h, w = rgb.shape[:2]
    nw, nh = target_size(w, h, s)
    top, left = round_half_even((nh - s) / 2), round_half_even((nw - s) / 2)
    wy = resize_weights(h, nh, top, s)
    wx = resize_weights(w, nw, left, s)
    img = rgb.astype(np.float64) / 255.0
    rows = np.tensordot(wy, img, axes=(1, 0))                       # (S, W, 3)
    out = np.tensordot(rows, wx, axes=(1, 1)).transpose(1, 0, 2)     # (3, S, S)
    mean = np.array(labels["mean"], dtype=np.float64)[:, None, None]
    std = np.array(labels["std"], dtype=np.float64)[:, None, None]
    return ((out - mean) / std).astype(np.float32)[None]


def softmax(logits, temperature: float = 1.0) -> list[float]:
    z = [v / temperature for v in logits]
    m = max(z)
    e = [math.exp(v - m) for v in z]
    t = sum(e)
    return [v / t for v in e]


def decide(probs: list[float], labels: dict) -> dict:
    """Top-1 class, its probability, and whether it falls below the abstain threshold."""
    i = max(range(len(probs)), key=probs.__getitem__)
    cls = labels["classes"][i]
    unclear = probs[i] < float(labels.get("abstain_below", 0.0))
    ranked = sorted(range(len(probs)), key=probs.__getitem__, reverse=True)
    return {"id": cls["id"], "name": cls["name"], "pest": bool(cls.get("pest", False)),
            "prob": probs[i], "unclear": unclear,
            "top": [{"id": labels["classes"][j]["id"], "name": labels["classes"][j]["name"], "prob": probs[j]}
                    for j in ranked[:3]]}


def load_rgb(path: Path):
    import numpy as np
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        return np.asarray(ImageOps.exif_transpose(im).convert("RGB"))


def classify(photo: Path, model_dir: Path) -> dict:
    import onnxruntime as ort
    labels = json.loads((model_dir / "labels.json").read_text())
    sess = ort.InferenceSession(str(model_dir / "taupin.onnx"), providers=["CPUExecutionProvider"])
    x = preprocess(load_rgb(photo), labels)
    logits = sess.run(None, {sess.get_inputs()[0].name: x})[0][0].tolist()
    return decide(softmax(logits, float(labels.get("temperature", 1.0))), labels)


def format_answer(r: dict) -> str:
    """One line, same wording as the browser card."""
    pct = f"{100 * r['prob']:.1f} %"
    if r["unclear"]:
        return f"{UNCLEAR} (best guess {r['name']}, {pct})"
    return f"{r['name']} ({pct}){', pest' if r['pest'] else ''}"
