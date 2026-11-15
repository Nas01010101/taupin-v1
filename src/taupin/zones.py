"""Scouting zones and bait-trap points.

Zones are k-means classes of the field's own layers (wetness index, NDVI, spring surface
temperature, soil map unit). They group cells that look alike so the traps cover the field's
variability. They are not risk predictions: the field risk model gives one rank per field.

Trap rules from the RAP bait-trap protocol (Agri-Réseau doc. 115269, 16 April 2025, p. 2-3):
at least 10 traps per field, spread evenly, about 25 m apart, flags lettered A to J (figure 1),
GPS of each trap in decimal degrees. The protocol says the count may vary with field area but
gives no number per hectare, and gives no rule for splitting traps between zones; here the
10-trap minimum is split in proportion to zone area, at least one per zone.
"""
from __future__ import annotations

import numpy as np

RAP_MIN_TRAPS = 10
RAP_SPACING_M = 25.0
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def kmeans(x: np.ndarray, k: int, iters: int = 60, seed: int = 0) -> np.ndarray:
    """Labels 0..k-1 for the rows of x. k-means++ start with a fixed seed: the same bake gives
    the same zones."""
    rng = np.random.default_rng(seed)
    cent = [x[rng.integers(len(x))]]
    for _ in range(1, k):
        d = np.min([((x - c) ** 2).sum(1) for c in cent], axis=0)
        cent.append(x[rng.choice(len(x), p=d / d.sum())])
    cent = np.array(cent)
    lab = np.zeros(len(x), int)
    for _ in range(iters):
        new = np.argmin(((x[:, None, :] - cent[None]) ** 2).sum(2), axis=1)
        if _ and (new == lab).all():
            break
        lab = new
        cent = np.array([x[lab == j].mean(0) if (lab == j).any() else cent[j] for j in range(k)])
    return lab


def scouting_zones(features: dict[str, np.ndarray], soil: np.ndarray, mask: np.ndarray,
                   k: int) -> np.ndarray:
    """Zone id per cell, 1..k, 0 outside `mask`. Continuous features are standardised over the
    masked cells; the soil unit enters one-hot, so a soil boundary weighs about as much as a
    two-standard-deviation change in one layer. Zones are numbered by rising mean of the first
    feature (the wetness index), so zone 1 is the driest-ranked."""
    cols = []
    for a in features.values():
        v = a[mask]
        cols.append((v - v.mean()) / (v.std() or 1.0))
    for u in np.unique(soil[mask]):
        cols.append((soil[mask] == u).astype(float) * np.sqrt(2.0))
    lab = kmeans(np.column_stack(cols), k)
    first = next(iter(features.values()))[mask]
    order = np.argsort([first[lab == j].mean() if (lab == j).any() else np.inf for j in range(k)])
    rank = np.empty(k, int)
    rank[order] = np.arange(1, k + 1)
    out = np.zeros(mask.shape, np.uint8)
    out[mask] = rank[lab]
    return out


def allocate(areas: dict[int, int], n: int) -> dict[int, int]:
    """n traps over zones in proportion to area (largest remainder), at least one per zone."""
    zs = sorted(areas)
    if n < len(zs):
        raise ValueError(f"{n} traps cannot cover {len(zs)} zones")
    out = {z: 1 for z in zs}
    left = n - len(zs)
    total = sum(areas.values())
    quota = {z: left * areas[z] / total for z in zs}
    for z in zs:
        out[z] += int(quota[z])
    rem = n - sum(out.values())
    for z in sorted(zs, key=lambda z: quota[z] - int(quota[z]), reverse=True)[:rem]:
        out[z] += 1
    return out


def depth(mask: np.ndarray, cap: int = 15) -> np.ndarray:
    """Cells from the mask edge (3 x 3 erosions survived, up to `cap`): high in the heart of a
    patch, 0 on its rim. A trap there samples the zone, not a road verge or a tree line."""
    out = np.zeros(mask.shape, np.int32)
    cur = mask.copy()
    for _ in range(cap):
        out += cur
        win = np.lib.stride_tricks.sliding_window_view(np.pad(cur, 1), (3, 3))
        cur = win.all(axis=(2, 3))
        if not cur.any():
            break
    return out


def place_traps(zones: np.ndarray, res: float, n: int = RAP_MIN_TRAPS,
                spacing_m: float = RAP_SPACING_M) -> list[dict]:
    """Trap cells: per zone, the deepest cells of the zone's patches, each at least `spacing_m`
    from the traps already placed. Lettered along a nearest-neighbour walk from the north-west
    trap, the order a scout would flag them."""
    ids = [int(z) for z in np.unique(zones) if z]
    alloc = allocate({z: int((zones == z).sum()) for z in ids}, n)
    deep = {z: depth(zones == z) for z in ids}
    chosen: list[tuple[int, int, int]] = []

    def best(z):
        rc = np.argwhere(deep[z] > 0)
        score = deep[z][rc[:, 0], rc[:, 1]].astype(float)
        if chosen:
            pts = np.array([(r, c) for r, c, _ in chosen])
            d = np.sqrt(((rc[:, None, :] - pts[None]) ** 2).sum(2)).min(1) * res
            score[d < spacing_m] = -1
        i = int(np.argmax(score))
        return (int(rc[i, 0]), int(rc[i, 1])) if score[i] >= 0 else None

    for z in sorted(ids, key=lambda z: -alloc[z]):
        for _ in range(alloc[z]):
            # A zone with no room left 25 m from the other traps hands the trap to the
            # largest zone that still has room, so the field keeps its 10 traps.
            for zz in [z] + sorted(ids, key=lambda q: -alloc[q]):
                rc = best(zz)
                if rc:
                    chosen.append((*rc, zz))
                    break
            else:
                raise ValueError(f"no cell {spacing_m} m from the other traps for trap {len(chosen) + 1}")
    # Nearest-neighbour walk from the trap closest to the north-west corner.
    left = sorted(chosen, key=lambda t: t[0] + t[1])
    walk = [left.pop(0)]
    while left:
        r0, c0, _ = walk[-1]
        left.sort(key=lambda t: (t[0] - r0) ** 2 + (t[1] - c0) ** 2)
        walk.append(left.pop(0))
    return [{"id": LETTERS[i], "row": r, "col": c, "zone": z} for i, (r, c, z) in enumerate(walk)]


def min_spacing_m(traps: list[dict], res: float) -> float:
    pts = np.array([(t["row"], t["col"]) for t in traps], float)
    d = np.sqrt(((pts[:, None] - pts[None]) ** 2).sum(2)) * res
    return float(d[np.triu_indices(len(pts), 1)].min())
