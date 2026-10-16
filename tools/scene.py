"""Load a DUSK level's world-space triangle soup (+ per-triangle metadata) and cache it as .npz."""
import json
import os
import sys

import numpy as np

from unitymesh import (CLASS_MESH, CLASS_MESHFILTER, CLASS_MESHRENDERER, CLASS_MESHCOLLIDER, SerializedFile,
                       matrix_trs, read_mesh, read_meshfilter)

from paths import CACHE, DUSK_DATA

DATA = os.path.join(DUSK_DATA, "")
os.makedirs(CACHE, exist_ok=True)

CLASS_GAMEOBJECT, CLASS_TRANSFORM, CLASS_RECTTRANSFORM = 1, 4, 224


class Scene:
    def __init__(self, idx):
        self.sf = sf = SerializedFile(f"{DATA}level{idx}")
        self.go = {p: sf.gameobject(p) for p in sf.of_class(CLASS_GAMEOBJECT)}
        self.tr = {}
        for cid in (CLASS_TRANSFORM, CLASS_RECTTRANSFORM):
            for p in sf.of_class(cid):
                self.tr[p] = sf.transform(p)
        self.go_tr = {t["go"][1]: p for p, t in self.tr.items()}
        self._world = {}

    def world(self, trpid):
        if trpid in self._world:
            return self._world[trpid]
        t = self.tr[trpid]
        M = matrix_trs(t["pos"], t["rot"], t["scale"])
        f = t["father"][1]
        if f:
            M = self.world(f) @ M
        self._world[trpid] = M
        return M

    def active(self, gopid):
        t = self.go_tr.get(gopid)
        while t:
            if not self.go[self.tr[t]["go"][1]]["active"]:
                return False
            t = self.tr[t]["father"][1] or None
        return True

    def path(self, gopid):
        names = []
        t = self.go_tr.get(gopid)
        while t:
            names.append(self.go[self.tr[t]["go"][1]]["name"])
            t = self.tr[t]["father"][1] or None
        return "/".join(reversed(names))


def load(idx, force=False):
    fn = f"{CACHE}/level{idx}.npz"
    if os.path.exists(fn) and not force:
        z = np.load(fn, allow_pickle=True)
        return {k: z[k] for k in z.files}
    S = Scene(idx)
    sf = S.sf
    meshes = {}
    tris, objid, active, matid, uvs = [], [], [], [], []
    names, mats = [], {}
    filters = {}
    for p in sf.of_class(CLASS_MESHFILTER):
        go, mesh = read_meshfilter(sf, p)
        filters[go[1]] = mesh

    def getmesh(mpid):
        if mpid not in meshes:
            try:
                meshes[mpid] = read_mesh(sf, mpid)
            except Exception:
                meshes[mpid] = None
        return meshes[mpid]

    for p in sf.of_class(CLASS_MESHRENDERER):
        r = sf.reader(p)
        go = r.pptr()[1]
        enabled = r.u8()
        r.bytes(6); r.align(); r.u32(); r.u16(); r.u16(); r.bytes(32)
        mlist = [r.pptr() for _ in range(r.i32())]
        sb_first, sb_count = r.u16(), r.u16()
        mesh = filters.get(go)
        if not mesh or mesh[0] != 0 or mesh[1] == 0:
            continue
        m = getmesh(mesh[1])
        if m is None:
            continue
        trp = S.go_tr.get(go)
        if trp is None:
            continue
        if sb_count:
            v = m["vertices"]
            subs = list(range(sb_first, sb_first + sb_count))
        else:
            M = S.world(trp)
            v = m["vertices"] @ M[:3, :3].T + M[:3, 3]
            subs = list(range(len(m["subs"])))
        oid = len(names)
        names.append(S.path(go))
        act = S.active(go) and bool(enabled)
        for j, si in enumerate(subs):
            if si >= len(m["subs"]):
                continue
            t = m["subs"][si]
            if not len(t):
                continue
            mp = mlist[min(j, len(mlist) - 1)] if mlist else (0, 0)
            key = (sf.externals[mp[0] - 1] if mp[0] else "local") + ":" + str(mp[1])
            mi = mats.setdefault(key, len(mats))
            tris.append(v[t].astype(np.float32))
            uv = m["uv"] if m["uv"] is not None and m["uv"].shape[1] >= 2 else np.zeros((len(v), 2), np.float32)
            uvs.append(uv[:, :2][t].astype(np.float32))
            objid.append(np.full(len(t), oid, np.int32))
            active.append(np.full(len(t), act, bool))
            matid.append(np.full(len(t), mi, np.int32))
    out = {
        "tris": np.concatenate(tris),
        "obj": np.concatenate(objid),
        "active": np.concatenate(active),
        "names": np.array(names, dtype=object),
        "mat": np.concatenate(matid),
        "uv": np.concatenate(uvs),
        "matkeys": np.array(sorted(mats, key=mats.get), dtype=object),
    }
    np.savez_compressed(fn, **out)
    return out


if __name__ == "__main__":
    for i in map(int, sys.argv[1:]):
        d = load(i, force=True)
        print(i, len(d["tris"]), d["active"].mean())
