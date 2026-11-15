"""Bake the demo field's daily rain and air temperature into web/data/weather.json.

Rain is NASA GPM IMERG (POWER parameter IMERG_PRECTOT, daily total, UTC days). Air temperature is
POWER T2M_MAX and T2M_MIN (MERRA-2). The browser turns these into crop water need, rain over the
season and heavy-rain days on bare soil (web/js/soilwater.js); nothing is precomputed here, so the
demo field and a user's own field go through the same code.

    uv run python -m taupin.weather --power power.json [--imerg imerg.json]

Each input is a POWER daily point JSON. POWER returns IMERG_PRECTOT only with time-standard=UTC;
with the default local solar time every value is the fill value -999.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRST, LAST = date(2001, 1, 1), date(2025, 12, 31)
FILL = -999.0


def params(path: Path) -> tuple[dict, dict]:
    d = json.loads(path.read_text())
    return d.get("properties", {}).get("parameter", d), d.get("geometry", {})


def daily(series: dict, first: date = FIRST, last: date = LAST) -> list[float | None]:
    """One value per day from first to last; fill and missing days become None."""
    out, d = [], first
    while d <= last:
        v = series.get(d.strftime("%Y%m%d"))
        out.append(None if v is None or v <= FILL + 1 else round(float(v), 1))
        d += timedelta(days=1)
    return out


def bake(power: Path, imerg: Path | None = None) -> dict:
    p, geo = params(power)
    rain_src = params(imerg)[0] if imerg else p
    rain = daily(rain_src["IMERG_PRECTOT"])
    if sum(v is not None for v in rain) < 0.9 * len(rain):
        raise ValueError("IMERG_PRECTOT is mostly fill: fetch it with time-standard=UTC")
    lon, lat = geo.get("coordinates", [None, None])[:2]
    return {
        "site": {"lat": lat, "lon": lon},
        "start": FIRST.isoformat(),
        "rain": rain,
        "tmax": daily(p["T2M_MAX"]),
        "tmin": daily(p["T2M_MIN"]),
        "sources": {
            "rain": "NASA GPM IMERG daily precipitation, via NASA POWER (IMERG_PRECTOT, UTC days), mm",
            "tmax": "NASA POWER daily point API, T2M_MAX (MERRA-2), deg C",
            "tmin": "NASA POWER daily point API, T2M_MIN (MERRA-2), deg C",
        },
    }


def main(argv=None) -> None:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--power", type=Path, required=True, help="POWER JSON with T2M_MAX, T2M_MIN")
    a.add_argument("--imerg", type=Path, help="POWER JSON with IMERG_PRECTOT, if not in --power")
    a.add_argument("--out", type=Path, default=ROOT / "web" / "data" / "weather.json")
    o = a.parse_args(argv)
    w = bake(o.power, o.imerg)
    o.out.write_text(json.dumps(w, separators=(",", ":")))
    print(o.out, len(w["rain"]), "days")


if __name__ == "__main__":
    main()
