"""Build web/data/gallery.json and copy credited insect photos into web/gallery/.

Sources, in order:
  1. a Commons set with a Markdown credit table (wireworm-risk-twin assets/insects/ATTRIBUTION.md)
  2. the ML samples: data/samples/<class_id>/*.jpg credited by rows of data/attribution.csv
A photo with no credit row is skipped: the gallery never shows an image it cannot attribute.

    python -m taupin.gallery --commons ../wireworm-risk-twin/assets/insects
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Commons file -> (class id from model/labels.json or None, caption)
COMMONS = {
    "wireworm_larva.jpg": ("wireworm", "Wireworm (Elateridae larva)"),
    "click_beetle_adult.jpg": ("click_beetle", "Click beetle (Agriotes adult)"),
    "wcr_adult.jpg": ("corn_rootworm", "Western corn rootworm adult"),
    "wcr_larvae.jpg": (None, "Corn rootworm larvae (not a model class)"),
    "white_grub.jpg": ("white_grub", "White grub (scarab larva)"),
    "ground_beetle.jpg": ("ground_beetle", "Ground beetle (Carabidae, beneficial)"),
}
NC = ("-nc", " nc", "noncommercial", "non-commercial")


def parse_md_table(text: str) -> list[dict]:
    rows, header = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
        elif not set("".join(cells)) <= set("-: "):
            rows.append(dict(zip(header, cells)))
    return rows


def _pick(row: dict, *keys: str) -> str:
    for k, v in row.items():
        if any(key in k.lower() for key in keys):
            return (v or "").strip()
    return ""


def open_licence(lic: str) -> bool:
    low = lic.lower()
    return bool(low) and not any(t in low for t in NC)


def from_commons(src: Path, dst: Path) -> list[dict]:
    md = src / "ATTRIBUTION.md"
    if not md.exists():
        return []
    out = []
    for row in parse_md_table(md.read_text()):
        f = row.get("file", "")
        if f not in COMMONS or not (src / f).exists() or not open_licence(row.get("licence", "")):
            continue
        shutil.copy2(src / f, dst / f)
        cls, caption = COMMONS[f]
        out.append({"file": f"gallery/{f}", "class_id": cls, "caption": caption, "author": row.get("author", ""),
                    "licence": row.get("licence", ""), "source": row.get("source", "")})
    return out


def from_samples(samples: Path, attribution: Path, dst: Path) -> list[dict]:
    if not samples.is_dir() or not attribution.exists():
        return []
    with attribution.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for img in sorted(samples.glob("*/*.jpg")):
        cls = img.parent.name
        match = next((r for r in rows if _pick(r, "file", "path").replace("\\", "/").endswith(f"{cls}/{img.name}")
                      or _pick(r, "file", "path").endswith(img.name)
                      or (_pick(r, "source_id", "source id", "id") and _pick(r, "source_id", "source id", "id") == img.stem)), None)
        if match is None:
            continue
        lic = _pick(match, "licen")
        if not open_licence(lic):
            continue
        name = f"{cls}__{img.name}"
        shutil.copy2(img, dst / name)
        out.append({"file": f"gallery/{name}", "class_id": cls, "caption": cls.replace("_", " "),
                    "author": _pick(match, "author", "creator"), "licence": lic,
                    "source": _pick(match, "url", "source")})
    return out


def build(commons: Path | None, samples: Path, attribution: Path, web: Path) -> list[dict]:
    dst = web / "gallery"
    dst.mkdir(parents=True, exist_ok=True)
    items = (from_commons(commons, dst) if commons else []) + from_samples(samples, attribution, dst)
    (web / "data" / "gallery.json").write_text(json.dumps({"items": items}, indent=1, ensure_ascii=False))
    return items


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--commons", type=Path, help="folder with ATTRIBUTION.md and the Commons photos")
    p.add_argument("--samples", type=Path, default=ROOT / "data" / "samples")
    p.add_argument("--attribution", type=Path, default=ROOT / "data" / "attribution.csv")
    p.add_argument("--web", type=Path, default=ROOT / "web")
    a = p.parse_args(argv)
    items = build(a.commons, a.samples, a.attribution, a.web)
    print(len(items), "gallery photos")


if __name__ == "__main__":
    main()
