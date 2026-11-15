"""Bake the park rasters and NASA POWER soil temperature into small static files for web/.

Inputs (a field-shift `data/park/` fetch):  dem.tif (NASADEM), rgb.tif + ndvi.tif (HLS),
site.json, and a POWER daily JSON that carries TSOIL1.
Outputs in web/data/:
  field.json   parcel heights (m), NDVI, low-pocket mask, corner coordinates, sources
  field.png    true-colour HLS texture of the parcel
  soil.json    trap window per year, 12 C trend, Mar-Jul daily TSOIL1 for the recent years
  risk.json    3 rotations x 5 years wireworm / corn rootworm levels for two soil zones and two
               evidence scenarios, every line with its source (taupin.engine)
The parcel is the square at the site centre: the park is a meadow, not a crop field, so the
field-shift `pick_parcel` search for corn/soy does not apply.

    uv run --extra bake python -m taupin.bake --park ../field-shift/data/park \
        --tsoil ../wireworm-risk-twin/data/power_daily.json
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from . import engine, soil

ROOT = Path(__file__).resolve().parents[2]
START_YEAR = 2026
RECENT = [2021, 2022, 2023, 2024, 2025]
# Two zones of the same parcel. OM 12 % in the low pocket is a scenario to be measured, not data.
ZONES = {
    "upland": {"label": "Upland, clay-loam, OM 5 %", "field": engine.Field("clay-loam", 5.0)},
    "pocket": {"label": "Low wet pocket, clay-loam, OM 12 % (to be measured)",
               "field": engine.Field("clay-loam", 12.0)},
}
POCKET_PCT = 15   # lowest 15 % of parcel cells form the pocket zone


def load_power_param(path: Path, name: str) -> dict:
    """Accept both the POWER API GeoJSON ({properties: {parameter: ...}}) and a flat dict."""
    d = json.loads(path.read_text())
    params = d.get("properties", {}).get("parameter", d)
    if name not in params:
        raise KeyError(f"{path} has no {name}; fetch it with scripts/fetch_power.py")
    return params[name]


def risk_matrix() -> dict:
    """{zone: {scenario: {rotation: [YearRisk dict]}}}. The `trap_threshold` scenario feeds the
    engine a first-year bait-trap mean equal to the RAP threshold of the dominant genus."""
    out = {}
    for zk, z in ZONES.items():
        fld = z["field"]
        thr = engine.TRAP_THRESHOLD[fld.dominant_genus]
        scen = {"baseline": {}, "trap_threshold": {}}
        for rk, crops in engine.ROTATIONS.items():
            scen["baseline"][rk] = [asdict(r) for r in engine.plan_rotation(crops, fld, START_YEAR)]
            scen["trap_threshold"][rk] = [asdict(r) for r in engine.plan_rotation(
                crops, fld, START_YEAR, traps={START_YEAR: thr})]
        out[zk] = {"label": z["label"], "dominant_genus": fld.dominant_genus, "trap_threshold": thr,
                   "scenarios": scen}
    return {"start_year": START_YEAR, "rotations": {k: v for k, v in engine.ROTATIONS.items()},
            "zones": out, "sources": engine.SRC}


def box_blur(a, k: int):
    import numpy as np
    p = k // 2
    padded = np.pad(a, p, mode="edge")
    out = np.zeros_like(a, dtype=np.float64)
    for dr in range(k):
        for dc in range(k):
            out += padded[dr:dr + a.shape[0], dc:dc + a.shape[1]]
    return out / (k * k)


def true_color(rgb):
    """Per-band 2-98 percentile stretch plus gamma, so a summer scene doesn't render dark."""
    import numpy as np
    bands = []
    for b in rgb:
        lo, hi = np.nanpercentile(b, [2, 98])
        bands.append(np.clip((b - lo) / (hi - lo), 0, 1) ** 0.8)
    return (np.nan_to_num(np.stack(bands, -1)) * 255).astype(np.uint8)


def bake_field(park: Path, out: Path, size: int, tex: int) -> dict:
    import numpy as np
    import rasterio
    from PIL import Image

    site = json.loads((park / "site.json").read_text())
    with rasterio.open(park / "dem.tif") as r:
        dem = r.read(1).astype(np.float64)
        tr = r.transform
    with rasterio.open(park / "rgb.tif") as r:
        rgb = r.read().astype(np.float64)
    with rasterio.open(park / "ndvi.tif") as r:
        ndvi = r.read(1).astype(np.float64)
    h, w = dem.shape
    r0, c0 = (h - size) // 2, (w - size) // 2
    win = (slice(r0, r0 + size), slice(c0, c0 + size))
    height = box_blur(dem, 3)[win]     # NASADEM cells are integer metres with speckle
    pocket = height <= np.percentile(height, POCKET_PCT)
    nd = np.clip(np.nan_to_num(ndvi[win], nan=0.0), -1, 1)
    # Nearest keeps one visible block per 15 m cell: the HLS pixels as observed, not smoothed.
    Image.fromarray(true_color(rgb[:, win[0], win[1]])).resize((tex, tex), Image.NEAREST).save(
        out / "field.png", optimize=True)

    # Corner coordinates from the UTM transform; the parcel is small enough for a linear
    # lat/lon mapping in the browser (photo GPS -> cell).
    res = float(site["res_m"])
    x0, y0 = tr.c + c0 * tr.a, tr.f + r0 * tr.e    # north-up grid: no rotation terms
    x1, y1 = x0 + size * tr.a, y0 + size * tr.e
    nw, se = _utm_to_ll(x0, y0, site), _utm_to_ll(x1, y1, site)
    hls = json.loads((park / "hls_meta.json").read_text()) if (park / "hls_meta.json").exists() else {}
    field = {
        "site": {"name": site["name"], "lat": site["lat"], "lon": site["lon"]},
        "parcel": {"size": size, "res_m": res, "area_ha": round(size * size * res * res / 1e4, 1),
                   "nw": nw, "se": se, "window": [int(r0), int(c0)]},
        "height": np.round(height, 2).ravel().tolist(),
        "ndvi": np.round(nd, 3).ravel().tolist(),
        "pocket": pocket.astype(int).ravel().tolist(),
        "texture": "field.png",
        "sources": {
            "terrain": "NASADEM (SRTM reprocessed), 30 m, resampled to 15 m, 3x3 smoothed",
            "image": f"HLS {hls.get('id', 'v2.0')} ({hls.get('datetime', '')[:10]}), true colour",
            "ndvi": "HLS NDVI, same scene",
            "pocket": f"lowest {POCKET_PCT} % of parcel cells by NASADEM height",
        },
    }
    (out / "field.json").write_text(json.dumps(field, separators=(",", ":")))
    return field


def _utm_to_ll(x: float, y: float, site: dict) -> list[float]:
    """Inverse of the site bbox: the park grid is axis-aligned in UTM and spans bbox_lonlat, so a
    linear map over 3 km is within a few metres of a full projection."""
    left, bottom, right, top = site["bounds"]
    lon0, lat0, lon1, lat1 = site["bbox_lonlat"]
    lon = lon0 + (x - left) / (right - left) * (lon1 - lon0)
    lat = lat0 + (y - bottom) / (top - bottom) * (lat1 - lat0)
    return [round(lat, 6), round(lon, 6)]


def bake_soil(tsoil_json: Path, out: Path) -> dict:
    series = soil.parse_series(load_power_param(tsoil_json, "TSOIL1"))
    years = sorted({d.year for d, _ in series})
    full = [y for y in years if any(d.month == 12 for d, _ in series if d.year == y)]
    summary = soil.soil_summary(series, full, RECENT)
    (out / "soil.json").write_text(json.dumps(summary, separators=(",", ":")))
    return summary


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--park", type=Path, required=True, help="field-shift data/park directory")
    p.add_argument("--tsoil", type=Path, required=True, help="POWER daily JSON with TSOIL1")
    p.add_argument("--out", type=Path, default=ROOT / "web" / "data")
    p.add_argument("--size", type=int, default=40, help="parcel side in 15 m cells")
    p.add_argument("--texture", type=int, default=520, help="texture side in pixels (a multiple of --size)")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    f = bake_field(a.park, a.out, a.size, a.texture)
    s = bake_soil(a.tsoil, a.out)
    (a.out / "risk.json").write_text(json.dumps(risk_matrix(), separators=(",", ":")))
    print("parcel", f["parcel"], "relief m", round(max(f["height"]) - min(f["height"]), 1))
    print("trap 12C mean", s["trap_12C_mean"], "trend d/decade", s["trap_12C_trend_days_per_decade"],
          "+/-", s["trap_12C_trend_95ci_days_per_decade"])


if __name__ == "__main__":
    main()
