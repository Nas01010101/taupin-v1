"""Layer bake on synthetic rasters: a valley running north-south, a tree clump in the north-west,
two soil polygons (west, east) and satellite stacks that differ between the halves."""
import json

import pytest

np = pytest.importorskip("numpy")
rasterio = pytest.importorskip("rasterio")
shapefile = pytest.importorskip("shapefile")
from rasterio.transform import from_origin  # noqa: E402
from rasterio.warp import transform as warp  # noqa: E402

from taupin import layers, terrain, zones  # noqa: E402
from taupin.grid import Grid  # noqa: E402

N, RES = 150, 2.0
GRID = Grid(x0=600000.0, y_top=5040000.0, res=RES, size=N)


def _tif(path, stack, res):
    with rasterio.open(path, "w", driver="GTiff", height=stack.shape[1], width=stack.shape[2],
                       count=stack.shape[0], dtype="float32", crs=GRID.crs,
                       transform=from_origin(GRID.x0, GRID.y_top, res, res), nodata=np.nan) as d:
        d.write(stack.astype("float32"))


def _soil_shp(path):
    """West and east halves as two IRDA-style units, in NAD83 lon/lat like the real sheets."""
    w = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    for f in ["APP_CART", "SOL1", "SOL2", "SOL3", "SOL4", "PCT_SOL1", "PCT_SOL2", "PCT_SOL3", "PCT_SOL4",
              "CANSIS1", "CANSIS2", "CANSIS3", "CANSIS4"]:
        w.field(f, "C", 20)
    x_mid, (x0, y0, x1, y1) = GRID.x0 + N, GRID.bounds
    for (a, b), rec in [((x0 - 10, x_mid), ["Do", "Do", "", "", "", "", "", "", "", "DOV", "", "", ""]),
                        ((x_mid, x1 + 10), ["Mk+Au", "Mk", "Au", "", "", "60", "40", "", "", "TNH", "ALL", "", ""])]:
        xs, ys = [a, b, b, a, a], [y1 + 10, y1 + 10, y0 - 10, y0 - 10, y1 + 10]
        lon, lat = warp(GRID.crs, "EPSG:4269", xs, ys)
        w.poly([list(zip(lon, lat))])
        w.record(*rec)
    w.close()


@pytest.fixture(scope="module")
def baked(tmp_path_factory):
    work = tmp_path_factory.mktemp("work")
    cols = np.arange(N)
    dtm = np.tile(20.0 + 0.05 * np.abs(cols - N // 2), (N, 1)) + np.linspace(1.0, 0.0, N)[:, None]
    dsm = dtm.copy()
    dsm[10:30, 10:30] += 12.0                      # tree clump, 40 x 40 m
    dsm[18, 18] += 3.0                             # its top
    _tif(work / "hrdem_dtm.tif", dtm[None], RES)
    _tif(work / "hrdem_dsm.tif", dsm[None], RES)
    n10 = N * RES / 10
    half = np.where(np.arange(int(n10)) < n10 / 2, 0.8, 0.6)
    _tif(work / "hls_ndvi.tif", np.tile(half, (3, int(n10), 1)), 10.0)
    lst = 290.0 + np.arange(4)[:, None, None] + np.tile(np.where(half > 0.7, 0.0, 2.0), (4, int(n10), 1))
    _tif(work / "landsat_lst.tif", lst, 10.0)
    for name, n in [("hls_meta.json", 3), ("landsat_meta.json", 4)]:
        scenes = [{"id": f"s{i}", "date": f"202{i}-06-01", "valid": 1.0} for i in range(n)]
        (work / name).write_text(json.dumps({"grid_res_m": 10, "scenes": scenes}))
    _soil_shp(work / "Pedo_test")
    out = work / "web"
    field = layers.bake_layers(work, out, GRID, [work / "Pedo_test.shp"], [])
    return field, out, dtm, dsm


def _read(out, lay):
    e = lay["encoding"]
    q = np.frombuffer((out / lay["file"]).read_bytes(), dtype="<" + e["dtype"]).reshape(lay["size"], lay["size"])
    v = e["offset"] + e["scale"] * q.astype(float)
    v[q == e["nodata"]] = np.nan
    return v


def test_manifest_states_native_resolution(baked):
    field, out, _, _ = baked
    lay = {l["key"]: l for l in field["layers"]}
    assert lay["height"]["native_res_m"] == 1.0 and lay["height"]["size"] == N
    assert lay["ndvi"]["native_res_m"] == 30.0 and lay["ndvi"]["size"] == N * RES / 30
    assert lay["lst"]["native_res_m"] == 100.0 and lay["lst"]["grid_res_m"] == 30.0
    for l in field["layers"]:
        assert {"name", "unit", "range", "source", "dates"} <= set(l)
        n = l["size"]
        assert (out / l["file"]).stat().st_size == n * n * (2 if l["encoding"]["dtype"] == "u2" else 1)
    assert lay["ndvi"]["dates"] == ["2020-06-01", "2022-06-01"]


def test_layers_roundtrip_and_shape(baked):
    field, out, dtm, dsm = baked
    lay = {l["key"]: l for l in field["layers"]}
    h = _read(out, lay["height"])
    assert np.abs(h - dtm).max() < 0.01                       # uint16 keeps centimetres
    assert abs(_read(out, lay["canopy"])[20, 20] - 12.0) < 0.1
    twi = _read(out, lay["twi"])
    assert twi[60:140, N // 2].mean() > twi[60:140, 10].mean() + 1   # the valley floor is wetter
    ndvi = _read(out, lay["ndvi"])
    assert ndvi[0, 0] == pytest.approx(0.8, abs=0.01) and ndvi[0, -1] == pytest.approx(0.6, abs=0.01)
    lst = _read(out, lay["lst"])                                # anomaly: per-scene offsets cancel
    assert lst[0, -1] - lst[0, 0] == pytest.approx(2.0, abs=0.05) and abs(np.nanmean(lst)) < 0.05


def test_soil_units_and_legend(baked):
    field, out, _, _ = baked
    soil = next(l for l in field["layers"] if l["key"] == "soil")
    a = _read(out, soil)
    units = {u["id"]: u for u in soil["classes"]}
    assert units[a[75, 5]]["symbol"] == "Do" and units[a[75, N - 5]]["symbol"] == "Mk+Au"
    mk = units[a[75, N - 5]]["components"]
    assert [c["pct"] for c in mk] == [60, 40]
    assert units[a[75, 5]]["components"][0]["name"] == "Dorval"      # from the survey report notes


def test_trees_and_traps(baked):
    field, _, _, _ = baked
    assert [18, 18, 15.0] in field["trees"]
    traps = field["traps"]
    assert [t["id"] for t in traps] == list("ABCDEFGHIJ")
    assert zones.min_spacing_m(traps, RES) >= zones.RAP_SPACING_M
    edge = layers.EDGE_M / RES
    for t in traps:
        assert edge <= t["row"] < N - edge and edge <= t["col"] < N - edge
        assert not (10 <= t["row"] < 30 and 10 <= t["col"] < 30)  # never under the trees
        x, y = GRID.center(t["row"], t["col"])
        lon, lat = warp(GRID.crs, "EPSG:4326", [x], [y])
        assert (t["lat"], t["lon"]) == pytest.approx((lat[0], lon[0]), abs=1e-6)
    z = next(l for l in field["layers"] if l["key"] == "zones")
    assert "not a risk prediction" in z["note"]
    assert sum(len(c["traps"]) for c in z["classes"]) == 10


def test_hillshade_faces_the_north_west_sun():
    z = np.tile(np.arange(20.0), (20, 1))           # rises to the east, so it faces west
    assert terrain.hillshade(z, 1.0).mean() > terrain.hillshade(z[:, ::-1], 1.0).mean()


def test_allocate_and_depth():
    assert zones.allocate({1: 100, 2: 300}, 10) == {1: 3, 2: 7}
    assert sum(zones.allocate({1: 1, 2: 1, 3: 1000}, 10).values()) == 10
    with pytest.raises(ValueError):
        zones.allocate({1: 1, 2: 1}, 1)
    m = np.zeros((9, 9), bool)
    m[1:8, 1:8] = True
    d = zones.depth(m)
    assert d[4, 4] == 4 and d[1, 1] == 1 and d[0, 0] == 0


def test_encode_marks_nodata():
    a = np.array([[0.0, 1.0], [np.nan, 0.5]])
    buf, enc = layers.encode(a)
    q = np.frombuffer(buf, np.uint8)
    assert q[2] == enc["nodata"] == 255 and q[0] == 0 and q[1] == 254
    buf, enc = layers.encode(np.array([[1.0, 3.0]]), classes=True)
    assert list(np.frombuffer(buf, np.uint8)) == [1, 3] and (enc["offset"], enc["scale"]) == (0.0, 1.0)


def test_park_mask_keeps_cells_inside_the_outline(tmp_path):
    every, info = layers.park_mask(tmp_path / "park.json", GRID)
    assert every.all() and info is None                       # no outline: nothing is masked
    x0, y0, x1, y1 = GRID.bounds
    xs, ys = [x0, x1, x1, x0, x0], [y1, y1, (y0 + y1) / 2, (y0 + y1) / 2, y1]   # the north half
    lon, lat = warp(GRID.crs, "EPSG:4326", xs, ys)
    (tmp_path / "park.json").write_text(json.dumps({"way": 1, "name": "Test park", "ring": list(zip(lon, lat))}))
    m, info = layers.park_mask(tmp_path / "park.json", GRID)
    assert m[: N // 2 - 1].all() and not m[N // 2 + 1:].any()
    assert info["area_ha"] == pytest.approx(N * RES * N * RES / 2e4, abs=0.1) and "way 1" in info["source"]


def test_open_ground_area_is_reported(baked):
    field = baked[0]
    zone_ha = sum(c["area_ha"] for c in field["layers"][-1]["classes"])
    assert field["open"]["area_ha"] == pytest.approx(zone_ha, abs=0.2) and "park" not in field
