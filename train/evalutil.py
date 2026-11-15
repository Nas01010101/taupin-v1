"""Preprocessing, metrics, calibration and bootstrap shared by training, baseline and export.

`preprocess` is the reference preprocessing from docs/spec.md; the browser must match it.
"""
import numpy as np
from PIL import Image, ImageOps

MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def load_rgb(path):
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def resize_crop(im, size=224, resample=Image.BILINEAR):
    """Resize so the short side is `size`, then centre-crop size x size."""
    w, h = im.size
    s = size / min(w, h)
    nw, nh = max(size, round(w * s)), max(size, round(h * s))
    im = im.resize((nw, nh), resample)
    left, top = (nw - size) // 2, (nh - size) // 2
    return im.crop((left, top, left + size, top + size))


def preprocess(im, size=224, mean=MEAN, std=STD, resample=Image.BILINEAR):
    """PIL RGB image -> float32 [3,size,size], scaled to 0..1 then normalised."""
    x = np.asarray(resize_crop(im, size, resample), dtype=np.float32) / 255.0
    x = (x - np.array(mean, np.float32)) / np.array(std, np.float32)
    return x.transpose(2, 0, 1).copy()


def softmax(z, t=1.0):
    z = z / t
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def nll(logits, y, t):
    p = softmax(logits, t)
    return -np.log(p[np.arange(len(y)), y] + 1e-12).mean()


def fit_temperature(logits, y):
    """Grid then golden-section search for the NLL-minimising temperature on validation."""
    grid = np.exp(np.linspace(np.log(0.05), np.log(20), 200))
    t0 = grid[np.argmin([nll(logits, y, t) for t in grid])]
    lo, hi = t0 / 1.2, t0 * 1.2
    for _ in range(60):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if nll(logits, y, m1) < nll(logits, y, m2):
            hi = m2
        else:
            lo = m1
    return float((lo + hi) / 2)


def ece(prob, y, bins=15):
    conf, pred = prob.max(1), prob.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    e = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(e)


def pick_threshold(prob, y, target=0.90, min_coverage=0.05):
    """Lowest top-1 threshold whose answered set reaches `target` accuracy on validation.

    Lowest threshold maximises coverage among thresholds meeting the target. Returns
    (threshold, achieved) where achieved is False if no threshold met the target.
    """
    conf, ok = prob.max(1), prob.argmax(1) == y
    for t in np.unique(np.concatenate([[0.0], conf])):
        m = conf >= t
        if m.mean() < min_coverage:
            break
        if ok[m].mean() >= target:
            return float(t), True
    return float(np.quantile(conf, 1 - min_coverage)), False


def per_class(y, pred, n):
    out = []
    for k in range(n):
        tp = int(((pred == k) & (y == k)).sum())
        fp = int(((pred == k) & (y != k)).sum())
        fn = int(((pred != k) & (y == k)).sum())
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        out.append({"precision": p, "recall": r, "f1": f, "support": int((y == k).sum())})
    return out


def macro_f1(y, pred, n):
    present = [k for k in range(n) if (y == k).any()]
    pc = per_class(y, pred, n)
    return float(np.mean([pc[k]["f1"] for k in present])) if present else 0.0


def confusion(y, pred, n):
    m = np.zeros((n, n), int)
    np.add.at(m, (y, pred), 1)
    return m.tolist()


def headline(prob, y, thr, n):
    pred = prob.argmax(1)
    ans = prob.max(1) >= thr
    return {"accuracy": float((pred == y).mean()), "macro_f1": macro_f1(y, pred, n),
            "coverage_at_threshold": float(ans.mean()),
            "accuracy_at_threshold": float((pred[ans] == y[ans]).mean()) if ans.any() else None}


def bootstrap(prob, y, thr, n, reps=2000, seed=0):
    """Percentile 95% intervals for the headline numbers, resampling images."""
    rng = np.random.default_rng(seed)
    vals = {k: [] for k in ["accuracy", "macro_f1", "coverage_at_threshold", "accuracy_at_threshold"]}
    for _ in range(reps):
        i = rng.integers(0, len(y), len(y))
        h = headline(prob[i], y[i], thr, n)
        for k, v in h.items():
            if v is not None:
                vals[k].append(v)
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in vals.items() if v}


def report(logits, y, t, thr, classes):
    n = len(classes)
    prob = softmax(logits, t)
    pred = prob.argmax(1)
    pc = per_class(y, pred, n)
    return {"n": int(len(y)), **headline(prob, y, thr, n), "ci95": bootstrap(prob, y, thr, n),
            "ece": ece(prob, y), "nll": float(nll(logits, y, t)),
            "per_class": {c: pc[k] for k, c in enumerate(classes)},
            "confusion_matrix": {"labels": classes, "rows_true_cols_pred": confusion(y, pred, n)}}
