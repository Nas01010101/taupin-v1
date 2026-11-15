"""Sample NASA SMAP L4 root-zone soil moisture at the demo field and compare it with the POWER
soil wetness (GWETROOT) that the field ranking uses. Output: web/data/smap.json.

SMAP is read from NASA GIBS (WMS, layer SMAP_L4_Analyzed_Root_Zone_Soil_Moisture, about 9 km),
which needs no login: each request returns one pixel as a PNG, and the GIBS colour map turns the
colour back into m3/m3 (bins of 0.003). Two dates a month, the 1st and the 15th.

    uv run --with pillow python -m taupin.smap --power power.json
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics as st
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYER = "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture"
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
COLORMAP = "https://gibs.earthdata.nasa.gov/colormaps/v1.3/SMAP_Analyzed_Soil_Moisture.xml"
BIN = re.compile(r'rgb="(\d+),(\d+),(\d+)"[^>]*value="\[([-\d.]+),?([-\d.+INF]*)[)\]]"')
FIRST, LAST = date(2015, 4, 1), date(2025, 9, 15)


def colormap(xml: str) -> dict[tuple[int, int, int], float]:
    """RGB -> bin centre in m3/m3."""
    out = {}
    for r, g, b, lo, hi in BIN.findall(xml):
        lo = float(lo)
        hi = float(hi) if hi and "INF" not in hi else lo
        out[(int(r), int(g), int(b))] = round((lo + hi) / 2, 4)
    return out


# Montreal island is masked out of SMAP L4 at the field itself, so the value is the median of the
# valid cells in a 0.4 degree box around it (about 45 km, close to the POWER grid of about 50 km).
BOX, PX = 0.2, 9


def url(lat: float, lon: float, day: date, d: float = BOX) -> str:
    # WMS 1.3.0 in EPSG:4326 takes the bounding box latitude first.
    return (f"{WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={LAYER}&CRS=EPSG:4326"
            f"&BBOX={lat - d},{lon - d},{lat + d},{lon + d}&WIDTH={PX}&HEIGHT={PX}&FORMAT=image/png"
            f"&TIME={day.isoformat()}")


def decode(png: bytes, cmap: dict) -> float | None:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    vals = [cell(im.getpixel((x, y)), cmap) for x in range(im.width) for y in range(im.height)]
    vals = [v for v in vals if v is not None and v >= 0]
    return round(st.median(vals), 4) if vals else None


def cell(px, cmap) -> float | None:
    if px[3] == 0:
        return None
    if px[:3] in cmap:
        return cmap[px[:3]]
    # nearest colour, for resampling at bin edges
    k = min(cmap, key=lambda c: sum((a - b) ** 2 for a, b in zip(c, px[:3])))
    return cmap[k] if sum((a - b) ** 2 for a, b in zip(k, px[:3])) < 30 else None


def get(u: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "taupin-bake"}), timeout=60) as r:
        return r.read()


def dates() -> list[date]:
    out, y, m = [], FIRST.year, FIRST.month
    while date(y, m, 1) <= LAST:
        out += [date(y, m, 1), date(y, m, 15)]
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return [d for d in out if FIRST <= d <= LAST]


def pearson(a: list[float], b: list[float]) -> float:
    ma, mb = st.fmean(a), st.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return num / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5


def compare(samples: dict[str, float], gwet: dict[str, float]) -> dict:
    """Monthly means of both series, the climatology of each month, and the agreement of
    month-to-month anomalies (each series minus its own monthly climatology)."""
    def monthly(s):
        acc = {}
        for k, v in s.items():
            if v is not None and v > -998:
                acc.setdefault(k.replace("-", "")[:6], []).append(v)
        return {k: st.fmean(v) for k, v in acc.items()}
    sm, gw = monthly(samples), monthly(gwet)
    common = sorted(set(sm) & set(gw))
    if len(common) < 24:
        # Anomalies need each calendar month at least twice; fewer usually means the SMAP fetch failed.
        raise ValueError(f"SMAP and GWETROOT overlap in {len(common)} months; need 24 or more")
    clim = lambda s: {m: st.fmean([s[k] for k in common if k[4:] == m]) for m in {k[4:] for k in common}}
    cs, cg = clim(sm), clim(gw)
    an_s = [sm[k] - cs[k[4:]] for k in common]
    an_g = [gw[k] - cg[k[4:]] for k in common]
    months = [f"{m:02d}" for m in range(1, 13)]
    dry = sorted(common, key=lambda k: sm[k] - cs[k[4:]])[:5]
    return {
        "months": len(common),
        "climatology": {m: {"smap": round(cs[m], 3), "gwetroot": round(cg[m], 3)} for m in months if m in cs},
        "anomaly_r": round(pearson(an_s, an_g), 2),
        "driest": [{"month": f"{k[:4]}-{k[4:]}", "smap": round(sm[k], 3),
                    "below_usual": round(sm[k] - cs[k[4:]], 3)} for k in dry],
        "series": {k: [round(sm[k], 3), round(gw[k], 3)] for k in common},
    }


def bake(lat: float, lon: float, gwet: dict, workers: int = 6) -> dict:
    cmap = colormap(get(COLORMAP).decode())
    ds = dates()
    with ThreadPoolExecutor(workers) as ex:
        pngs = list(ex.map(lambda d: get(url(lat, lon, d)), ds))
    samples = {d.isoformat(): decode(p, cmap) for d, p in zip(ds, pngs)}
    return {
        "site": {"lat": lat, "lon": lon},
        "unit": "m3/m3",
        "samples": samples,
        "compare": compare(samples, gwet),
        "sources": {
            "smap": f"NASA SMAP L4 analysed root-zone soil moisture (0 to 100 cm), GIBS layer {LAYER}, "
                    "decoded from the GIBS colour map (bins of 0.003 m3/m3); median of the valid cells "
                    "within 0.2 degrees of the field",
            "gwetroot": "NASA POWER daily point API, GWETROOT (MERRA-2), 0 = dry, 1 = saturated",
        },
    }


def main(argv=None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--power", type=Path, required=True, help="POWER JSON with GWETROOT")
    a.add_argument("--out", type=Path, default=ROOT / "web" / "data" / "smap.json")
    o = a.parse_args(argv)
    d = json.loads(o.power.read_text())
    lon, lat = d["geometry"]["coordinates"][:2]
    res = bake(lat, lon, d["properties"]["parameter"]["GWETROOT"])
    o.out.write_text(json.dumps(res, separators=(",", ":")))
    print(o.out, sum(v is not None for v in res["samples"].values()), "of", len(res["samples"]),
          "| r", res["compare"]["anomaly_r"])


if __name__ == "__main__":
    main()
