"""Bait-trap window and larval activity dates from NASA POWER daily soil temperature (TSOIL1).

TSOIL1 is the MERRA-2 top soil layer (0-10 cm) served by POWER at ~0.5 degree resolution.
The RAP bait-trap protocol places traps when 10 cm soil reaches 12 C; wireworm larvae move up
to feed near the surface from about 8 C. A single warm day in April does not open the window,
so a threshold counts as reached on the last day of the first 7-day run whose mean is at or
above it (same rule as the wireworm-risk-twin figures).
Standard library only, so the app and tests run without numpy.
"""
from __future__ import annotations

from datetime import date, timedelta

from .engine import SRC as ENGINE_SRC

TRAP_C = 12.0     # RAP bait-trap window (Agri-Réseau doc. 115269)
LARVAE_C = 8.0    # larvae near the surface and feeding
CRW_BASE_C, CRW_DD = 10.5, 258.0   # western corn rootworm egg hatch, soil degree-days from 1 Mar
SRC = {
    "POWER": "NASA POWER daily API, TSOIL1 (MERRA-2 soil layer 1, 0-10 cm), ~0.5 deg grid",
    "RAP": ENGINE_SRC["RAP"],
    "CRW": "Western corn rootworm egg hatch: 258 soil degree-days above 10.5 C from 1 Mar",
}
FILL = -999.0


def parse_series(param: dict) -> list[tuple[date, float]]:
    """POWER {"YYYYMMDD": value} -> sorted [(date, value)], dropping fill values."""
    out = []
    for k, v in param.items():
        if v is None or v <= FILL + 1:
            continue
        out.append((date(int(k[:4]), int(k[4:6]), int(k[6:])), float(v)))
    return sorted(out)


def _spring(series, year):
    return [(d, v) for d, v in series if d.year == year and d >= date(year, 3, 1)]


def crossing(series, year: int, thr: float, run: int = 7) -> date | None:
    """Last day of the first `run`-day window after 1 Mar whose mean soil temperature is >= thr."""
    days = _spring(series, year)
    for i in range(len(days) - run + 1):
        if sum(v for _, v in days[i:i + run]) / run >= thr:
            return days[i + run - 1][0]
    return None


def degree_day_date(series, year: int, base: float = CRW_BASE_C, need: float = CRW_DD) -> date | None:
    """First day after 1 Mar when soil degree-days above `base` reach `need`."""
    acc = 0.0
    for d, v in _spring(series, year):
        acc += max(0.0, v - base)
        if acc >= need:
            return d
    return None


def linear_trend(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Least-squares slope and its 95 % half-width (1.96 standard errors)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    resid = [y - (my + slope * (x - mx)) for x, y in zip(xs, ys)]
    se = (sum(r * r for r in resid) / (n - 2) / sxx) ** 0.5 if n > 2 else 0.0
    return slope, 1.96 * se


def doy(d: date) -> int:
    return d.timetuple().tm_yday


def doy_label(day_of_year: float) -> str:
    """Day of year -> 'DD Mon' in a non-leap year."""
    return (date(2001, 1, 1) + timedelta(days=round(day_of_year) - 1)).strftime("%d %b")


def soil_summary(series, years: list[int], recent: list[int]) -> dict:
    """Per-year window dates, the trend of the 12 C date, and Mar-Jul daily values for `recent`."""
    rows = {}
    for y in years:
        t12, t8, crw = crossing(series, y, TRAP_C), crossing(series, y, LARVAE_C), degree_day_date(series, y)
        if t12 is None or t8 is None:
            continue
        rows[y] = {"trap_12C": t12.isoformat(), "larvae_8C": t8.isoformat(),
                   "crw_hatch": crw.isoformat() if crw else None}
    ys = sorted(rows)
    t12 = [doy(date.fromisoformat(rows[y]["trap_12C"])) for y in ys]
    t8 = [doy(date.fromisoformat(rows[y]["larvae_8C"])) for y in ys]
    slope, ci = linear_trend([float(y) for y in ys], [float(v) for v in t12])
    mean12, mean8 = sum(t12) / len(t12), sum(t8) / len(t8)
    daily = {}
    for y in recent:
        pts = [(d, v) for d, v in series if d.year == y and date(y, 3, 1) <= d <= date(y, 7, 31)]
        daily[str(y)] = {"start": pts[0][0].isoformat(), "tsoil": [round(v, 2) for _, v in pts]} if pts else None
    return {
        "years": [ys[0], ys[-1]],
        "thresholds_c": {"trap": TRAP_C, "larvae": LARVAE_C},
        "trap_12C_mean_doy": round(mean12, 1), "trap_12C_mean": doy_label(mean12),
        "larvae_8C_mean_doy": round(mean8, 1), "larvae_8C_mean": doy_label(mean8),
        "trap_12C_trend_days_per_decade": round(10 * slope, 2),
        "trap_12C_trend_95ci_days_per_decade": round(10 * ci, 2),
        "per_year": {str(y): rows[y] for y in ys},
        "daily": daily,
        "sources": {"tsoil": SRC["POWER"], "trap": SRC["RAP"], "crw": SRC["CRW"]},
    }
