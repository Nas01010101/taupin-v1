"""Bake steps for the soil and water inputs: daily IMERG and POWER series, SMAP colour decoding
and the SMAP vs GWETROOT comparison."""
import json
import math
from datetime import date
from pathlib import Path

import pytest

from taupin import smap, weather

DATA = Path(__file__).resolve().parents[1] / "web" / "data"


def test_daily_turns_fill_and_gaps_into_none():
    s = {"20200101": 1.24, "20200102": -999.0, "20200104": 0.0}
    assert weather.daily(s, date(2020, 1, 1), date(2020, 1, 4)) == [1.2, None, None, 0.0]


def test_bake_refuses_mostly_fill_imerg(tmp_path):
    days = {d: -999.0 for d in ("20010101", "20010102")}
    p = tmp_path / "p.json"
    p.write_text(json.dumps({"properties": {"parameter": {"IMERG_PRECTOT": days, "T2M_MAX": {}, "T2M_MIN": {}}}}))
    with pytest.raises(ValueError, match="time-standard=UTC"):
        weather.bake(p)


def test_weather_json_shape():
    w = json.loads((DATA / "weather.json").read_text())
    n = (weather.LAST - weather.FIRST).days + 1
    assert w["start"] == weather.FIRST.isoformat()
    assert len(w["rain"]) == len(w["tmax"]) == len(w["tmin"]) == n
    assert sum(v is not None for v in w["rain"]) >= 0.9 * n


def test_colormap_bin_centres():
    xml = ('<entry rgb="10,20,30" value="[0.000,0.003)"/>'
           '<entry rgb="40,50,60" value="[0.600,+INF)"/>')
    assert smap.colormap(xml) == {(10, 20, 30): 0.0015, (40, 50, 60): 0.6}


def test_cell_transparent_exact_and_near():
    cmap = {(10, 20, 30): 0.2}
    assert smap.cell((10, 20, 30, 0), cmap) is None
    assert smap.cell((10, 20, 30, 255), cmap) == 0.2
    assert smap.cell((11, 21, 31, 255), cmap) == 0.2
    assert smap.cell((200, 200, 200, 255), cmap) is None


def _synthetic(years=3, phase=0.0, noise=None):
    out = {}
    for y in range(2016, 2016 + years):
        for m in range(1, 13):
            base = 0.3 + 0.1 * math.sin((m + phase) / 12 * 2 * math.pi)
            out[f"{y}{m:02d}01"] = base + (noise(y, m) if noise else 0)
    return out


def test_compare_recovers_shared_anomalies():
    bump = lambda y, m: 0.05 if (y, m) in {(2017, 7), (2018, 3)} else 0.0
    res = smap.compare(_synthetic(noise=bump), _synthetic(phase=1, noise=bump))
    assert res["months"] == 36
    assert res["anomaly_r"] > 0.95
    assert {d["month"] for d in res["driest"][:1]} <= {f"{y}-{m:02d}" for y in range(2016, 2019) for m in range(1, 13)}


def test_compare_without_overlap_says_why():
    a = {"20160101": 0.3}
    b = {"20200101": 0.5}
    with pytest.raises(ValueError, match="overlap"):
        smap.compare(a, b)


def test_smap_json_shape():
    s = json.loads((DATA / "smap.json").read_text())
    c = s["compare"]
    assert c["months"] >= 100
    assert sorted(c["climatology"]) == [f"{m:02d}" for m in range(1, 13)]
    assert -1 <= c["anomaly_r"] <= 1
    assert all(0 <= v["smap"] <= 1 and 0 <= v["gwetroot"] <= 1 for v in c["climatology"].values())
