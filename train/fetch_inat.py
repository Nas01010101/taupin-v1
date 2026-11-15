"""Download open-licence (CC0, CC-BY) iNaturalist photos for each Taupin class.

One photo per observation (the first CC0/CC-BY photo) so near-identical shots of one animal do
not spread across splits. Writes <root>/inat_records.csv and images under <root>/img/inat/.

    uv run --with pillow python train/fetch_inat.py --root ~/scratch/taupin-data
"""
import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from classes import CLASSES

API = "https://api.inaturalist.org/v1/observations"
UA = "taupin-dataset-builder/0.1"  # generic client name, no personal details
OPEN = {"cc0", "cc-by"}
FIELDS = ["source", "source_id", "photo_id", "url", "author", "user_id", "licence",
          "taxon_id", "taxon_name", "class", "quality", "observed_on"]


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # rate limit or transient network error: back off
            print("retry", i, e, flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def query(taxon, extra, cap, grade):
    """Yield observation dicts, newest first, until `cap` are returned."""
    params = {"taxon_id": taxon, "photo_license": "cc0,cc-by", "quality_grade": grade,
              "captive": "false", "per_page": 200, "order_by": "id", "order": "desc", **extra}
    below, n = None, 0
    while n < cap:
        p = dict(params)
        if below:
            p["id_below"] = below
        res = get_json(API + "?" + urllib.parse.urlencode(p))["results"]
        time.sleep(1.1)  # iNaturalist asks for about 1 request per second
        if not res:
            return
        for o in res:
            below = o["id"]
            if grade == "needs_id" and not (o.get("num_identification_agreements", 0) >= 1
                                            and o.get("num_identification_disagreements", 0) == 0):
                continue
            yield o
            n += 1
            if n >= cap:
                return


def to_row(o, cls):
    ph = next((p for p in o.get("photos", []) if (p.get("license_code") or "") in OPEN), None)
    if ph is None or not ph.get("url"):
        return None
    t = o.get("taxon") or {}
    return {"source": "inaturalist", "source_id": f"inat-obs-{o['id']}", "photo_id": ph["id"],
            "url": ph["url"].replace("/square.", "/medium."),
            "author": ph.get("attribution", ""), "user_id": f"inat-user-{o['user']['id']}",
            "licence": ph["license_code"], "taxon_id": t.get("id"), "taxon_name": t.get("name"),
            "class": cls, "quality": o.get("quality_grade"), "observed_on": o.get("observed_on")}


def download(row, img_dir):
    out = img_dir / f"{row['photo_id']}.jpg"
    if not row["url"].startswith(("https://", "http://")):
        return False  # urllib would also open file:// from a tampered CSV
    if out.exists() and out.stat().st_size > 0:
        return True
    try:
        req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            out.write_bytes(r.read())
        return True
    except Exception as e:
        print("img fail", row["url"], e, flush=True)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*", help="restrict to these class ids")
    a = ap.parse_args()
    img_dir = a.root / "img" / "inat"
    img_dir.mkdir(parents=True, exist_ok=True)
    rec_path = a.root / "inat_records.csv"
    rows, seen = [], set()
    if rec_path.exists():  # resume: keep earlier classes
        rows = [r for r in csv.DictReader(rec_path.open())]
        if a.only:
            rows = [r for r in rows if r["class"] not in a.only]
        seen = {r["source_id"] for r in rows}
    for cls, _, _, queries in CLASSES:
        if a.only and cls not in a.only:
            continue
        if not a.only and any(r["class"] == cls for r in rows):
            continue
        n0 = len(rows)
        for taxon, extra, cap, relax in queries:
            grades = ["research", "needs_id"] if relax else ["research"]
            got = 0
            for g in grades:
                for o in query(taxon, extra, cap - got, g):
                    r = to_row(o, cls)
                    if r and r["source_id"] not in seen:
                        seen.add(r["source_id"])
                        rows.append(r)
                        got += 1
                if got >= cap:
                    break
        print(cls, len(rows) - n0, flush=True)
        with rec_path.open("w", newline="") as f:
            w = csv.DictWriter(f, FIELDS)
            w.writeheader()
            w.writerows(rows)
    with ThreadPoolExecutor(a.workers) as ex:
        ok = list(ex.map(lambda r: download(r, img_dir), rows))
    print("downloaded", sum(ok), "of", len(rows), flush=True)


if __name__ == "__main__":
    main()
