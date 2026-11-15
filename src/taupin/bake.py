"""Bake NASA POWER soil temperature and the risk matrix into small static files for web/.

Input: a POWER daily JSON that carries TSOIL1. The field layers (field.json, layers/) come from
`taupin.layers`.
Outputs in web/data/:
  soil.json    trap window per year, 12 C trend, Mar-Jul daily TSOIL1 for the recent years
  risk.json    4 rotations x 5 years wireworm / corn rootworm levels for two soil zones and two
               evidence scenarios, every line with its source (taupin.engine)
weather.json (GPM IMERG rain, air temperature) and smap.json come from `taupin.weather` and
`taupin.smap`; crops.json and rotations.json are written by hand, a source key per value.

    uv run --extra bake python -m taupin.bake \
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


def bake_soil(tsoil_json: Path, out: Path) -> dict:
    series = soil.parse_series(load_power_param(tsoil_json, "TSOIL1"))
    years = sorted({d.year for d, _ in series})
    full = [y for y in years if any(d.month == 12 for d, _ in series if d.year == y)]
    summary = soil.soil_summary(series, full, RECENT)
    (out / "soil.json").write_text(json.dumps(summary, separators=(",", ":")))
    return summary


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tsoil", type=Path, required=True, help="POWER daily JSON with TSOIL1")
    p.add_argument("--out", type=Path, default=ROOT / "web" / "data")
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    s = bake_soil(a.tsoil, a.out)
    (a.out / "risk.json").write_text(json.dumps(risk_matrix(), separators=(",", ":")))
    print("trap 12C mean", s["trap_12C_mean"], "trend d/decade", s["trap_12C_trend_days_per_decade"],
          "+/-", s["trap_12C_trend_95ci_days_per_decade"])


if __name__ == "__main__":
    main()
