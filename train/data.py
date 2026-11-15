"""Dataset over data/attribution.csv with the test seal enforced."""
import csv
import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from evalutil import load_rgb, preprocess

SEALED = {"test"}


def read_rows(attr_csv, splits, classes, final=False, seal_file=None, log_file=None, who=""):
    """Rows of the given splits. Reading 'test' needs final=True and a matching seal; it is logged."""
    rows = [r for r in csv.DictReader(open(attr_csv)) if r["split"] in splits and r["class"] in classes]
    if SEALED & set(splits):
        if not final:
            raise PermissionError("test split is sealed; pass --final for the one evaluation")
        ids = sorted(r["source_id"] for r in csv.DictReader(open(attr_csv)) if r["split"] == "test")
        seal = hashlib.sha256("\n".join(ids).encode()).hexdigest()
        expected = Path(seal_file).read_text().split()[0]
        if seal != expected:
            raise RuntimeError("test manifest changed since sealing")
        with open(log_file, "a") as f:
            f.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"),
                                "who": who, "seal": seal[:16]}) + "\n")
    return rows


class ImageRows(Dataset):
    def __init__(self, rows, root, classes, transform=None, size=224):
        self.rows, self.root, self.size = rows, Path(root), size
        self.cidx = {c: i for i, c in enumerate(classes)}
        self.transform = transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        im = load_rgb(self.root / r["file"])
        x = self.transform(im) if self.transform else torch.from_numpy(preprocess(im, self.size))
        return x, self.cidx[r["class"]]


def labels(rows, classes):
    c = {k: i for i, k in enumerate(classes)}
    return np.array([c[r["class"]] for r in rows])
