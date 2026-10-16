"""Compose an 'exploded' multi-layer map for one DUSK level (HP2-pack style).

Each height band ("layer") is rendered top-down with the level's own textures, cropped to the area its checks
occupy, and the layers are stacked (highest on top) aligned on world X, so the red connector lines that join the
same spot on two layers (stairs, ramps, drops between floors) run vertically.

Returns {check name: (x, y, layer)} in image pixels plus metadata.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

from bands import auto_bands, check_profile, floor_histogram, floor_tris, heights_at
from quick import SCENE_IDX
from render import render_band, stylise
from scene import load

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(ROOT, "level_config.json")
CFG = json.load(open(CFG_PATH)) if os.path.exists(CFG_PATH) else {}
from paths import LOCATIONS_JSON, RAW_PICKUPS_JSON, need  # noqa: E402

RAW = json.load(open(need(RAW_PICKUPS_JSON, "dusk-rando raw_pickups.json")))
LEVELS = {l["code"]: l for l in json.load(open(LOCATIONS_JSON))["levels"]}

MAX_DIM = 2600
FONT = cv2.FONT_HERSHEY_DUPLEX
RED = (235, 30, 30)
TEXT = (235, 225, 200)
HEADER_H = 96


def label(img, text, org, scale=0.8, color=TEXT, thick=1):
    cv2.putText(img, text, org, FONT, scale, (0, 0, 0), thick + 4, cv2.LINE_AA)
    cv2.putText(img, text, org, FONT, scale, color, thick, cv2.LINE_AA)


def band_names(n):
    if n == 1:
        return ["Map"]
    return [f"Layer {i + 1}" + (" (lowest)" if i == 0 else " (highest)" if i == n - 1 else "") for i in range(n)]


def exits_for(code):
    scene = LEVELS[code]["scene"]
    return [np.array(r["pos"], float) for r in RAW if r["scene"] == scene and r["tag"] == "EndButtonTag"]


def compose(code, out_png, verbose=False):
    cfg = CFG.get(code, {})
    d = load(SCENE_IDX[code])
    sel = floor_tris(d)
    prof = check_profile(code)
    P0 = np.array([p for _, p, _, _ in prof])
    fh = floor_histogram(d, sel, (P0[:, 0].min() - 15, P0[:, 2].min() - 15, P0[:, 0].max() + 15, P0[:, 2].max() + 15))
    cuts = ([-np.inf] + cfg["cuts"] + [np.inf]) if "cuts" in cfg else auto_bands(prof, floor_hist=fh)
    nb = len(cuts) - 1
    names = cfg.get("names") or band_names(nb)

    def band(support):
        return max(i for i in range(nb) if support >= cuts[i] or i == 0)

    P = np.array([p for _, p, _, _ in prof])
    band_of = np.array([cfg.get("force", {}).get(l["name"], band(s)) for l, p, s, c in prof])
    margin = cfg.get("margin", 14)
    full = (P[:, 0].min() - margin, P[:, 2].min() - margin, P[:, 0].max() + margin, P[:, 2].max() + margin)
    # per layer: main crop + detached "inset" areas for far-off, small clusters of checks
    from scipy.cluster.hierarchy import fcluster, linkage

    def bbox(Q):
        return (max(full[0], Q[:, 0].min() - margin), max(full[1], Q[:, 2].min() - margin),
                min(full[2], Q[:, 0].max() + margin), min(full[3], Q[:, 2].max() + margin))

    def barea(b):
        return (b[2] - b[0]) * (b[3] - b[1])

    crops, insets = [], []  # insets: (layer, crop)
    for k in range(nb):
        Q = P[band_of == k]
        if len(Q) == 0:
            crops.append(None)
            continue
        if len(Q) == 1:
            crops.append(bbox(Q))
            continue
        cl = fcluster(linkage(Q[:, [0, 2]], "single"), cfg.get("cluster_gap", 60), "distance")
        groups = sorted((Q[cl == i] for i in set(cl)), key=len, reverse=True)
        main = groups[0]
        for g in groups[1:]:
            merged = np.vstack([main, g])
            if barea(bbox(merged)) <= 2.2 * barea(bbox(main)) + 2000 or len(g) > 15:
                main = merged
            else:
                insets.append((k, bbox(g)))
        crops.append(bbox(main))

    # exit buttons -> layer, if they fall inside that layer's panel
    exits = []
    T = d["tris"][sel]
    for e in exits_for(code):
        hs = heights_at(T, e[None, [0, 2]])[0]
        below = hs[hs <= e[1] + 0.6]
        k = band(below.max() if len(below) else e[1] - 1)
        for pi, c in [(k, crops[k])] + [(("i", j), b) for j, (kk, b) in enumerate(insets) if kk == k]:
            if c and c[0] <= e[0] <= c[2] and c[1] <= e[2] <= c[3]:
                exits.append((pi, e))
                break

    # layout: highest layer on top, aligned on world x; too tall -> several columns
    order = [k for k in range(nb - 1, -1, -1) if crops[k] is not None]
    gminx = min(crops[k][0] for k in order)
    gmaxx = max(crops[k][2] for k in order)
    wspan = gmaxx - gminx
    hsum = sum(crops[k][3] - crops[k][1] for k in order)
    ncols = 1
    while ncols < len(order) and hsum / ncols > 2.6 * wspan * ncols:
        ncols += 1
    per = math.ceil(len(order) / ncols)
    columns = [order[i * per:(i + 1) * per] for i in range(ncols)]
    colh = max(sum(crops[k][3] - crops[k][1] for k in col) for col in columns)
    iw = max([b[2] - b[0] for _, b in insets], default=0)
    ih = sum(b[3] - b[1] for _, b in insets)
    ppu = cfg.get("ppu") or min(10.0, MAX_DIM / max(wspan * ncols + iw, colh + 7 * len(order), ih + 7 * len(insets)))

    renders = []
    for k in range(nb):
        img, hb = render_band(d, full, cuts[k], cuts[k + 1], ppu, sel=sel)
        renders.append((stylise(img, hb, ppu), hb))

    # connectors between adjacent layers: lower floor near the cut touching upper floor near the cut
    conns = []
    pairs = [(k, k + 1) for k in range(nb - 1)] + [(k, k + 2) for k in range(nb - 2)]
    for k, j in pairs:
        ha, hb_ = renders[k][1], renders[j][1]
        A = (~np.isnan(ha)) & (ha >= cuts[k + 1] - 1.6)
        B = (~np.isnan(hb_)) & (hb_ <= cuts[j] + 1.6)
        if j == k + 2:  # stairs passing through the middle layer's height range
            mid = renders[k + 1][1]
            A = (~np.isnan(ha)) & (ha >= cuts[k + 1] - 1.6)
            B = B & np.isnan(mid)
        r = max(1, int(ppu * 1.0))
        touch = cv2.dilate(A.astype(np.uint8), np.ones((2 * r + 1, 2 * r + 1), np.uint8)).astype(bool) & B
        n, lab, stats, cent = cv2.connectedComponentsWithStats(touch.astype(np.uint8), 8)
        for jj in range(1, n):
            if stats[jj, cv2.CC_STAT_AREA] < (ppu * 1.0) ** 2:
                continue
            x, y = cent[jj]
            conns.append((k, j, full[0] + x / ppu, full[3] - y / ppu, stats[jj, cv2.CC_STAT_AREA]))
    kept = []
    for k1, k2, wx, wz, a in sorted(conns, key=lambda t: -t[4]):
        if not all(crops[k] and crops[k][0] <= wx <= crops[k][2] and crops[k][1] <= wz <= crops[k][3] for k in (k1, k2)):
            continue
        if any(math.hypot(q[2] - wx, q[3] - wz) < 16 and (q[0] == k1 or q[1] == k2) for q in kept):
            continue
        kept.append((k1, k2, wx, wz, a))
    conns = kept[: cfg.get("max_connectors", 10) * max(1, nb - 1)] + [
        (a, b, x, z, 0) for a, b, x, z in cfg.get("extra_connectors", [])]

    # place panels
    pad, title_h = 24, 38
    placed = {}
    colx = pad
    for col in columns:
        cy = HEADER_H
        for k in col:
            c = crops[k]
            x0 = int((c[0] - full[0]) * ppu); y0 = int((full[3] - c[3]) * ppu)
            x1 = int((c[2] - full[0]) * ppu); y1 = int((full[3] - c[1]) * ppu)
            placed[k] = (colx + int((c[0] - gminx) * ppu), cy + title_h, x0, y0, x1, y1)
            cy += title_h + (y1 - y0) + pad
        colx += int(wspan * ppu) + 2 * pad
    cy = HEADER_H
    for j, (k, c) in enumerate(insets):
        x0 = int((c[0] - full[0]) * ppu); y0 = int((full[3] - c[3]) * ppu)
        x1 = int((c[2] - full[0]) * ppu); y1 = int((full[3] - c[1]) * ppu)
        placed[("i", j)] = (colx, cy + title_h, x0, y0, x1, y1)
        cy += title_h + (y1 - y0) + pad
    W = max(max(v[0] + max(v[4] - v[2], 330) for v in placed.values()) + pad, 760)
    H = max(v[1] + (v[5] - v[3]) for v in placed.values()) + pad
    canvas = np.zeros((H, W, 3), np.uint8)
    for pk, (px, py, x0, y0, x1, y1) in placed.items():
        k = insets[pk[1]][0] if isinstance(pk, tuple) else pk
        canvas[py:py + (y1 - y0), px:px + (x1 - x0)] = renders[k][0][y0:y1, x0:x1]
        cv2.rectangle(canvas, (px - 2, py - 2), (px + x1 - x0 + 1, py + y1 - y0 + 1), (70, 62, 55), 2)
        lo = "" if not np.isfinite(cuts[k]) else f"{cuts[k]:.0f}"
        hi = "" if not np.isfinite(cuts[k + 1]) else f"{cuts[k + 1]:.0f}"
        rng = "" if nb == 1 else f"   height {lo or 'below'} {'to ' + hi if hi else 'and up'}" if lo else f"   height below {hi}"
        label(canvas, names[k] + (" - detached area" if isinstance(pk, tuple) else rng), (px, py - 12), 0.75)

    def to_px(k, wx, wz):
        px, py, x0, y0, x1, y1 = placed[k]
        return (int(round((wx - full[0]) * ppu - x0 + px)), int(round((full[3] - wz) * ppu - y0 + py)))

    for k1, k2, wx, wz, _ in conns:
        a, b = to_px(k1, wx, wz), to_px(k2, wx, wz)
        cv2.line(canvas, a, b, (0, 0, 0), 6, cv2.LINE_AA)
        cv2.line(canvas, a, b, RED, 3, cv2.LINE_AA)
        for q in (a, b):
            cv2.circle(canvas, q, 7, (0, 0, 0), -1, cv2.LINE_AA)
            cv2.circle(canvas, q, 5, RED, -1, cv2.LINE_AA)
    exit_px = []
    for k, e in exits:
        x, y = to_px(k, e[0], e[2])
        cv2.rectangle(canvas, (x - 22, y - 30), (x + 22, y - 14), (20, 90, 30), -1)
        cv2.putText(canvas, "EXIT", (x - 19, y - 17), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        exit_px.append((x, y))

    # header: title, legend, level-complete box
    lv = LEVELS[code]
    label(canvas, f"{code}  {lv['name']}", (pad, 42), 1.1, thick=2)
    legend = "Red lines join the same spot on two layers (stairs, ramps, drops)." if nb > 1 else ""
    if legend:
        label(canvas, legend, (pad, 74), 0.55, (200, 190, 170))
    bx = W - 190
    cv2.rectangle(canvas, (bx, 14), (W - pad, HEADER_H - 14), (60, 52, 46), 2)
    label(canvas, "Level", (bx + 10, 44), 0.6)
    label(canvas, "Complete", (bx + 10, 66), 0.6)
    lc = exit_px[0] if exit_px else (W - pad - 30, HEADER_H // 2)

    coords = {}
    for (l, p, s, c), k in zip(prof, band_of):
        pk = k
        for j, (kk, b) in enumerate(insets):
            if kk == k and b[0] <= p[0] <= b[2] and b[1] <= p[2] <= b[3]:
                pk = ("i", j)
        coords[l["name"]] = to_px(pk, p[0], p[2]) + (int(k),)
    coords[f"{code} - Level Complete"] = (int(lc[0]), int(lc[1]), -1)
    cv2.imwrite(out_png, canvas[:, :, ::-1], [cv2.IMWRITE_PNG_COMPRESSION, 9])
    meta = {"code": code, "cuts": [float(c) for c in cuts[1:-1]], "ppu": ppu, "size": [W, H], "names": names,
            "connectors": len(conns), "per_layer": np.bincount(band_of, minlength=nb).tolist(), "exits": len(exit_px), "insets": len(insets)}
    if verbose:
        print(json.dumps(meta))
    return coords, meta


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "preview"), exist_ok=True)
    for code in sys.argv[1:]:
        compose(code, os.path.join(ROOT, "preview", f"{code}.png"), verbose=True)
