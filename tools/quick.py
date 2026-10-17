"""Quick diagnostic render: top-down, highest visible surface coloured by height, with check markers."""
import json
import os
import sys

import cv2
import numpy as np

from scene import load

from paths import LOCATIONS_JSON, TOOLS, need

LOC = json.load(open(need(LOCATIONS_JSON, "dusk-rando locations.json")))
# Locations the pack leaves out even though dusk-rando's locations.json still lists them
# ("drop" lists in level_config.json, e.g. pickups the apworld no longer makes checks).
_CFG = json.load(open(os.path.join(TOOLS, "level_config.json")))
DROPPED = {name for cfg in _CFG.values() for name in cfg.get("drop", [])}
LOC["locations"] = [l for l in LOC["locations"] if l["name"] not in DROPPED]
SCENE_IDX = {"E1M1": 3, "E1M2": 4, "E1M3": 5, "E1M4": 6, "E1M5": 7, "E1M6": 8, "E1M7": 9, "E1M8": 10, "E1M9": 11,
             "E1M10": 12, "E1MS": 14, "E2M1": 22, "E2M2": 23, "E2M3": 24, "E2M4": 25, "E2M5": 26, "E2M6": 27,
             "E2M7": 28, "E2M8": 29, "E2M9": 30, "E2M10": 31, "E2MS": 32, "E3M1": 37, "E3M2": 38, "E3M3": 39,
             "E3M4": 40, "E3M5": 41, "E3M6": 42, "E3M7": 43, "E3M8": 44, "E3M9": 45, "E3M10": 46, "E3MS": 47}


def render(code, ylo=-1e9, yhi=1e9, scale=4, out=None):
    d = load(SCENE_IDX[code])
    T = d["tris"][d["active"]]
    locs = [l for l in LOC["locations"] if l["level"] == code and l.get("pos")]
    P = np.array([l["pos"] for l in locs])
    lo = P.min(0) - 20
    hi = P.max(0) + 20
    # keep triangles within check xz bbox (+margin) and y band
    c = T.mean(1)
    keep = (c[:, 0] > lo[0] - 40) & (c[:, 0] < hi[0] + 40) & (c[:, 2] > lo[2] - 40) & (c[:, 2] < hi[2] + 40)
    keep &= (T[:, :, 1].min(1) < yhi) & (T[:, :, 1].max(1) > ylo)
    T = T[keep]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    up = np.abs(n[:, 1]) > 0.5
    W = int((hi[0] - lo[0]) * scale)
    H = int((hi[2] - lo[2]) * scale)
    img = np.zeros((H, W, 3), np.uint8)
    zbuf = np.full((H, W), -1e9, np.float32)
    ymin, ymax = np.percentile(T[up][:, :, 1], [2, 98]) if up.any() else (0, 1)
    order = np.argsort(T[:, :, 1].mean(1))
    for i in order:
        t = T[i]
        y = t[:, 1].mean()
        if y > yhi:
            continue
        pts = np.stack([(t[:, 0] - lo[0]) * scale, (hi[2] - t[:, 2]) * scale], 1).astype(np.int32)
        if up[i]:
            v = np.clip((y - ymin) / max(1e-3, ymax - ymin), 0, 1)
            col = cv2.applyColorMap(np.array([[int(v * 255)]], np.uint8), cv2.COLORMAP_VIRIDIS)[0, 0]
            col = (col * (0.55 + 0.45 * abs(n[i, 1]))).astype(np.uint8)
            cv2.fillConvexPoly(img, pts, tuple(int(x) for x in col))
        else:
            cv2.polylines(img, [pts], True, (200, 200, 200), 1)
    for l, p in zip(locs, P):
        if not (ylo <= p[1] <= yhi):
            continue
        x, z = int((p[0] - lo[0]) * scale), int((hi[2] - p[2]) * scale)
        cv2.circle(img, (x, z), 5, (0, 0, 255), -1)
    cv2.imwrite(out or os.path.join(TOOLS, f"q_{code}.png"), img)
    return img


if __name__ == "__main__":
    render(sys.argv[1], *(float(a) for a in sys.argv[2:4]))
