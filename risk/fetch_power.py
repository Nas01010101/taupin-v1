"""NASA POWER daily weather for each Labrie 2020 site: previous growing season, winter and trap spring.

Usage: python3 risk/fetch_power.py <cache_dir>   (writes risk/data/power_features.csv)
POWER is a 0.5 x 0.625 degree reanalysis grid (MERRA-2), so neighbouring fields share a cell.
"""
import csv, datetime as dt, json, pathlib, sys, time, urllib.request

HERE = pathlib.Path(__file__).parent
PARAMS = "TSOIL1,GWETROOT,PRECTOTCORR,T2M"
URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters={p}&community=AG"
       "&longitude={lon}&latitude={lat}&start={y0}0401&end={y1}0630&format=JSON")
TRAP_C, RUN = 12.0, 7  # same rule as src/taupin/soil.py: first 7-day run at or above 12 C


def fetch(lat, lon, year, cache):
    f = cache / f"{lat}_{lon}_{year}.json"
    if not f.exists():
        req = urllib.request.Request(URL.format(p=PARAMS, lon=lon, lat=lat, y0=year - 1, y1=year),
                                     headers={"User-Agent": "python-urllib"})
        for attempt in range(4):
            try:
                f.write_bytes(urllib.request.urlopen(req, timeout=90).read()); break
            except Exception as e:  # POWER throttles bursts; back off and retry
                if attempt == 3: raise
                time.sleep(5 * (attempt + 1))
        time.sleep(1)
    return json.loads(f.read_text())["properties"]["parameter"]


def window(series, a, b):
    v = [x for d, x in series.items() if a <= d <= b and x > -900]  # -999 is POWER's missing value
    return v


def features(p, year):
    d = lambda y, m, day: f"{y}{m:02d}{day:02d}"
    ts = p["TSOIL1"]
    spring = [(k, v) for k, v in sorted(ts.items()) if d(year, 3, 1) <= k <= d(year, 6, 30) and v > -900]
    doy = None
    for i in range(len(spring) - RUN + 1):
        if all(v >= TRAP_C for _, v in spring[i:i + RUN]):
            doy = dt.datetime.strptime(spring[i][0], "%Y%m%d").timetuple().tm_yday; break
    mean = lambda v: round(sum(v) / len(v), 3) if v else ""
    return {
        "tsoil_spring_c": mean(window(ts, d(year, 4, 15), d(year, 5, 31))),
        "trap_doy": doy if doy is not None else "",
        "gwet_spring": mean(window(p["GWETROOT"], d(year, 4, 1), d(year, 5, 31))),
        "gwet_prev_summer": mean(window(p["GWETROOT"], d(year - 1, 6, 1), d(year - 1, 8, 31))),
        "precip_prev_mm": round(sum(window(p["PRECTOTCORR"], d(year - 1, 5, 1), d(year - 1, 9, 30))), 1),
        "tsoil_winter_min_c": min(window(ts, d(year - 1, 12, 1), d(year, 3, 31)), default=""),
        "t2m_spring_c": mean(window(p["T2M"], d(year, 4, 15), d(year, 5, 31))),
    }


def main():
    cache = pathlib.Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(HERE / "data/labrie_sites.csv")))
    out = []
    for i, r in enumerate(rows):
        f = features(fetch(r["lat"], r["lon"], int(r["year"]), cache), int(r["year"]))
        out.append({"crop": r["crop"], "year": r["year"], "site": r["site"], **f})
        print(i + 1, len(rows), r["crop"], r["year"], r["site"], f, flush=True)
    with open(HERE / "data/power_features.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)


if __name__ == "__main__":
    main()
