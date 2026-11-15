"""Assign splits, remove near-duplicates and write data/attribution.csv plus the test seal.

- iNaturalist rows are split by observer (user id hashed into train 70 / val 15 / test 15), so no
  photographer is on two sides.
- A 64-bit difference hash (dHash) marks near-identical photos. An image within Hamming distance
  DUP_BITS of an image in another split is dropped (from the later split in val -> test -> ood
  order), so duplicates never cross splits. OOD rows near any iNaturalist image are dropped.
- The test manifest hash goes to data/test_seal.txt; train.py refuses to read test rows unless
  told this is the final evaluation, and every such read is appended to data/test_access.log.

    uv run --no-project --with pillow python train/split.py --root ~/scratch/taupin-data --out data
"""
import argparse
import csv
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from fetch_ood import ILLUSTRATION

DUP_BITS = 6
ATTR_FIELDS = ["url", "author", "licence", "source", "source_id", "class", "split", "photo_id",
               "user_id", "taxon_name", "dataset", "quality", "file"]


def dhash(path):
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("L")
            if min(im.size) < 64:
                return None
            im = im.resize((9, 8), Image.BILINEAR)
            px = list(im.get_flattened_data()) if hasattr(im, "get_flattened_data") else list(im.getdata())
        return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])
    except Exception:
        return None


def user_split(uid):
    h = int(hashlib.sha256(("taupin-v1" + uid).encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    rows = []
    for name, sub in [("inat_records.csv", "inat"), ("ood_records.csv", "ood")]:
        if not (a.root / name).exists():
            print("missing", name)
            continue
        for r in csv.DictReader((a.root / name).open()):
            r["file"] = f"img/{sub}/{r['photo_id']}.jpg"
            r["split"] = user_split(r["user_id"]) if sub == "inat" else "ood"
            r.setdefault("dataset", "inaturalist")
            if r["source"] == "wikimedia_commons" and ILLUSTRATION.search(r["dataset"]):
                continue  # drawings and plates are not photos
            rows.append(r)
    with ThreadPoolExecutor(4) as ex:
        hashes = list(ex.map(lambda r: dhash(a.root / r["file"]), rows))
    kept, dropped = [], {"unreadable": 0, "dup": 0}
    order = {"train": 0, "val": 1, "test": 2, "ood": 3}
    idx = sorted(range(len(rows)), key=lambda i: order[rows[i]["split"]])
    bank = []  # (hash, split) of accepted images
    for i in idx:
        h, r = hashes[i], rows[i]
        if h is None:
            dropped["unreadable"] += 1
            continue
        # OOD must not resemble any accepted image; in-distribution rows must not resemble other splits
        clash = any((h ^ bh).bit_count() <= DUP_BITS and (r["split"] == "ood" or bs != r["split"])
                    for bh, bs in bank)
        if clash:
            dropped["dup"] += 1
            continue
        bank.append((h, r["split"]))
        kept.append(r)
    a.out.mkdir(parents=True, exist_ok=True)
    with (a.out / "attribution.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ATTR_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)
    test_ids = sorted(r["source_id"] for r in kept if r["split"] == "test")
    seal = hashlib.sha256("\n".join(test_ids).encode()).hexdigest()
    (a.out / "test_seal.txt").write_text(f"{seal}  {len(test_ids)} test rows\n")
    counts = {}
    for r in kept:
        counts.setdefault(r["class"], {}).setdefault(r["split"], 0)
        counts[r["class"]][r["split"]] += 1
    for c, v in counts.items():
        print(c, v)
    print("dropped", dropped, "seal", seal[:16])


if __name__ == "__main__":
    main()
