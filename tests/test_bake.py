import json
from pathlib import Path

import pytest

from taupin import bake, engine

WEB_DATA = Path(__file__).resolve().parents[1] / "web" / "data"


def test_risk_matrix_covers_three_rotations_five_years_with_sources():
    m = bake.risk_matrix()
    assert set(m["zones"]) == {"upland", "pocket"}
    for z in m["zones"].values():
        for scen in z["scenarios"].values():
            assert set(scen) == set(engine.ROTATIONS)
            for rows in scen.values():
                assert [r["year"] for r in rows] == list(range(2026, 2031))
                for r in rows:
                    assert r["trace"] and all(t.endswith("]") and "[" in t for t in r["trace"])


def test_trap_scenario_only_raises_first_year_on_upland():
    z = bake.risk_matrix()["zones"]["upland"]["scenarios"]
    base, trap = z["baseline"]["B_corn_soy_wheat"], z["trap_threshold"]["B_corn_soy_wheat"]
    assert base[0]["wireworm"] == "MODERATE" and trap[0]["wireworm"] == "HIGH"
    assert trap[0]["prescription_supportable"] and not base[0]["prescription_supportable"]
    assert base[1:] == trap[1:]


def test_committed_risk_json_matches_engine():
    # The app reads web/data/risk.json; a stale bake would show numbers the engine no longer gives.
    committed = json.loads((WEB_DATA / "risk.json").read_text())
    assert committed == json.loads(json.dumps(bake.risk_matrix()))


def test_committed_soil_json_has_trap_window():
    s = json.loads((WEB_DATA / "soil.json").read_text())
    assert s["years"][0] <= 2000 and s["years"][1] >= 2025
    assert 100 < s["trap_12C_mean_doy"] < 170 and s["larvae_8C_mean_doy"] < s["trap_12C_mean_doy"]


def test_load_power_param_accepts_both_layouts(tmp_path):
    api = tmp_path / "api.json"
    api.write_text(json.dumps({"properties": {"parameter": {"TSOIL1": {"20200101": 1.0}}}}))
    flat = tmp_path / "flat.json"
    flat.write_text(json.dumps({"TSOIL1": {"20200101": 1.0}}))
    assert bake.load_power_param(api, "TSOIL1") == bake.load_power_param(flat, "TSOIL1")
    with pytest.raises(KeyError):
        bake.load_power_param(flat, "T2M")


def test_bake_field_on_synthetic_rasters(tmp_path):
    np = pytest.importorskip("numpy")
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    n, res, left, top = 20, 15.0, 595000.0, 5041000.0
    tr = from_origin(left, top, res, res)
    yy, xx = np.mgrid[0:n, 0:n]
    layers = {"dem": (xx + yy).astype("float32")[None], "ndvi": np.full((1, n, n), 0.6, "float32"),
              "rgb": np.stack([xx / n, yy / n, np.full((n, n), 0.3)]).astype("float32")}
    for name, arr in layers.items():
        with rasterio.open(tmp_path / f"{name}.tif", "w", driver="GTiff", height=n, width=n,
                           count=arr.shape[0], dtype="float32", crs="EPSG:32618", transform=tr) as dst:
            dst.write(arr)
    site = {"name": "test", "lat": 45.5, "lon": -73.7, "res_m": res, "crs": "EPSG:32618",
            "bounds": [left, top - n * res, left + n * res, top],
            "bbox_lonlat": [-73.71, 45.49, -73.69, 45.51]}
    (tmp_path / "site.json").write_text(json.dumps(site))
    out = tmp_path / "out"
    out.mkdir()
    f = bake.bake_field(tmp_path, out, size=8, tex=64)
    assert len(f["height"]) == 64 and len(f["ndvi"]) == 64 and sum(f["pocket"]) >= 1
    assert f["parcel"]["window"] == [6, 6]
    nw, se = f["parcel"]["nw"], f["parcel"]["se"]
    assert nw[0] > se[0] and nw[1] < se[1]
    assert (out / "field.png").exists() and (out / "field.json").exists()
