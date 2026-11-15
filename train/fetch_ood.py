"""Build the out-of-distribution test set from non-iNaturalist sources.

Sources: GBIF occurrence images from datasets other than iNaturalist, and Wikimedia Commons files
that are not copies of iNaturalist photos. Only per-image CC0, CC-BY or public-domain media are
kept (an open occurrence licence on GBIF does not license the image). Never used for training,
model selection, temperature or threshold.

    uv run --no-project python train/fetch_ood.py --root ~/scratch/taupin-data
"""
import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "taupin-dataset-builder/0.1"
GBIF = "https://api.gbif.org/v1/occurrence/search"
INAT_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
OPEN_MEDIA = re.compile(r"publicdomain/(zero|mark)|creativecommons\.org/licenses/by/|^cc0|^cc-?by(\s|-)?\d|^cc by \d|public domain", re.I)
NOT_OPEN = re.compile(r"nc|nd|sa", re.I)
FIELDS = ["source", "source_id", "photo_id", "url", "author", "user_id", "licence", "taxon_id",
          "taxon_name", "class", "quality", "observed_on", "dataset"]

# class -> list of (GBIF taxonKey, extra params, cap)
GBIF_Q = {
    "wireworm": [("7825", {"lifeStage": "Larva"}, 200)],
    "click_beetle": [("7825", {"lifeStage": "Adult"}, 150), ("7825", {}, 150)],
    "corn_rootworm": [("1048497", {}, 150), ("1048496", {}, 150)],
    "white_grub": [("5840", {"lifeStage": "Larva"}, 200)],
    "ground_beetle": [("3792", {}, 200)],
    "millipede": [("361", {}, 200)],
    "earthworm": [("6103", {}, 200)],
    # Chilopoda, Tenebrionidae larvae, Tipulidae larvae, Noctuidae larvae, Formicidae, Araneae, Gastropoda
    "other": [("360", {}, 40), ("7857", {"lifeStage": "Larva"}, 40), ("7634", {"lifeStage": "Larva"}, 40),
              ("7015", {"lifeStage": "Larva"}, 40), ("4342", {}, 30), ("1496", {}, 30), ("225", {}, 30)],
}
# Wikimedia Commons categories (searched recursively one level)
COMMONS_Q = {
    "wireworm": ["Elateridae larvae", "Wireworms", "Agriotes larvae", "Agriotes lineatus", "Elateridae (larvae)",
                 "Larvae of Elateridae", "Agriotes obscurus", "Agriotes sputator"],
    "click_beetle": ["Elateridae", "Agriotes"],
    "corn_rootworm": ["Diabrotica virgifera", "Diabrotica barberi", "Diabrotica virgifera virgifera"],
    "white_grub": ["Scarabaeidae larvae", "White grubs", "Melolontha melolontha larvae", "Popillia japonica larvae", "Phyllophaga larvae"],
    "ground_beetle": ["Carabidae", "Carabus", "Pterostichus", "Harpalus"],
    "millipede": ["Diplopoda", "Julidae", "Polydesmidae", "Tachypodoiulus niger", "Ommatoiulus sabulosus",
                  "Narceus americanus", "Cylindroiulus", "Glomeris marginata", "Polydesmus", "Oxidus gracilis",
                  "Julus scandinavius", "Diplopoda in Quebec"],
    "earthworm": ["Lumbricidae", "Lumbricus terrestris", "Earthworms", "Lumbricus rubellus", "Aporrectodea",
                  "Eisenia fetida", "Allolobophora chlorotica", "Octolasion", "Aporrectodea caliginosa",
                  "Dendrobaena", "Lumbricus"],
    "other": ["Chilopoda", "Oniscidea", "Tenebrionidae larvae", "Tipulidae larvae", "Agrotis larvae", "Soil"],
}


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, e, flush=True)
            time.sleep(4 * (i + 1))
    return None


def is_open(lic):
    return bool(lic) and bool(OPEN_MEDIA.search(lic)) and not NOT_OPEN.search(lic.split("licenses/")[-1] if "licenses/" in lic else lic)


def gbif_rows(cls, key, extra, cap, per_dataset=60):
    out, per_ds, offset = [], {}, 0
    while len(out) < cap and offset < 3000:
        p = {"taxonKey": key, "mediaType": "StillImage", "limit": 300, "offset": offset, **extra}
        r = get_json(GBIF + "?" + urllib.parse.urlencode(p))
        if not r or not r["results"]:
            break
        for o in r["results"]:
            ds = o.get("datasetKey")
            if ds == INAT_DATASET or "inaturalist" in json.dumps(o.get("media", [])).lower():
                continue
            m = next((x for x in o.get("media", []) if x.get("type") == "StillImage" and x.get("identifier")), None)
            if not m or not is_open(m.get("license", "")) or per_ds.get(ds, 0) >= per_dataset:
                continue
            per_ds[ds] = per_ds.get(ds, 0) + 1
            out.append({"source": "gbif", "source_id": f"gbif-occ-{o['key']}", "photo_id": f"g{o['key']}",
                        "url": m["identifier"], "author": m.get("rightsHolder") or m.get("creator") or o.get("recordedBy") or "",
                        "user_id": f"gbif-{ds}-{o.get('recordedBy', '')}", "licence": m["license"],
                        "taxon_id": o.get("taxonKey"), "taxon_name": o.get("scientificName"), "class": cls,
                        "quality": o.get("basisOfRecord"), "observed_on": o.get("eventDate", ""), "dataset": ds})
            if len(out) >= cap:
                break
        if r.get("endOfRecords"):
            break
        offset += 300
    return out


COMMONS = "https://commons.wikimedia.org/w/api.php"


def commons_rows(cls, cat, cap=80):
    p = {"action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": f"Category:{cat}",
         "gcmtype": "file", "gcmlimit": 200, "prop": "imageinfo", "iiprop": "url|extmetadata|size",
         "iiurlwidth": 640}
    r = get_json(COMMONS + "?" + urllib.parse.urlencode(p))
    time.sleep(1)
    out = []
    for pg in ((r or {}).get("query", {}).get("pages", {}) or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        blob = json.dumps(md).lower()
        if not pg["title"].lower().endswith((".jpg", ".jpeg", ".png")) or "inaturalist" in blob:
            continue
        if not is_open(lic):
            continue
        artist = re.sub("<[^>]+>", "", md.get("Artist", {}).get("value", "")).strip()
        out.append({"source": "wikimedia_commons", "source_id": f"commons-{pg['pageid']}", "photo_id": f"c{pg['pageid']}",
                    "url": ii.get("thumburl") or ii.get("url"), "author": artist, "user_id": f"commons-{artist}",
                    "licence": lic, "taxon_id": "", "taxon_name": cat, "class": cls, "quality": "",
                    "observed_on": md.get("DateTimeOriginal", {}).get("value", "")[:20],
                    "dataset": "commons:" + ii.get("descriptionurl", "")})
        if len(out) >= cap:
            break
    return out


ILLUSTRATION = re.compile(r"plate|calwer|britannica|illustrat|drawing|engraving|lithograph|diagram|tafel|\.png$|\.svg|icon|map", re.I)


def commons_thumb(url, width=960):
    """upload.wikimedia.org original -> its standard-width thumbnail URL."""
    path = url.split("?")[0].split("/wikipedia/commons/", 1)[1]  # a/ab/Name.jpg
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{path}/{width}px-{path.rsplit('/', 1)[1]}"


def download(row, img_dir, tries=4):
    out = img_dir / f"{row['photo_id']}.jpg"
    if not row["url"].startswith(("https://", "http://")):
        return False  # urllib would also open file:// from a tampered CSV
    if out.exists() and out.stat().st_size > 0:
        return True
    if row["source"] == "wikimedia_commons" and ILLUSTRATION.search(row["dataset"]):
        return False  # drawings and plates are not field photos
    urls = [row["url"]]
    if row["source"] == "wikimedia_commons":  # originals get HTTP 429; standard 960px thumbnails do not
        urls.insert(0, commons_thumb(row["url"]))
    for i in range(tries):
        try:
            req = urllib.request.Request(urls[min(i, len(urls) - 1)], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if len(data) > 25_000_000:
                return False
            out.write_bytes(data)
            if row["source"] == "wikimedia_commons":
                time.sleep(1.0)  # Commons rate-limits bursts
            return True
        except Exception as e:
            if i == 0 and len(urls) > 1:
                continue  # thumbnail missing (small original): fall back to the original
            if "429" in str(e) and i + 1 < tries:
                time.sleep(10 * (i + 1))
                continue
            print("img fail", row["url"][:100], e, flush=True)
            return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--download-only", action="store_true", help="retry downloads from ood_records.csv")
    ap.add_argument("--extend-commons", nargs="*", help="append Commons rows for these classes")
    a = ap.parse_args()
    img_dir = a.root / "img" / "ood"
    img_dir.mkdir(parents=True, exist_ok=True)
    if a.download_only:
        rows = list(csv.DictReader((a.root / "ood_records.csv").open()))
        commons = [r for r in rows if r["source"] == "wikimedia_commons"]
        with ThreadPoolExecutor(a.workers) as ex:
            ok = list(ex.map(lambda r: download(r, img_dir), [r for r in rows if r not in commons]))
        ok += [download(r, img_dir) for r in commons]  # sequential for Commons
        print("downloaded", sum(ok), "of", len(rows), flush=True)
        return
    if a.extend_commons:
        rows = list(csv.DictReader((a.root / "ood_records.csv").open()))
        seen = {r["source_id"] for r in rows}
        for cls in a.extend_commons:
            add = [r for cat in COMMONS_Q[cls] for r in commons_rows(cls, cat) if r["source_id"] not in seen]
            for r in add:
                seen.add(r["source_id"])
                rows.append(r)
            print(cls, "added", len(add), flush=True)
        with (a.root / "ood_records.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, FIELDS)
            w.writeheader()
            w.writerows(rows)
        ok = [download(r, img_dir) for r in rows]
        print("downloaded", sum(ok), "of", len(rows), flush=True)
        return
    rows, seen = [], set()
    for cls in GBIF_Q:
        n0 = len(rows)
        cands = [r for k, ex, cap in GBIF_Q[cls] for r in gbif_rows(cls, k, ex, cap)]
        cands += [r for cat in COMMONS_Q[cls] for r in commons_rows(cls, cat)]
        for r in cands:
            if r["source_id"] not in seen:
                seen.add(r["source_id"])
                rows.append(r)
        print(cls, len(rows) - n0, flush=True)
    with (a.root / "ood_records.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    with ThreadPoolExecutor(a.workers) as ex:
        ok = list(ex.map(lambda r: download(r, img_dir), rows))
    print("downloaded", sum(ok), "of", len(rows), flush=True)


if __name__ == "__main__":
    main()
