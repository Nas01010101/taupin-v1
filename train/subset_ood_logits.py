"""Cut saved OOD logits down to the rows that survive the OOD audit, without re-running the model.

The audit only removes OOD rows and split.py keeps CSV order, so the new OOD rows are an ordered
subset of the old ones and their logits are the matching rows of the old array. The old array is
kept as ood_logits_<n>.npy.

    python subset_ood_logits.py --old-attr ../meta/attribution_ood648.csv --attr ../meta/attribution.csv \
        ../runs/clip_b32 ../runs/clip_l14 ../runs/bioclip
"""
import argparse
import csv
from pathlib import Path

import numpy as np


def ood_ids(attr_csv):
    return [r["photo_id"] for r in csv.DictReader(open(attr_csv)) if r["split"] == "ood"]


def subset_index(old_ids, new_ids):
    """Positions of new_ids inside old_ids; fails if new is not an ordered subset of old."""
    pos = {p: i for i, p in enumerate(old_ids)}
    idx = [pos[p] for p in new_ids]
    if idx != sorted(idx):
        raise ValueError("new OOD rows are not in the old order")
    return np.array(idx, dtype=int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-attr", required=True)
    ap.add_argument("--attr", required=True)
    ap.add_argument("dirs", nargs="+")
    a = ap.parse_args()
    old, new = ood_ids(a.old_attr), ood_ids(a.attr)
    idx = subset_index(old, new)
    for d in map(Path, a.dirs):
        L = np.load(d / "ood_logits.npy")
        if len(L) != len(old):
            raise ValueError(f"{d}: {len(L)} rows, old manifest has {len(old)}")
        np.save(d / f"ood_logits_{len(old)}.npy", L)
        np.save(d / "ood_logits.npy", L[idx])
        print(d, len(old), "->", len(idx))


if __name__ == "__main__":
    main()
