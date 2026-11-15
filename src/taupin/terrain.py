"""Terrain layers from a lidar DTM and DSM on one grid: hillshade, slope, topographic wetness
index, canopy height and treetops. numpy only, sized for the 300 x 300 parcel grid.
"""
from __future__ import annotations

import heapq

import numpy as np

# 8 neighbours as (row step, col step); diagonal distance is sqrt(2) cells.
NBRS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
# Freeman (1991) multiple-flow-direction exponent: flow splits over all lower neighbours in
# proportion to slope^1.1, which spreads catchment area over hollows instead of single D8 lines.
MFD_P = 1.1
# Flat cells would give ln(a / 0) = inf; flooring tan(slope) keeps them finite and highest.
TAN_MIN = 0.001
TREE_MIN_M = 2.0       # canopy above 2 m counts as tree or shrub (Taupin choice, not a source)
TOP_WINDOW = 7         # treetop = highest canopy cell in a 7 x 7 window (14 m at 2 m cells)


def gradients(z: np.ndarray, res: float) -> tuple[np.ndarray, np.ndarray]:
    """dz/dx (east) and dz/dy (north) for a north-up grid (row 0 is the north edge)."""
    dzdr, dzdc = np.gradient(z, res)
    return dzdc, -dzdr


def slope_deg(z: np.ndarray, res: float) -> np.ndarray:
    gx, gy = gradients(z, res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def hillshade(z: np.ndarray, res: float, azimuth: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    """Cosine of the angle between the surface normal and a sun at (azimuth, altitude), 0 to 1.
    Default sun from the north-west at 45 degrees, the cartographic convention."""
    gx, gy = gradients(z, res)
    az, zen = np.radians(azimuth), np.radians(90.0 - altitude)
    lx, ly, lz = np.sin(zen) * np.sin(az), np.sin(zen) * np.cos(az), np.cos(zen)
    hs = (-gx * lx - gy * ly + lz) / np.sqrt(1 + gx * gx + gy * gy)
    return np.clip(hs, 0.0, 1.0)


def fill_depressions(z: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    """Priority-flood fill from the grid edge (Barnes et al. 2014, +epsilon variant): every cell
    ends up with a strictly downhill path to the edge, so lidar pits and flats still drain."""
    h, w = z.shape
    out = z.astype(np.float64).copy()
    done = np.zeros(z.shape, bool)
    heap = []
    for r in range(h):
        for c in (0, w - 1):
            heap.append((out[r, c], r, c)); done[r, c] = True
    for c in range(1, w - 1):
        for r in (0, h - 1):
            heap.append((out[r, c], r, c)); done[r, c] = True
    heapq.heapify(heap)
    while heap:
        zc, r, c = heapq.heappop(heap)
        for dr, dc in NBRS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not done[nr, nc]:
                done[nr, nc] = True
                out[nr, nc] = max(out[nr, nc], zc + eps)
                heapq.heappush(heap, (out[nr, nc], nr, nc))
    return out


def mfd_accumulation(z: np.ndarray, res: float) -> np.ndarray:
    """Upslope contributing area (m^2) per cell with Freeman multiple flow directions on a
    depression-filled surface. Area from outside the grid is unknown and not counted."""
    h, w = z.shape
    pad = np.pad(z, 1, mode="edge")
    wts = np.zeros((8, h, w))
    for k, (dr, dc) in enumerate(NBRS):
        drop = (z - pad[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]) / (res * np.hypot(dr, dc))
        wts[k] = np.where(drop > 0, drop, 0.0) ** MFD_P
    # Edge cells must not send flow off the grid into padded copies of themselves.
    wts[:, 0, :][[0, 1, 2]] = 0; wts[:, -1, :][[5, 6, 7]] = 0
    wts[:, :, 0][[0, 3, 5]] = 0; wts[:, :, -1][[2, 4, 7]] = 0
    tot = wts.sum(0)
    wts = np.divide(wts, tot, out=np.zeros_like(wts), where=tot > 0)
    acc = np.full(h * w, res * res)
    flat_w = wts.reshape(8, -1)
    offs = [dr * w + dc for dr, dc in NBRS]
    for i in np.argsort(-z, axis=None, kind="stable"):
        a = acc[i]
        for k in range(8):
            f = flat_w[k, i]
            if f:
                acc[i + offs[k]] += a * f
    return acc.reshape(h, w)


def box_mean(a: np.ndarray, k: int) -> np.ndarray:
    """k x k moving mean with edge padding (k odd)."""
    p = k // 2
    win = np.lib.stride_tricks.sliding_window_view(np.pad(a, p, mode="edge"), (k, k))
    return win.mean(axis=(2, 3))


def wetness_index(dtm: np.ndarray, res: float) -> np.ndarray:
    """Topographic wetness index ln(a / tan b) (Beven and Kirkby 1979): a = specific catchment
    area (contributing area per metre of contour, m), b = local slope. The DTM is smoothed 3 x 3
    first: at 2 m, single-cell lidar noise otherwise breaks flow lines."""
    z = box_mean(dtm.astype(np.float64), 3)
    acc = mfd_accumulation(fill_depressions(z), res)
    gx, gy = gradients(z, res)
    return np.log(acc / res / np.maximum(np.hypot(gx, gy), TAN_MIN))


def treetops(chm: np.ndarray, min_h: float = TREE_MIN_M + 1.0, window: int = TOP_WINDOW) -> list[list[float]]:
    """[row, col, height m] of local canopy maxima at least `min_h` tall: one crown per window."""
    p = window // 2
    win = np.lib.stride_tricks.sliding_window_view(np.pad(chm, p, constant_values=-1.0), (window, window))
    peak = (chm >= win.max(axis=(2, 3))) & (chm >= min_h)
    rows, cols = np.nonzero(peak)
    return [[int(r), int(c), round(float(chm[r, c]), 1)] for r, c in zip(rows, cols)]
