from datetime import date, timedelta

from taupin import soil


def ramp_series(year, start_c=0.0, per_day=0.2, extra=None):
    """Synthetic daily TSOIL1 rising linearly from 1 Jan; `extra` overrides single days."""
    out, d = {}, date(year, 1, 1)
    while d.year == year:
        v = start_c + per_day * (d - date(year, 1, 1)).days
        out[d.strftime("%Y%m%d")] = (extra or {}).get(d, v)
        d += timedelta(days=1)
    return out


def test_parse_drops_fill_values_and_sorts():
    s = soil.parse_series({"20200102": 3.0, "20200101": -999.0, "20200103": 4.0})
    assert s == [(date(2020, 1, 2), 3.0), (date(2020, 1, 3), 4.0)]


def test_crossing_uses_seven_day_mean():
    series = soil.parse_series(ramp_series(2024))
    # value(d) = 0.2 * day_index; a 7-day mean reaches 12 when the window centre is day 60,
    # so the window ends on day index 63 = 4 Mar 2024 (leap year). Window starts on 1 Mar.
    got = soil.crossing(series, 2024, 12.0)
    days = [(d, v) for d, v in series if d >= date(2024, 3, 1)]
    run = [sum(v for _, v in days[i:i + 7]) / 7 for i in range(len(days) - 6)]
    first = next(i for i, m in enumerate(run) if m >= 12.0)
    assert got == days[first + 6][0]


def test_single_warm_day_does_not_open_window():
    spike = {date(2024, 3, 10): 30.0}
    flat = soil.parse_series(ramp_series(2024, start_c=5.0, per_day=0.0, extra=spike))
    assert soil.crossing(flat, 2024, 12.0) is None


def test_degree_days_accumulate_above_base():
    series = soil.parse_series(ramp_series(2023, start_c=20.5, per_day=0.0))
    # 10 DD per day above 10.5 -> 258 DD reached on the 26th day from 1 Mar.
    assert soil.degree_day_date(series, 2023) == date(2023, 3, 1) + timedelta(days=25)


def test_trend_recovers_known_slope():
    xs = [float(x) for x in range(2000, 2010)]
    slope, ci = soil.linear_trend(xs, [2 * x + 1 for x in xs])
    assert abs(slope - 2) < 1e-9 and ci < 1e-6


def test_summary_shape_and_sources():
    raw = {}
    for y in range(2018, 2026):
        raw.update(ramp_series(y, start_c=-5.0, per_day=0.15 + 0.001 * (y - 2018)))
    s = soil.soil_summary(soil.parse_series(raw), list(range(2018, 2026)), [2024, 2025])
    assert s["years"] == [2018, 2025]
    assert set(s["per_year"]["2020"]) == {"trap_12C", "larvae_8C", "crw_hatch"}
    assert s["larvae_8C_mean_doy"] < s["trap_12C_mean_doy"]
    assert s["daily"]["2025"]["start"] == "2025-03-01" and len(s["daily"]["2025"]["tsoil"]) == 153
    assert "TSOIL1" in s["sources"]["tsoil"] and "115269" in s["sources"]["trap"]
    # Warmer years cross earlier, so the trend is negative.
    assert s["trap_12C_trend_days_per_decade"] < 0


def test_doy_label():
    assert soil.doy_label(134.2) == "14 May"
