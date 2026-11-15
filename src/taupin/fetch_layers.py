"""Download the field rasters onto the 2 m parcel grid and cache them as GeoTIFFs.

Sources (all open, no login):
  NRCan HRDEM lidar 1 m DTM and DSM (CMM 2023 project), read through windowed COG requests
  NASA HLS v2 (L30 + S30) red/NIR/Fmask, June to August, several scenes per year
  USGS Landsat 8/9 Collection 2 Level-2 surface temperature (lwir11) + QA_PIXEL, April to May
  OpenStreetMap outline of the park (Overpass API, ODbL)
HLS and Landsat come from Microsoft Planetary Computer. Every read is a WarpedVRT window: only
the COG blocks over the 600 m parcel are fetched.

    uv run --extra bake python -m taupin.fetch_layers --work /path/to/cache
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from .grid import PARCEL, Grid

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
HRDEM_ID = "QC-600023_52_CMM_2023-1m"
HRDEM_URL = "https://canelevation-dem.s3.ca-central-1.amazonaws.com/hrdem-lidar/{id}-{kind}.tif"
OVERPASS = "https://overpass-api.de/api/interpreter"
PARK_WAY = 542903996    # OpenStreetMap way: Parc-nature du Bois-de-Liesse (leisure=nature_reserve)
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3")
if os.environ.get("CURL_CA_BUNDLE"):
    GDAL_ENV["GDAL_CURL_CA_BUNDLE"] = GDAL_ENV["CURL_CA_BUNDLE"] = os.environ["CURL_CA_BUNDLE"]
# Landsat C2 L2 surface temperature: DN * 0.00341802 + 149.0 = kelvin (USGS LSDS-1619).
ST_SCALE, ST_OFFSET = 0.00341802, 149.0
# QA_PIXEL bits 0-5: fill, dilated cloud, cirrus, cloud, cloud shadow, snow.
LANDSAT_BAD_BITS = 0b111111
# HLS Fmask bits 1-3: cloud, adjacent to cloud, cloud shadow. 255 = outside the swath.
HLS_BAD_BITS = 0b1110


def warp(href: str, grid: Grid, resampling: Resampling, nodata: float) -> np.ndarray:
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        src_nodata = src.nodata if src.nodata is not None else nodata
        with WarpedVRT(src, crs=grid.crs, transform=grid.transform(), width=grid.size,
                       height=grid.size, resampling=resampling, src_nodata=src_nodata,
                       nodata=nodata) as vrt:
            return vrt.read(1)


def write_tif(path: Path, arr: np.ndarray, grid: Grid, nodata=None) -> None:
    arr = arr if arr.ndim == 3 else arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=grid.size, width=grid.size,
                       count=arr.shape[0], dtype=arr.dtype, crs=grid.crs,
                       transform=grid.transform(), compress="deflate", nodata=nodata) as dst:
        dst.write(arr)


def _catalog():
    import planetary_computer
    import pystac_client
    return pystac_client.Client.open(PC_STAC, modifier=planetary_computer.sign_inplace)


def _bbox_lonlat(grid: Grid) -> list[float]:
    from rasterio.warp import transform_bounds
    return list(transform_bounds(grid.crs, "EPSG:4326", *grid.bounds))


def hrdem(grid: Grid, work: Path) -> dict:
    """DTM and DSM averaged from 1 m to the grid cell. Average, not bilinear: each 2 m cell is
    the mean of the four lidar cells inside it."""
    out = {}
    for kind in ("dtm", "dsm"):
        a = warp(HRDEM_URL.format(id=HRDEM_ID, kind=kind), grid, Resampling.average, -32767.0)
        a = a.astype(np.float32)
        a[a < -1000] = np.nan
        if np.isnan(a).mean() > 0.01:
            raise RuntimeError(f"HRDEM {kind} leaves {np.isnan(a).mean():.1%} of the grid empty")
        write_tif(work / f"hrdem_{kind}.tif", a, grid, nodata=np.nan)
        out[kind] = [float(np.nanmin(a)), float(np.nanmax(a))]
    meta = dict(id=HRDEM_ID, url=HRDEM_URL.format(id=HRDEM_ID, kind="{dtm,dsm}"), range_m=out)
    (work / "hrdem_meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def hls_ndvi(grid: Grid, work: Path, years=range(2019, 2026), per_year: int = 4,
             min_valid: float = 0.95, log=print) -> dict:
    """Up to `per_year` clear June-August HLS scenes per year, NDVI on a 10 m grid (HLS is 30 m;
    the finer grid only avoids double resampling later)."""
    g = grid.coarse(10.0)
    cat, bbox = _catalog(), _bbox_lonlat(grid)
    stack, scenes = [], []
    for y in years:
        items = cat.search(collections=["hls2-l30", "hls2-s30"], bbox=bbox,
                           datetime=f"{y}-06-01/{y}-08-31",
                           query={"eo:cloud_cover": {"lt": 40}}).items()
        kept = 0
        for it in sorted(items, key=lambda i: i.properties["eo:cloud_cover"])[:10]:
            fmask = warp(it.assets["Fmask"].href, g, Resampling.nearest, 255)
            bad = (fmask == 255) | ((fmask & HLS_BAD_BITS) != 0)
            if 1 - bad.mean() < min_valid:
                continue
            nir = "B8A" if it.collection_id == "hls2-s30" else "B05"
            red = warp(it.assets["B04"].href, g, Resampling.bilinear, -9999).astype(np.float32)
            nr = warp(it.assets[nir].href, g, Resampling.bilinear, -9999).astype(np.float32)
            ndvi = (nr - red) / (nr + red + 1e-6)
            ndvi[bad | (red <= -9999) | (nr <= -9999)] = np.nan
            stack.append(ndvi)
            scenes.append(dict(id=it.id, date=it.properties["datetime"][:10],
                               valid=round(float(1 - bad.mean()), 3)))
            kept += 1
            if kept >= per_year:
                break
        log(f"HLS {y}: {kept} scene(s)")
    if not stack:
        raise RuntimeError("no clear HLS scene in the window")
    write_tif(work / "hls_ndvi.tif", np.stack(stack).astype(np.float32), g, nodata=np.nan)
    meta = dict(scenes=scenes, grid_res_m=g.res, years=[min(years), max(years)])
    (work / "hls_meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def landsat_lst(grid: Grid, work: Path, years=range(2016, 2026), min_valid: float = 0.95,
                log=print) -> dict:
    """Clear April-May Landsat 8/9 surface temperature scenes (kelvin) on a 10 m grid. The
    thermal band is 100 m native; USGS distributes it resampled to 30 m."""
    g = grid.coarse(10.0)
    cat, bbox = _catalog(), _bbox_lonlat(grid)
    stack, scenes = [], []
    for y in years:
        items = cat.search(collections=["landsat-c2-l2"], bbox=bbox,
                           datetime=f"{y}-04-01/{y}-05-31",
                           query={"eo:cloud_cover": {"lt": 40},
                                  "platform": {"in": ["landsat-8", "landsat-9"]}}).items()
        for it in sorted(items, key=lambda i: i.properties["eo:cloud_cover"]):
            qa = warp(it.assets["qa_pixel"].href, g, Resampling.nearest, 1)
            bad = (qa & LANDSAT_BAD_BITS) != 0
            if 1 - bad.mean() < min_valid:
                continue
            dn = warp(it.assets["lwir11"].href, g, Resampling.bilinear, 0).astype(np.float32)
            k = dn * ST_SCALE + ST_OFFSET
            k[bad | (dn == 0)] = np.nan
            stack.append(k)
            scenes.append(dict(id=it.id, date=it.properties["datetime"][:10],
                               valid=round(float(1 - bad.mean()), 3)))
        log(f"Landsat {y}: {sum(s['date'].startswith(str(y)) for s in scenes)} scene(s)")
    if not stack:
        raise RuntimeError("no clear April-May Landsat scene")
    write_tif(work / "landsat_lst.tif", np.stack(stack).astype(np.float32), g, nodata=np.nan)
    meta = dict(scenes=scenes, grid_res_m=g.res, years=[min(years), max(years)])
    (work / "landsat_meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def park(grid: Grid, work: Path) -> dict:
    """Park outline as [lon, lat] pairs. Traps and tree crowns stay inside it."""
    import urllib.parse
    import urllib.request
    body = urllib.parse.urlencode({"data": f"[out:json];way({PARK_WAY});out geom;"}).encode()
    req = urllib.request.Request(OVERPASS, data=body, headers={"User-Agent": "taupin-bake"})
    with urllib.request.urlopen(req, timeout=60) as r:
        way = json.load(r)["elements"][0]
    meta = dict(way=PARK_WAY, name=way["tags"]["name"],
                ring=[[pt["lon"], pt["lat"]] for pt in way["geometry"]])
    (work / "park.json").write_text(json.dumps(meta))
    return meta


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", type=Path, required=True, help="cache directory for the GeoTIFFs")
    p.add_argument("--only", choices=["hrdem", "hls", "landsat", "park"], action="append")
    a = p.parse_args(argv)
    a.work.mkdir(parents=True, exist_ok=True)
    steps = {"hrdem": hrdem, "hls": hls_ndvi, "landsat": landsat_lst, "park": park}
    for name in a.only or list(steps):
        meta = steps[name](PARCEL, a.work)
        print(name, json.dumps(meta)[:300])


if __name__ == "__main__":
    main()
