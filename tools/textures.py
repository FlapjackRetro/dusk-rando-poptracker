"""Material -> main texture lookup and Texture2D decoding (Unity 2018.2)."""
import functools
import os

import numpy as np

from unitymesh import SerializedFile

from paths import DUSK_DATA

DATA = os.path.join(DUSK_DATA, "")
CLASS_MATERIAL, CLASS_TEXTURE2D = 21, 28


@functools.lru_cache(None)
def sfile(name):
    p = DATA + name
    if not os.path.exists(p):
        return None
    return SerializedFile(p)


def read_material(sf, pid):
    r = sf.reader(pid)
    name = r.string()
    shader = r.pptr()
    r.string()  # keywords
    r.u32()
    r.u8(); r.u8(); r.align()
    r.i32()
    for _ in range(r.i32()):
        r.string(); r.string()
    for _ in range(r.i32()):
        r.string()
    tex = {}
    for _ in range(r.i32()):
        k = r.string()
        t = r.pptr()
        scale = (r.f32(), r.f32())
        off = (r.f32(), r.f32())
        tex[k] = (t, scale, off)
    floats = {}
    for _ in range(r.i32()):
        k = r.string(); floats[k] = r.f32()
    colors = {}
    for _ in range(r.i32()):
        k = r.string(); colors[k] = (r.f32(), r.f32(), r.f32(), r.f32())
    return {"name": name, "tex": tex, "colors": colors}


def _dxt_colors(c0, c1, four):
    def rgb565(c):
        r = ((c >> 11) & 31) * 255 // 31
        g = ((c >> 5) & 63) * 255 // 63
        b = (c & 31) * 255 // 31
        return np.stack([r, g, b], -1).astype(np.int32)
    a, b = rgb565(c0), rgb565(c1)
    c2 = np.where(four[:, None], (2 * a + b) // 3, (a + b) // 2)
    c3 = np.where(four[:, None], (a + 2 * b) // 3, 0)
    return np.stack([a, b, c2, c3], 1)  # n,4,3


def decode_dxt(data, w, h, dxt5):
    bw, bh = (w + 3) // 4, (h + 3) // 4
    bs = 16 if dxt5 else 8
    raw = np.frombuffer(data, np.uint8, count=bw * bh * bs).reshape(-1, bs)
    col = raw[:, 8:] if dxt5 else raw
    c0 = col[:, 0].astype(np.uint16) | (col[:, 1].astype(np.uint16) << 8)
    c1 = col[:, 2].astype(np.uint16) | (col[:, 3].astype(np.uint16) << 8)
    four = (c0 > c1) | np.bool_(dxt5)
    pal = _dxt_colors(c0.astype(np.int32), c1.astype(np.int32), four)
    bits = col[:, 4:8].astype(np.uint32)
    bits = bits[:, 0] | (bits[:, 1] << 8) | (bits[:, 2] << 16) | (bits[:, 3] << 24)
    idx = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))[None]) & 3
    px = np.take_along_axis(pal, idx[:, :, None].astype(np.int64).repeat(3, 2), 1)  # n,16,3
    img = px.reshape(bh, bw, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 3)
    if not dxt5:
        return img[:h, :w].astype(np.uint8)
    a0 = raw[:, 0].astype(np.int32); a1 = raw[:, 1].astype(np.int32)
    k = np.arange(8)
    six = np.stack([a0, a1] + [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)], 1)
    four = np.stack([a0, a1] + [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0 * a0, 0 * a0 + 255], 1)
    apal = np.where((a0 > a1)[:, None], six, four)
    ab = np.zeros(len(raw), np.uint64)
    for i in range(6):
        ab |= raw[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    aidx = ((ab[:, None] >> (np.uint64(3) * np.arange(16, dtype=np.uint64))[None]) & np.uint64(7)).astype(np.int64)
    al = np.take_along_axis(apal, aidx, 1)
    al = al.reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)
    return np.dstack([img, al])[:h, :w].astype(np.uint8)


def read_texture(sf, pid, alpha=False):
    r = sf.reader(pid)
    name = r.string()
    r.i32(); r.u8(); r.align()
    w, h = r.i32(), r.i32()
    size = r.i32()
    fmt = r.i32()
    mips = r.i32()
    r.u8(); r.u8(); r.align()  # readable, streaming mips
    r.i32()  # streaming priority
    r.i32(); r.i32()  # image count, dimension
    r.bytes(24)
    r.i32(); r.i32()
    n = r.i32()
    data = r.bytes(n)
    r.align()
    if n == 0:
        off, sz = r.u32(), r.u32()
        path = r.string()
        fn = DATA + os.path.basename(path)
        if not os.path.exists(fn):
            return name, None
        with open(fn, "rb") as fh:
            fh.seek(off)
            data = fh.read(sz)
    try:
        if fmt == 10:
            img = decode_dxt(data, w, h, False)
        elif fmt == 12:
            img = decode_dxt(data, w, h, True)
            img = img if alpha else img[:, :, :3]
        elif fmt == 3:
            img = np.frombuffer(data, np.uint8, count=w * h * 3).reshape(h, w, 3)
        elif fmt == 4:
            img = np.frombuffer(data, np.uint8, count=w * h * 4).reshape(h, w, 4)
            img = img if alpha else img[:, :, :3]
        elif fmt == 5:
            img = np.frombuffer(data, np.uint8, count=w * h * 4).reshape(h, w, 4)[:, :, [1, 2, 3, 0]]
            img = img if alpha else img[:, :, :3]
        elif fmt == 1:
            a = np.frombuffer(data, np.uint8, count=w * h).reshape(h, w)
            img = np.dstack([np.full_like(a, 255)] * 3 + ([a] if alpha else []))
        elif fmt == 7:
            c = np.frombuffer(data, np.uint16, count=w * h).reshape(h, w).astype(np.int32)
            img = np.stack([((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31], -1)
        else:
            return name, ("fmt", fmt)
    except Exception as e:  # noqa
        return name, ("err", str(e))
    # Unity stores textures bottom-up
    return name, np.ascontiguousarray(np.asarray(img, np.uint8)[::-1])


@functools.lru_cache(None)
def material_texture(key):
    """key 'sharedassetsN.assets:pid' -> (RGB uint8 image or None, tiling(sx,sy), offset, tint rgb)"""
    fname, pid = key.split(":")
    if fname == "local":
        return None
    sf = sfile(fname)
    if sf is None or int(pid) not in sf.objects:
        return None
    m = read_material(sf, int(pid))
    t = m["tex"].get("_MainTex")
    tint = m["colors"].get("_Color", (1, 1, 1, 1))[:3]
    if not t or t[0][1] == 0:
        return None, (1, 1), (0, 0), tint, m["name"]
    (fi, tpid), scale, off = t
    tsf = sf if fi == 0 else sfile(sf.externals[fi - 1].split("/")[-1])
    if tsf is None or tpid not in tsf.objects:
        return None, scale, off, tint, m["name"]
    tname, img = read_texture(tsf, tpid)
    if not isinstance(img, np.ndarray):
        return img, scale, off, tint, m["name"]
    return img, scale, off, tint, m["name"]
