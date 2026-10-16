"""Per-check support floor / overhead occluder, and automatic height bands."""
import re
import sys

import numpy as np

from quick import LOC, SCENE_IDX
from render import tri_normals
from scene import load

BADMAT = re.compile(r"lightshaft|light ?beam|prototype|trigger|invisible|nodraw|fog", re.I)
EXCLUDE = re.compile(r"decal|sky|tree|grass|bush|fern|plant|cloud|fog|light ?beam|godray|shadow", re.I)


def floor_tris(d):
    T = d["tris"]
    n = tri_normals(T)
    names = d["names"]
    bad = np.array([bool(EXCLUDE.search(str(s))) for s in names])
    m = d["active"] & (n[:, 1] > 0.35) & ~bad[d["obj"]]
    # drop non-solid materials (light shafts, editor prototype/trigger materials, fog)
    from textures import material_texture
    badmat = np.zeros(len(d["matkeys"]), bool)
    for i, k in enumerate(d["matkeys"]):
        r = material_texture(str(k))
        mname = r[4] if r else ""
        badmat[i] = bool(BADMAT.search(mname or ""))
    m &= ~badmat[d["mat"]]
    # drop objects with only a sliver of floor (fence posts, candles, small props)
    area = 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) * np.clip(n[:, 1], 0, 1)
    per_obj = np.bincount(d["obj"], weights=np.where(m, area, 0), minlength=len(names))
    m &= per_obj[d["obj"]] >= 1.5
    return m


def heights_at(T, pts):
    """For each xz point, list of (height) of triangles covering it. Returns list of arrays."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    out = []
    v0 = (c - a)[:, [0, 2]]
    v1 = (b - a)[:, [0, 2]]
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    den = d00 * d11 - d01 * d01
    ok = np.abs(den) > 1e-9
    den = np.where(ok, den, 1)
    for p in pts:
        v2 = p[None, :] - a[:, [0, 2]]
        d02 = (v0 * v2).sum(1); d12 = (v1 * v2).sum(1)
        u = (d11 * d02 - d01 * d12) / den
        v = (d00 * d12 - d01 * d02) / den
        inside = ok & (u >= -1e-4) & (v >= -1e-4) & (u + v <= 1 + 1e-4)
        hs = a[inside, 1] + u[inside] * (c[inside, 1] - a[inside, 1]) + v[inside] * (b[inside, 1] - a[inside, 1])
        out.append(hs)
    return out


def check_profile(code):
    d = load(SCENE_IDX[code])
    m = floor_tris(d)
    T = d["tris"][m]
    locs = [l for l in LOC["locations"] if l["level"] == code and l.get("pos")]
    P = np.array([l["pos"] for l in locs], float)
    hs = heights_at(T, P[:, [0, 2]])
    prof = []
    for l, p, h in zip(locs, P, hs):
        below = h[h <= p[1] + 0.6]
        support = below.max() if len(below) else p[1] - 1.0
        above = h[h > p[1] + 1.6]
        ceil = above.min() if len(above) else np.inf
        prof.append((l, p, float(support), float(ceil)))
    return prof


def auto_bands(prof, pad=0.25, floor_hist=None):
    """Greedy minimal height bands so no check is hidden under a higher floor in its own band.
    Returns cut heights [-inf, c1, ..., inf]. If floor_hist=(bin_edges, area) is given, each cut is moved within
    its feasible range to the height with the least floor area, so cuts avoid slicing through slopes/terrain."""
    items = sorted(((s, c) for _, _, s, c in prof))
    groups, cur, top = [], [], np.inf
    for s, c in items:
        if cur and s >= top:
            groups.append((cur, top))
            cur, top = [], np.inf
        cur.append(s)
        top = min(top, c - pad)
    groups.append((cur, top))
    cuts = [-np.inf]
    for i in range(len(groups) - 1):
        lo = max(groups[i][0]) + 0.3
        hi = min(groups[i][1], min(groups[i + 1][0]))
        cut = hi
        if floor_hist is not None and hi > lo:
            edges, area = floor_hist
            best = None
            for h in np.arange(lo, hi + 1e-6, 0.25):
                j = np.searchsorted(edges, h) - 1
                a = area[max(0, j - 1):j + 2].sum() if 0 <= j < len(area) else 0
                if best is None or a < best[0] - 1e-6:
                    best = (a, h)
            cut = best[1]
        cuts.append(float(cut))
    cuts.append(np.inf)
    return cuts


def floor_histogram(d, sel, bounds, step=0.25):
    T = d["tris"][sel]
    c = T.mean(1)
    m = (c[:, 0] > bounds[0]) & (c[:, 0] < bounds[2]) & (c[:, 2] > bounds[1]) & (c[:, 2] < bounds[3])
    T = T[m]
    n = tri_normals(T)
    area = 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) * np.clip(n[:, 1], 0, 1)
    # spread each triangle's area over its height span
    ylo, yhi = T[:, :, 1].min(1), T[:, :, 1].max(1)
    edges = np.arange(np.floor(ylo.min()) - 1, np.ceil(yhi.max()) + 1.5, step)
    hist = np.zeros(len(edges) - 1)
    for a, l, h in zip(area, ylo, yhi):
        i0, i1 = np.searchsorted(edges, l) - 1, np.searchsorted(edges, h) - 1
        i0, i1 = max(i0, 0), min(max(i1, i0), len(hist) - 1)
        hist[i0:i1 + 1] += a / (i1 - i0 + 1)
    return edges, hist


if __name__ == "__main__":
    for code in (sys.argv[1:] or SCENE_IDX):
        prof = check_profile(code)
        cuts = auto_bands(prof)
        counts = np.histogram([s for _, _, s, _ in prof], [-1e9] + cuts[1:-1] + [1e9])[0]
        print(code, len(prof), [round(c, 1) for c in cuts[1:-1]], counts.tolist())
