"""Read bar heights (wireworms per bait trap, most abundant sampling date) from Labrie et al. 2020
Figs 1 and 3A-B. Output: one row per crop, year, site with the untreated and treated plot means.

Check against the paper's text: 5 soybean fields at or above 1 per trap and 2 corn fields at or above
3 per trap, both reproduced. Corn fields at or above 1 per trap: 6 here, 5 of 68 in the paper; one
field sits on the threshold (1 px is about 0.04 wireworm)."""
import csv, sys, numpy as np
from PIL import Image

FIG = sys.argv[1]
PANELS = [  # file, crop, year, x_axis, x_right, y_top, y_zero, y_bottom, y tick values (bottom up), sites
    ("g001.png", "Corn", 2012, 97, 1796, 236, 487, 498, [0, 2.5, 5, 7.5], [101,102,103,104,105,106,107,108,109,110,112,114]),
    ("g001.png", "Corn", 2013, 97, 1796, 640, 891, 902, [0, 2.5, 5, 7.5], [201,202,203,204,205,206,207,208,209,211,212,213,214]),
    ("g001.png", "Corn", 2014, 97, 1796, 1044, 1295, 1306, [0, 2.5, 5, 7.5], [1,3,5,7,8,10,11,12,13,14,15,16,19,20,21,22,24,25,28]),
    ("g001.png", "Corn", 2015, 97, 1796, 1437, 1688, 1699, [0, 2.5, 5, 7.5], [50,51,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,70,71,72,73,75,76,77]),
    ("g003.png", "Soybean", 2015, 107, 882, 201, 568, 585, [0, 1, 2, 3], [101,102,104,106,107,108]),
    ("g003.png", "Soybean", 2016, 1022, 1796, 201, 568, 585, [0, 1, 2], [210,211,212,213,214,215,216,217]),
]

def clusters(idx):
    out, cur = [], [idx[0]]
    for i in idx[1:]:
        if i - cur[-1] <= 2: cur.append(i)
        else: out.append(sum(cur) / len(cur)); cur = [i]
    out.append(sum(cur) / len(cur)); return out

rows, imgs = [], {}
for f, crop, year, xa, xr, yt, y0, yb, yvals, sites in PANELS:
    a = imgs.setdefault(f, np.asarray(Image.open(f"{FIG}/{f}").convert("L")).astype(int))
    # y ticks: short dark marks just left of the axis line
    strip = (a[yt:yb, xa - 9:xa - 3] < 110).sum(axis=1)
    yt_px = sorted((c + yt for c in clusters([i for i, v in enumerate(strip) if v >= 4])), reverse=True)
    assert len(yt_px) == len(yvals), (f, year, yt_px)
    ppu = np.polyfit(yvals, yt_px, 1)  # px = slope * value + intercept
    zero_px = ppu[1]
    # x ticks: short dark marks just below the bottom border
    strip = (a[yb + 3:yb + 9, xa + 3:xr - 3] < 110).sum(axis=0)
    xt_px = [c + xa + 3 for c in clusters([i for i, v in enumerate(strip) if v >= 4])]
    assert len(xt_px) == len(sites), (f, year, len(xt_px), len(sites))
    s = np.median(np.diff(xt_px))
    def bar(lo, hi):
        hs = []
        for x in range(int(round(lo)), int(round(hi)) + 1):
            y = int(round(zero_px)) + 1
            while y > yt and a[y - 1, x] < 235: y -= 1  # topmost non-white row of the column
            hs.append(y)
        top = float(np.median(hs))  # median drops the thin error-bar line
        return max(0.0, (top + 1 - zero_px) / ppu[0])  # the outline is 3 px, its centre is the value
    for site, xc in zip(sites, xt_px):
        u, t = bar(xc - 0.21 * s, xc - 0.04 * s), bar(xc + 0.04 * s, xc + 0.21 * s)
        rows.append(dict(crop=crop, year=year, site=site, untreated=round(u, 2), treated=round(t, 2), mean=round((u + t) / 2, 2)))
    print(f, crop, year, "px/unit", round(-ppu[0], 2), "zero", round(zero_px, 1), "spacing", s, file=sys.stderr)

w = csv.DictWriter(sys.stdout, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
