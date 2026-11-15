"""Bake the cached field rasters (`taupin.fetch_layers`) and the IRDA soil map into web layers.

Inputs (--work, from fetch_layers): hrdem_dtm.tif, hrdem_dsm.tif (2 m), hls_ndvi.tif and
landsat_lst.tif (scene stacks on a 10 m grid), hls_meta.json, landsat_meta.json, park.json
(OpenStreetMap park outline; optional). Soil: IRDA
pedological map sheets (shapefiles, NAD83 lon/lat) and the CanSIS soil name and layer tables.
Outputs in web/data/:
  field.json         manifest: site, parcel corners, per layer file, encoding, unit, range,
                     native resolution, source and dates; soil units, zones, treetops, traps
  layers/<key>.bin   one raster per layer, row-major from the north-west cell, quantised to
                     uint8 or uint16 (value = offset + scale * q; q = max is no data)
2 m layers: terrain height, canopy height, hillshade, slope, wetness index, soil unit, zone.
NDVI and spring surface temperature stay on a 30 m grid (20 x 20): finer cells would show
detail the satellites do not have.

    uv run --extra bake python -m taupin.layers --work /Volumes/PortableSSD/scratch/taupin-work/layers \
        --irda /Volumes/PortableSSD/scratch/taupin-work/irda --cansis /Volumes/PortableSSD/scratch/taupin-work/cansis
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from . import terrain, zones
from .grid import PARCEL, Grid

ROOT = Path(__file__).resolve().parents[2]
SITE = {"name": "Bois-de-Liesse, Secteur des Champs (Saint-Laurent, QC)", "lat": 45.5013, "lon": -73.7651}
SAT_RES = 30.0          # HLS native pixel; the Landsat thermal band is coarser still (100 m)
POCKET_PCT = 15         # lowest 15 % of parcel cells by lidar height: the "low wet pocket" of risk.json
N_ZONES = 4
OPEN_FRAC = 0.6
OPEN_NDVI = 0.65        # mean summer NDVI under 0.65 at 30 m here is road, rail or roof
EDGE_M = 15.0           # no trap within 15 m of the parcel edge (Taupin choice; RAP gives none)
DRAINAGE = {"VR": "very rapidly drained", "R": "rapidly drained", "W": "well drained",
            "MW": "moderately well drained", "I": "imperfectly drained", "P": "poorly drained",
            "VP": "very poorly drained"}
PQ41 = "Lajoie and Baril, Les sols des îles de Montréal, Jésus et Bizard (CanSIS soil survey report PQ41)"
# Series the CanSIS Quebec tables do not carry; described from the survey report instead.
SERIES_NOTES = {"DOV": {"name": "Dorval", "texture": "clay loam on calcareous till",
                        "drainage": "fairly well drained (assez bon)", "source": f"{PQ41}, Série Dorval"}}
WATER = {"name": "Water", "texture": "", "drainage": "", "source": "IRDA map unit EAU"}
SRC = {
    "hrdem": "NRCan HRDEM lidar DTM and DSM, project QC-600023_52_CMM_2023, 1 m, averaged to 2 m",
    "hls": "NASA HLS v2 (Landsat 8/9 L30 and Sentinel-2 S30), 30 m",
    "landsat": "USGS Landsat 8/9 Collection 2 Level-2 surface temperature (band 10), 100 m thermal, distributed at 30 m",
    "irda": "IRDA, Cartes pédologiques du Québec, sheets 31H12-101 to 202 (study 41, 1:20 000)",
    "cansis": "AAFC CanSIS soil name and layer tables, Quebec v2r20130705",
    "osm": "OpenStreetMap contributors (ODbL)",
    "rap": "RAP Grandes cultures, Méthode standard de dépistage des vers fil-de-fer (Agri-Réseau doc. 115269, 16 April 2025)",
}


def read_tif(path: Path) -> np.ndarray:
    import rasterio
    with rasterio.open(path) as r:
        return r.read().astype(np.float64)


def block_mean(a: np.ndarray, k: int) -> np.ndarray:
    """Mean of k x k blocks, NaN ignored (a.shape divisible by k)."""
    h, w = a.shape
    return np.nanmean(a.reshape(h // k, k, w // k, k), axis=(1, 3))


def encode(a: np.ndarray, dtype: str = "u1", nodata_mask: np.ndarray | None = None,
           classes: bool = False) -> tuple[bytes, dict]:
    """Quantise to uint8/uint16 over the data range; the top code is no data."""
    top = 255 if dtype == "u1" else 65535
    bad = ~np.isfinite(a) if nodata_mask is None else (nodata_mask | ~np.isfinite(a))
    lo, hi = float(np.min(a[~bad])), float(np.max(a[~bad]))
    scale = (hi - lo) / (top - 1) or 1.0
    if classes:                                    # class ids are stored as they are
        lo, scale = 0.0, 1.0
    q = np.clip(np.round((np.where(bad, lo, a) - lo) / scale), 0, top - 1)
    q[bad] = top
    enc = {"dtype": dtype, "offset": round(lo, 6), "scale": float(f"{scale:.8g}"), "nodata": top}
    return q.astype("<u1" if dtype == "u1" else "<u2").tobytes(), enc


def cansis_tables(dirs: list[Path]) -> tuple[dict, dict]:
    """{soil code: name record} and {soil code: first layer record} from CanSIS .dbf tables."""
    import shapefile
    names, tops = {}, {}
    for d in dirs:
        for f in sorted(d.glob("soil_name_*.dbf")):
            for rec in shapefile.Reader(dbf=open(f, "rb"), encoding="latin1").iterRecords():
                r = rec.as_dict()
                if r["PROVINCE"] == "QC":
                    names.setdefault(r["SOIL_CODE"], r)
        for f in sorted(d.glob("soil_layer_*.dbf")):
            for rec in shapefile.Reader(dbf=open(f, "rb"), encoding="latin1").iterRecords():
                r = rec.as_dict()
                if r["PROVINCE"] == "QC" and r["LAYER_NO"] == 1:
                    tops.setdefault(r["SOIL_CODE"], r)
    return names, tops


def component(code: str, names: dict, tops: dict) -> dict:
    if code == "ZZZ":
        return dict(WATER)
    if code in names:
        n, t = names[code], tops.get(code, {})
        top = []
        if t.get("TCLAY", -9) >= 0:
            top.append(f"{t['TCLAY']} % clay")
        if t.get("ORGCARB", -9) >= 0:
            top.append(f"{t['ORGCARB']} % organic carbon")
        return {"name": n["SOILNAME"].title(), "texture": ("organic" if n["KIND"] == "O" else "mineral")
                + (f", surface layer {t['UDEPTH']}-{t['LDEPTH']} cm: " + ", ".join(top) if top else ""),
                "drainage": DRAINAGE.get(n["DRAINAGE"], n["DRAINAGE"]), "source": f"{SRC['cansis']}, {code}"}
    return dict(SERIES_NOTES.get(code, {"name": code, "texture": "", "drainage": "", "source": SRC["irda"]}))


def soil_map(shps: list[Path], grid: Grid, names: dict, tops: dict) -> tuple[np.ndarray, list[dict]]:
    """Rasterise the IRDA polygons onto the grid: unit index per cell (0 = no polygon) and the
    legend of the units present, each with its components and their share."""
    import shapefile
    from rasterio import features
    from rasterio.warp import transform_bounds, transform_geom
    w, s, e, n = transform_bounds(grid.crs, "EPSG:4269", *grid.bounds)
    units, shapes = {}, []
    for shp in shps:
        for sr in shapefile.Reader(str(shp), encoding="cp1252").iterShapeRecords():
            b = sr.shape.bbox
            if not (b[0] < e and b[2] > w and b[1] < n and b[3] > s):
                continue
            r = sr.record.as_dict()
            sym = r["APP_CART"]
            if sym not in units:
                comps = []
                for i in range(1, 5):
                    code = r[f"CANSIS{i}"]
                    if code:
                        pct = r[f"PCT_SOL{i}"] or "100"
                        comps.append({"symbol": r[f"SOL{i}"], "pct": int(pct), **component(code, names, tops)})
                units[sym] = {"id": len(units) + 1, "symbol": sym, "components": comps}
            shapes.append((transform_geom("EPSG:4269", grid.crs, sr.shape.__geo_interface__), units[sym]["id"]))
    a = features.rasterize(shapes, out_shape=(grid.size, grid.size), transform=grid.transform(),
                           fill=0, dtype="uint8") if shapes else np.zeros((grid.size, grid.size), np.uint8)
    legend = []
    for u in units.values():
        cells = int((a == u["id"]).sum())
        if cells:
            legend.append({**u, "area_ha": round(cells * grid.res ** 2 / 1e4, 2)})
    return a, legend


def park_mask(path: Path, grid: Grid) -> tuple[np.ndarray, dict | None]:
    """Cells inside the park outline written by fetch_layers; every cell when there is none."""
    if not path.exists():
        return np.ones((grid.size, grid.size), bool), None
    from rasterio.features import rasterize
    from rasterio.warp import transform
    meta = json.loads(path.read_text())
    xs, ys = transform("EPSG:4326", grid.crs, *map(list, zip(*meta["ring"])))
    ring = {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}
    m = rasterize([(ring, 1)], out_shape=(grid.size, grid.size), transform=grid.transform()).astype(bool)
    return m, {"name": meta["name"], "area_ha": round(float(m.sum()) * grid.res ** 2 / 1e4, 1),
               "source": f"{SRC['osm']}, way {meta['way']}"}


def lonlat(grid: Grid, rows, cols) -> list[list[float]]:
    from rasterio.warp import transform
    xs, ys = zip(*(grid.center(r, c) for r, c in zip(rows, cols)))
    lon, lat = transform(grid.crs, "EPSG:4326", list(xs), list(ys))
    return [[round(a, 6), round(o, 6)] for a, o in zip(lat, lon)]


def _dates(meta: dict) -> list[str]:
    d = sorted(s["date"] for s in meta["scenes"])
    return [d[0], d[-1]]


def bake_layers(work: Path, out: Path, grid: Grid, soil_shps: list[Path], cansis_dirs: list[Path],
                n_traps: int = zones.RAP_MIN_TRAPS, n_zones: int = N_ZONES) -> dict:
    res, n = grid.res, grid.size
    dtm = read_tif(work / "hrdem_dtm.tif")[0]
    dsm = read_tif(work / "hrdem_dsm.tif")[0]
    chm = np.clip(dsm - dtm, 0, None)
    hs, slope = terrain.hillshade(dtm, res), terrain.slope_deg(dtm, res)
    twi = terrain.wetness_index(dtm, res)

    hls_meta = json.loads((work / "hls_meta.json").read_text())
    ls_meta = json.loads((work / "landsat_meta.json").read_text())
    ndvi10 = np.nanmean(read_tif(work / "hls_ndvi.tif"), axis=0)
    lst = read_tif(work / "landsat_lst.tif")
    # Each scene minus its own parcel mean, then averaged: what stays is where the parcel is
    # warmer or cooler than itself in spring, not how warm a given day was.
    lst_anom10 = np.nanmean(lst - np.nanmean(lst, axis=(1, 2), keepdims=True), axis=0)
    k10 = round(SAT_RES / hls_meta["grid_res_m"])
    ndvi, lst_anom = block_mean(ndvi10, k10), block_mean(lst_anom10, k10)
    up = n // ndvi.shape[0]                       # 30 m cells -> 2 m cells

    names, tops = cansis_tables(cansis_dirs)
    soil, units = soil_map(soil_shps, grid, names, tops)
    water = {u["id"] for u in units if all(c["name"] == "Water" for c in u["components"])}
    # Trappable ground: under tree height, with at least 60 % such cells in the 30 m around it
    # (drops lawns between houses and road verges), green in summer at 30 m (drops pavement),
    # on a mapped soil unit, inside the park and EDGE_M in from the square's edge. Thresholds
    # are Taupin choices.
    park, park_info = park_mask(work / "park.json", grid)
    low = chm < terrain.TREE_MIN_M
    edge = int(EDGE_M / res)
    inside = np.zeros_like(low)
    inside[edge:-edge, edge:-edge] = True
    open_ = (low & (terrain.box_mean(low.astype(float), int(SAT_RES / res) | 1) >= OPEN_FRAC)
             & (np.kron(ndvi, np.ones((up, up))) >= OPEN_NDVI)
             & (soil > 0) & ~np.isin(soil, list(water)) & inside & park)
    feats = {"twi": terrain.box_mean(twi, int(SAT_RES / res) | 1),
             "ndvi": np.kron(ndvi, np.ones((up, up))), "lst": np.kron(lst_anom, np.ones((up, up)))}
    zone = zones.scouting_zones(feats, soil, open_, n_zones)
    traps = zones.place_traps(zone, res, n_traps)
    for t, ll in zip(traps, lonlat(grid, [t["row"] for t in traps], [t["col"] for t in traps])):
        t["lat"], t["lon"] = ll
    zone_info = []
    for z in range(1, n_zones + 1):
        m = zone == z
        su = np.bincount(soil[m], minlength=256)
        dom = next(u["symbol"] for u in units if u["id"] == int(su.argmax()))
        zone_info.append({"id": z, "area_ha": round(float(m.sum()) * res * res / 1e4, 1),
                          "twi": round(float(twi[m].mean()), 1), "ndvi": round(float(feats["ndvi"][m].mean()), 2),
                          "lst": round(float(feats["lst"][m].mean()), 1), "soil": dom,
                          "traps": [t["id"] for t in traps if t["zone"] == z]})

    hls_dates, ls_dates = _dates(hls_meta), _dates(ls_meta)
    lay = out / "layers"
    lay.mkdir(parents=True, exist_ok=True)

    def put(key, arr, dtype, meta, mask=None):
        buf, enc = encode(arr, dtype, mask, meta.get("kind") == "classes")
        (lay / f"{key}.bin").write_bytes(buf)
        v = arr[np.isfinite(arr) if mask is None else ~mask]
        return {"key": key, "file": f"layers/{key}.bin", "size": int(arr.shape[0]), "encoding": enc,
                "range": [round(float(v.min()), 2), round(float(v.max()), 2)], **meta}

    lidar = {"native_res_m": 1.0, "grid_res_m": res, "source": SRC["hrdem"], "dates": ["2023", "2023"]}
    layers = [
        put("height", dtm, "u2", {"name": "Terrain height", "unit": "m above sea level", **lidar}),
        put("canopy", chm, "u1", {"name": "Canopy height", "unit": "m", **lidar,
                                  "note": "lidar DSM minus DTM"}),
        put("hillshade", hs, "u1", {"name": "Hillshade", "unit": "0 to 1", **lidar,
                                    "note": "sun from the north-west at 45 degrees"}),
        put("slope", slope, "u1", {"name": "Slope", "unit": "degrees", **lidar}),
        put("twi", twi, "u1", {"name": "Wetness index", "unit": "ln(m)", **lidar,
                               "note": "ln(a / tan b), Beven and Kirkby 1979; multiple flow directions "
                                       "(Freeman 1991) on the 3 x 3 smoothed lidar DTM; flow from "
                                       "outside the parcel is not counted"}),
        put("ndvi", ndvi, "u1", {"name": "Vegetation (NDVI)", "unit": "NDVI", "native_res_m": SAT_RES,
                                 "grid_res_m": SAT_RES, "source": SRC["hls"], "dates": hls_dates,
                                 "note": f"mean of {len(hls_meta['scenes'])} clear June to August scenes"}),
        put("lst", lst_anom, "u1", {"name": "Spring surface temperature", "unit": "°C from the parcel mean",
                                    "native_res_m": 100.0, "grid_res_m": SAT_RES, "source": SRC["landsat"],
                                    "dates": ls_dates,
                                    "note": f"mean anomaly of {len(ls_meta['scenes'])} clear April and May scenes"}),
        put("soil", soil.astype(float), "u1", {"name": "Soil map unit", "unit": "map unit", "kind": "classes",
                                               "native_res_m": None, "grid_res_m": res, "classes": units,
                                               "source": f"{SRC['irda']}; {SRC['cansis']}; {PQ41}",
                                               "dates": ["1950s survey", "2006 digitised"]}, soil == 0),
        put("zones", zone.astype(float), "u1", {"name": "Scouting zones", "unit": "zone", "kind": "classes",
                                                "native_res_m": SAT_RES, "grid_res_m": res, "classes": zone_info,
                                                "source": "k-means classes of wetness index (30 m mean), NDVI, "
                                                          "spring surface temperature and soil map unit",
                                                "dates": [hls_dates[0][:4], hls_dates[1][:4]],
                                                "note": "classes for spreading traps; not a risk prediction"},
            zone == 0),
    ]
    nw = lonlat(Grid(grid.x0, grid.y_top, res, n), [-0.5], [-0.5])[0]
    se = lonlat(Grid(grid.x0, grid.y_top, res, n), [n - 0.5], [n - 0.5])[0]
    field = {
        "site": SITE,
        "parcel": {"size": n, "res_m": res, "area_ha": round((n * res) ** 2 / 1e4, 1), "nw": nw, "se": se,
                   "crs": grid.crs, "x0": grid.x0, "y_top": grid.y_top},
        "layers": layers,
        "pocket": {"height_max_m": round(float(np.percentile(dtm, POCKET_PCT)), 3),
                   "rule": f"lowest {POCKET_PCT} % of parcel cells by lidar height"},
        # Canopy outside the park is mostly roofs: no crown is drawn there.
        "trees": terrain.treetops(np.where(park, chm, 0.0)),
        "open": {"area_ha": round(float(open_.sum()) * res * res / 1e4, 1),
                 "rule": f"under {terrain.TREE_MIN_M:.0f} m of canopy, at least {OPEN_FRAC:.0%} such cells in the "
                         f"{SAT_RES:.0f} m around, summer NDVI of {OPEN_NDVI} or more, on a mapped soil unit, "
                         f"inside the park, {EDGE_M:.0f} m from the edge of the square (Taupin choices)"},
        **({"park": park_info} if park_info else {}),
        "traps": traps,
        "trap_rules": {"min_traps": zones.RAP_MIN_TRAPS, "spacing_m": zones.RAP_SPACING_M,
                       "min_spacing_here_m": round(zones.min_spacing_m(traps, res)), "source": SRC["rap"]},
        "sources": {
            "terrain": f"{SRC['hrdem']}; hillshade, slope and wetness index computed from the DTM",
            "trees": f"canopy height = lidar DSM minus DTM; a crown is drawn at each 14 m local maximum above "
                     f"{terrain.TREE_MIN_M + 1:.0f} m" + (", inside the park outline" if park_info else ""),
            "ndvi": f"{SRC['hls']}, {hls_dates[0]} to {hls_dates[1]}",
            "lst": f"{SRC['landsat']}, {ls_dates[0]} to {ls_dates[1]}",
            "soil": f"{SRC['irda']}; {SRC['cansis']}; {PQ41}",
            "pocket": f"lowest {POCKET_PCT} % of parcel cells by lidar height",
            "traps": SRC["rap"],
        },
    }
    (out / "field.json").write_text(json.dumps(field, ensure_ascii=False, separators=(",", ":")))
    return field


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", type=Path, required=True, help="fetch_layers cache directory")
    p.add_argument("--irda", type=Path, required=True, help="directory holding IRDA Pedo_*.shp sheets")
    p.add_argument("--cansis", type=Path, required=True, help="directory holding CanSIS soil_*.dbf tables")
    p.add_argument("--out", type=Path, default=ROOT / "web" / "data")
    a = p.parse_args(argv)
    f = bake_layers(a.work, a.out, PARCEL, sorted(a.irda.glob("**/Pedo_*.shp")), [a.cansis])
    size = sum(x.stat().st_size for x in (a.out / "layers").glob("*.bin"))
    print("layers", len(f["layers"]), "bytes", size, "trees", len(f["trees"]), "traps",
          [(t["id"], t["zone"]) for t in f["traps"]], "min spacing m", f["trap_rules"]["min_spacing_here_m"])
    for z in f["layers"][-1]["classes"]:
        print(" zone", z)


if __name__ == "__main__":
    main()
