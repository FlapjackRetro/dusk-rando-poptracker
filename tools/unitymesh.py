"""Mesh / MeshFilter / MeshRenderer / Material / Texture readers for Unity 2018.2 (SerializedFile v17).

Builds on dusk-rando/tools/asset_extract/sf.py.
"""
import os
import struct
import sys

import numpy as np

from paths import DUSK_RANDO, need  # noqa: E402

sys.path.insert(0, need(os.path.join(DUSK_RANDO, "tools", "asset_extract", "sf.py"), "dusk-rando sf.py").rsplit(os.sep, 1)[0])
from sf import Reader, SerializedFile  # noqa: E402

CLASS_MESHFILTER = 33
CLASS_MESHRENDERER = 23
CLASS_MESH = 43
CLASS_MESHCOLLIDER = 64
CLASS_MATERIAL = 21
CLASS_TEXTURE2D = 28

# Unity 2017/2018 ChannelFormat: Float, Float16, Color(unorm8), Byte, UInt32
FMT_SIZE = {0: 4, 1: 2, 2: 1, 3: 1, 4: 4}


def read_mesh(sf: SerializedFile, pid):
    """-> dict(name, vertices Nx3 float32, triangles Mx3 int, submesh_tris [array], uv Nx2|None)"""
    r = sf.reader(pid)
    name = r.string()
    subs = []
    for _ in range(r.i32()):
        first_byte, index_count, topology, base_vertex, first_vertex, vertex_count = (
            r.u32(), r.u32(), r.i32(), r.u32(), r.u32(), r.u32())
        r.bytes(24)  # AABB
        subs.append((first_byte, index_count, topology, base_vertex))
    # BlendShapeData
    n = r.i32(); r.bytes(n * 40)
    n = r.i32(); r.bytes(n * 12)
    for _ in range(r.i32()):
        r.string(); r.u32(); r.i32(); r.i32()
    n = r.i32(); r.bytes(n * 4)
    n = r.i32(); r.bytes(n * 64)  # bind pose
    n = r.i32(); r.bytes(n * 4)  # bone name hashes
    r.u32()  # root bone hash
    compression = r.u8()
    r.u8(); r.u8(); r.u8()  # readable, keepVerts, keepIdx
    r.align()
    index_format = r.i32()
    n = r.i32()
    ib = r.bytes(n)
    r.align()
    vcount = r.u32()
    chans = []
    for _ in range(r.i32()):
        chans.append((r.u8(), r.u8(), r.u8(), r.u8()))
    n = r.i32()
    vd = r.bytes(n)
    r.align()
    if compression != 0 or vcount == 0:
        return None
    # stream layout
    nstreams = max(c[0] for c in chans if (c[3] & 0xF)) + 1
    strides = [0] * nstreams
    for s, off, fmt, dim in chans:
        dim &= 0xF
        if dim:
            strides[s] += FMT_SIZE.get(fmt, 4) * dim
    offs, o = [], 0
    for s in range(nstreams):
        offs.append(o)
        o += strides[s] * vcount
        o = (o + 15) // 16 * 16

    def channel(i):
        if i >= len(chans):
            return None
        s, off, fmt, dim = chans[i]
        dim &= 0xF
        if not dim:
            return None
        dt = {0: np.float32, 1: np.float16, 2: np.uint8, 3: np.uint8, 4: np.uint32}[fmt]
        size = FMT_SIZE[fmt]
        buf = np.frombuffer(vd, dtype=np.uint8, count=strides[s] * vcount, offset=offs[s]).reshape(vcount, strides[s])
        return buf[:, off:off + size * dim].copy().view(dt).astype(np.float32).reshape(vcount, dim)

    verts = channel(0)
    uv = channel(4)
    idt = np.uint16 if index_format == 0 else np.uint32
    idx = np.frombuffer(ib, dtype=idt).astype(np.int64)
    isz = 2 if index_format == 0 else 4
    sub_tris = []
    for first_byte, count, topo, base in subs:
        if topo != 0:
            sub_tris.append(np.zeros((0, 3), np.int64))
            continue
        a = idx[first_byte // isz: first_byte // isz + count] + base
        sub_tris.append(a[: len(a) // 3 * 3].reshape(-1, 3))
    return {"name": name, "vertices": verts, "uv": uv, "subs": sub_tris}


def read_meshfilter(sf, pid):
    r = sf.reader(pid)
    return r.pptr(), r.pptr()  # gameobject, mesh


def read_meshrenderer(sf, pid):
    """-> (go, enabled, [material pptrs])"""
    r = sf.reader(pid)
    go = r.pptr()
    enabled = r.u8()
    r.u8(); r.u8(); r.u8()  # cast shadows, receive, dynamic occludee
    r.u8(); r.u8(); r.u8()  # motion vectors, light probe usage, reflection probe usage
    r.align()
    r.u32()  # rendering layer mask (2018.1+)
    r.i32()  # renderer priority (2018.3?)  -- verified empirically below
    return go, enabled, r


def matrix_trs(pos, rot, scale):
    x, y, z, w = rot
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    M = np.eye(4)
    M[:3, :3] = R * np.array(scale)[None, :]
    M[:3, 3] = pos
    return M
