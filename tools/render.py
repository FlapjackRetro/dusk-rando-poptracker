"""Textured top-down renderer for DUSK levels.

render_band(level_data, bounds, ylo, yhi, ppu) -> (rgb image, height buffer)
Floors (upward-facing triangles) whose height lies within [ylo, yhi] are drawn with their textures,
highest-first-wins (painter's order by height). Walls are derived from height discontinuities.
"""
import functools

import cv2
import numpy as np

from textures import material_texture

BG = (14, 12, 16)


@functools.lru_cache(None)
def tex_mips(key):
    r = material_texture(key)
    if r is None or not isinstance(r[0], np.ndarray):
        tint = (r[3] if r else (0.45, 0.45, 0.45))
        img = np.full((4, 4, 3), 200, np.uint8)
        return [img], (1, 1), (0, 0), tint
    img, scale, off, tint, _ = r
    mips = [img]
    while min(mips[-1].shape[:2]) > 4:
        mips.append(cv2.resize(mips[-1], (mips[-1].shape[1] // 2, mips[-1].shape[0] // 2), interpolation=cv2.INTER_AREA))
    return mips, scale, off, tint


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def tri_normals(T):
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)


def render_band(d, bounds, ylo, yhi, ppu, sel=None, below_fade=None):
    """bounds = (x0, z0, x1, z1) world; returns rgb uint8 (H,W,3), height (H,W) float (nan where empty)."""
    x0, z0, x1, z1 = bounds
    W = int(np.ceil((x1 - x0) * ppu))
    H = int(np.ceil((z1 - z0) * ppu))
    T, UV, MAT = d["tris"], d["uv"], d["mat"]
    m = d["active"].copy()
    if sel is not None:
        m &= sel
    n = tri_normals(T)
    c = T.mean(1)
    m &= n[:, 1] > 0.35  # walkable-ish, facing up
    m &= (c[:, 1] >= ylo) & (c[:, 1] <= yhi)
    m &= (T[:, :, 0].max(1) > x0) & (T[:, :, 0].min(1) < x1) & (T[:, :, 2].max(1) > z0) & (T[:, :, 2].min(1) < z1)
    idx = np.nonzero(m)[0]
    idx = idx[np.argsort(c[idx, 1], kind="stable")]
    img = np.zeros((H, W, 3), np.float32)
    hb = np.full((H, W), np.nan, np.float32)
    keys = d["matkeys"]
    for i in idx:
        t = T[i]
        px = np.stack([(t[:, 0] - x0) * ppu, (z1 - t[:, 2]) * ppu], 1)
        bx0, by0 = np.floor(px.min(0)).astype(int)
        bx1, by1 = np.ceil(px.max(0)).astype(int) + 1
        bx0c, by0c = max(bx0, 0), max(by0, 0)
        bx1c, by1c = min(bx1, W), min(by1, H)
        if bx1c <= bx0c or by1c <= by0c:
            continue
        mask = np.zeros((by1c - by0c, bx1c - bx0c), np.uint8)
        cv2.fillConvexPoly(mask, np.round((px - [bx0c, by0c]) * 16).astype(np.int32), 1, lineType=cv2.LINE_8, shift=4)
        if not mask.any():
            continue
        mips, scale, off, tint = tex_mips(keys[MAT[i]])
        # texel density -> mip choice
        uvp = UV[i] * np.array(scale) + np.array(off)
        tex0 = mips[0]
        th, tw = tex0.shape[:2]
        src = np.stack([uvp[:, 0] * tw, (1 - uvp[:, 1]) * th], 1)
        a_px = abs(cross2(px[1] - px[0], px[2] - px[0])) + 1e-6
        a_tx = abs(cross2(src[1] - src[0], src[2] - src[0])) + 1e-6
        lvl = int(np.clip(np.floor(0.5 * np.log2(a_tx / a_px)), 0, len(mips) - 1))
        tex = mips[lvl]
        f = tw / tex.shape[1]
        srcl = src / f
        # affine dst->src
        dst = (px - [bx0c, by0c]).astype(np.float32)
        A = cv2.getAffineTransform(dst, srcl.astype(np.float32)) if abs(cross2(dst[1] - dst[0], dst[2] - dst[0])) > 1e-4 else None
        if A is None:
            patch = np.full((by1c - by0c, bx1c - bx0c, 3), tex.mean((0, 1)), np.float32)
        else:
            patch = cv2.warpAffine(tex, A, (bx1c - bx0c, by1c - by0c), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                   borderMode=cv2.BORDER_WRAP).astype(np.float32)
        shade = 0.6 + 0.4 * n[i, 1]
        patch *= np.array(tint, np.float32) * shade
        mm = mask.astype(bool)
        sub = img[by0c:by1c, bx0c:bx1c]
        sub[mm] = patch[mm]
        # per-pixel height via plane
        hsub = hb[by0c:by1c, bx0c:bx1c]
        yy, xx = np.nonzero(mm)
        # plane: y = a*wx + b*wz + c
        nn = n[i]
        wx = (xx + bx0c + 0.5) / ppu + x0
        wz = z1 - (yy + by0c + 0.5) / ppu
        hsub[yy, xx] = t[0, 1] - (nn[0] * (wx - t[0, 0]) + nn[2] * (wz - t[0, 2])) / max(nn[1], 1e-3)
    img = 255.0 * (np.clip(img, 0, 255) / 255.0) ** 0.75
    return np.clip(img, 0, 255).astype(np.uint8), hb


def stylise(img, hb, ppu, step=0.6, ghost=None):
    """Background, wall outlines from height discontinuities, subtle drop shadow."""
    H, W = hb.shape
    filled = ~np.isnan(hb)
    out = np.empty((H, W, 3), np.uint8)
    out[:] = BG
    if ghost is not None:
        out = ghost.copy()
    out[filled] = img[filled]
    h = np.where(filled, hb, -1e4)
    # edges: neighbour height difference > step, or filled/empty boundary
    edge = np.zeros((H, W), bool)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        sh = np.roll(np.roll(h, dy, 0), dx, 1)
        edge |= (sh - h > step) & filled  # neighbour higher -> wall on our side
        edge |= filled & (sh < -1e3)
    k = max(1, int(round(ppu / 3)))
    edge = cv2.dilate(edge.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool) & filled
    out[edge] = (out[edge] * 0.25).astype(np.uint8)
    return out
