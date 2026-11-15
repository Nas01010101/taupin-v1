"""Inputs and ranking cut points for the trained field risk model (web/data/risk_model.json,
copied unchanged from risk/model/risk_model.json).

The model gives a score for a whole field from four inputs. The two weather inputs are read from
NASA POWER daily data exactly as risk/fetch_power.py reads them for the 82 training fields, and
`score` is the formula web/js/fieldrisk.js runs in the browser. The cut points rank a field
against the training fields (thirds of their fitted scores); they are not probabilities.

    python3 -m taupin.fieldrisk --power power.json --out web/data/field_risk.json
Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "web/data/risk_model.json"
SITES = ROOT / "risk/data/labrie_sites.csv"
TRAINING_POWER = ROOT / "risk/data/power_features.csv"
TRAINING_BAIT = ROOT / "risk/data/labrie_bait_digitized.csv"
POWER_URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters="
             "TSOIL1,GWETROOT,PRECTOTCORR,T2M&community=AG&longitude={lon}&latitude={lat}"
             "&start={start}&end={end}&format=JSON")
# Same test as risk/fit.py: the soil layer says sand or sandy loam. Organic soils count as 0.
LIGHT_TEXTURES = ("sand", "sandy loam")


def _window(series: dict, a: str, b: str) -> list[float]:
    # -999 is POWER's missing value
    return [v for d, v in series.items() if a <= d <= b and v > -900]


def power_features(p: dict, year: int) -> dict:
    """gwet_spring: mean GWETROOT 1 Apr-31 May of `year`; tsoil_winter_min_c: lowest TSOIL1
    from 1 Dec of the year before to 31 Mar. None when POWER has no value in the window."""
    gw = _window(p["GWETROOT"], f"{year}0401", f"{year}0531")
    ts = _window(p["TSOIL1"], f"{year - 1}1201", f"{year}0331")
    return {"gwet_spring": round(sum(gw) / len(gw), 3) if gw else None,
            "tsoil_winter_min_c": min(ts) if ts else None}


def is_light(texture: str) -> int:
    return int(texture.strip().lower() in LIGHT_TEXTURES)


def transform(kind: str, x: float) -> float:
    if kind == "log1p":
        return math.log1p(x)
    if kind == "log":
        return math.log(x)
    if kind in ("identity", "0/1"):
        return float(x)
    raise ValueError(f"unknown transform {kind!r}")


def score(model: dict, inputs: dict) -> float:
    """The linear score z = intercept + sum(coef * (transform(x) - mean) / sd)."""
    z = model["intercept"]
    for f in model["features"]:
        z += model["coef"][f["name"]] * (transform(f["transform"], inputs[f["name"]]) - f["mean"]) / f["sd"]
    return z


def first_number(s: str) -> float:
    """The site table writes some forage durations as "> 1" or "5 +"; keep the number, as
    risk/fit.py does."""
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", "."))
    return float(m.group()) if m else 0.0


def training_inputs(sites=SITES, power=TRAINING_POWER, bait=TRAINING_BAIT) -> list[dict]:
    """Model inputs of each field with a bait count (the fields the model was fitted on)."""
    key = lambda r: (r["crop"], r["year"], r["site"])
    weather = {key(r): r for r in csv.DictReader(open(power, encoding="utf-8"))}
    counted = {key(r) for r in csv.DictReader(open(bait, encoding="utf-8"))}
    out = []
    for r in csv.DictReader(open(sites, encoding="utf-8")):
        if key(r) not in counted:
            continue
        w = weather[key(r)]
        out.append({"light_soil": is_light(r["texture"]),
                    "forage_years": first_number(r["forage_years"]),
                    "gwet_spring": float(w["gwet_spring"]),
                    "tsoil_winter_min_c": float(w["tsoil_winter_min_c"])})
    return out


def training_scores(model: dict, rows=None) -> list[float]:
    return [score(model, r) for r in (rows if rows is not None else training_inputs())]


def cutpoints(scores: list[float]) -> list[float]:
    """Scores at one third and two thirds of the sorted list (nearest rank)."""
    s = sorted(scores)
    return [s[math.ceil(len(s) / 3) - 1], s[math.ceil(2 * len(s) / 3) - 1]]


def bake(power: dict, lat: float, lon: float, model: dict) -> dict:
    p = power["properties"]["parameter"]
    first = min(p["TSOIL1"])[:4]
    last = max(p["GWETROOT"])[:8]
    years = {}
    for y in range(int(first) + 1, int(last[:4]) + 1):
        if last < f"{y}0531":
            continue  # spring not complete in the download
        f = power_features(p, y)
        if None not in f.values():
            years[str(y)] = f
    rows = training_inputs()
    scores = training_scores(model, rows)
    return {
        "site": {"lat": lat, "lon": lon},
        "power_cell": power.get("geometry", {}).get("coordinates"),
        "power_url": POWER_URL.format(lat=lat, lon=lon, start="YYYY1201", end="YYYY0531"),
        "per_year": years,
        "rank_cutpoints": [round(c, 4) for c in cutpoints(scores)],
        "rank_basis": f"thirds of the model score over its {len(scores)} training fields",
        # Inputs outside these ranges are extrapolation; the page says so next to the ranking.
        "training_range": {k: [min(r[k] for r in rows), max(r[k] for r in rows)]
                           for k in ("forage_years", "gwet_spring", "tsoil_winter_min_c")},
        "source": "NASA POWER daily point API, community AG (MERRA-2, 0.5 x 0.625 degree)",
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--power", type=Path, required=True, help="POWER daily JSON, 1 Dec to 31 May")
    ap.add_argument("--lat", type=float, default=45.5056)
    ap.add_argument("--lon", type=float, default=-73.7639)
    ap.add_argument("--out", type=Path, default=ROOT / "web/data/field_risk.json")
    a = ap.parse_args(argv)
    out = bake(json.loads(a.power.read_text()), a.lat, a.lon, json.loads(MODEL.read_text()))
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(a.out, list(out["per_year"]), out["rank_cutpoints"])


if __name__ == "__main__":
    main()
