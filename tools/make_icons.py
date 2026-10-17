"""Generate the pack's item icons. Weapon/key glyphs come from DUSK's own HUD textures."""
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from textures import read_texture, sfile

from paths import PACK, TOOLS

OUT = os.path.join(PACK, "images", "items")
os.makedirs(OUT, exist_ok=True)
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
S = 64


FONT_CANDIDATES = [BOLD, "DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf",
                   r"C:\Windows\Fonts\arialbd.ttf", "/Library/Fonts/Arial Bold.ttf"]


def font(sz):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def tile(bg=(46, 38, 32), edge=(96, 78, 60)):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((1, 1, S - 2, S - 2), 8, fill=bg + (255,), outline=edge + (255,), width=2)
    return im, d


def ctext(d, y, text, sz, fill=(240, 228, 200)):
    f = font(sz)
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, y), text, font=f, fill=fill + (255,), stroke_width=2, stroke_fill=(0, 0, 0, 255))


def hud(name, pid):
    _, img = read_texture(sfile("resources.assets"), pid, alpha=True)
    return img


# ---- weapons: DUSK's HUD ammo glyphs + a label
WEAPONS = {  # code: (label, glyph pid or None)
    "pistol": ("PISTOL", 69), "shotgun": ("SHOTGUN", 42), "super_shotgun": ("SUPER SG", 107),
    "assault_rifle": ("ASSAULT", 63), "hunting_rifle": ("RIFLE", 34), "crossbow": ("XBOW", 103),
    "mortar": ("MORTAR", 89), "riveter": ("RIVETER", 111), "sword": ("SWORD", None),
}


def glyph_img(pid, box=34):
    g = hud("", pid)
    a = g[:, :, 3]
    ys, xs = np.nonzero(a > 20)
    g = g[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = g.shape[:2]
    k = min(box / w, (box - 8) / h)
    g = cv2.resize(g, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(g, "RGBA")


def sword_img():
    im = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(4, 15), (28, 12), (34, 15), (28, 18)], fill=(235, 235, 235, 255))
    d.rectangle((26, 8, 28, 22), fill=(200, 170, 90, 255))
    d.rectangle((28, 13, 38, 17), fill=(120, 80, 50, 255))
    return im


for code, (lab, pid) in WEAPONS.items():
    for stage, suffix in ((1, ""), (2, "_2")) if code in ("pistol", "shotgun") else ((1, ""),):
        im, d = tile()
        g = sword_img() if pid is None else glyph_img(pid)
        if stage == 2:
            im.alpha_composite(g, ((S - g.width) // 2 - 6, 8 + (28 - g.height) // 2))
            im.alpha_composite(g, ((S - g.width) // 2 + 6, 14 + (28 - g.height) // 2))
        else:
            im.alpha_composite(g, ((S - g.width) // 2, 10 + (28 - g.height) // 2))
        ctext(d, 42, lab, 12)
        if stage == 2:
            ctext(d, 2, "x2", 13, (255, 210, 90))
        im.save(f"{OUT}/{code}{suffix}.png")

# ---- keys: the HUD key glyph, per colour
KEYS = {"red": 55, "blue": 51, "yellow": 75}
for col, pid in KEYS.items():
    g = hud("", pid)
    a = g[:, :, 3]
    ys, xs = np.nonzero(a > 20)
    xs_r = xs[xs > 500]
    ys_r = ys[xs > 500]
    g = g[ys_r.min():ys_r.max() + 1, xs_r.min():xs_r.max() + 1]
    g = cv2.resize(g, (g.shape[1] * 2, g.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gi = Image.fromarray(g, "RGBA")
    k = min(54 / gi.width, 54 / gi.height)
    gi = gi.resize((int(gi.width * k), int(gi.height * k)), Image.NEAREST)
    im.alpha_composite(gi, ((S - gi.width) // 2, (S - gi.height) // 2))
    im.save(f"{OUT}/key_{col}.png")

# ---- level access tiles
EP_COL = {1: ((70, 46, 26), (176, 120, 60)), 2: ((30, 46, 56), (90, 140, 160)), 3: ((56, 26, 40), (170, 70, 110))}
for ep in (1, 2, 3):
    for m in list(range(1, 11)) + ["S"]:
        im, d = tile(*EP_COL[ep])
        ctext(d, 6, f"E{ep}", 16, (230, 210, 170))
        ctext(d, 24, f"M{m}", 26 if m != 10 else 22)
        im.save(f"{OUT}/e{ep}m{str(m).lower()}.png")

# ---- settings
SETTINGS = {
    "opt_weapons": "WEAPONS", "opt_keys": "KEYS", "opt_powerups": "POWER\nUPS", "opt_secrets": "SECRETS",
    "opt_treasure_chests": "CHESTS", "opt_health": "HEALTH", "opt_armor": "MORALE", "opt_ammo": "AMMO",
}
for code, text in SETTINGS.items():
    im, d = tile((34, 34, 40), (90, 90, 110))
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        ctext(d, (24 if len(lines) == 1 else 14 + 18 * i), ln, 12 if len(ln) > 6 else 14)
    im.save(f"{OUT}/{code}.png")
for stage, (a, b) in enumerate([("COMBAT", "NORMAL"), ("COMBAT", "LENIENT"), ("COMBAT", "NONE")]):
    im, d = tile((40, 30, 30), (130, 80, 70))
    ctext(d, 12, a, 12); ctext(d, 32, b, 12 if len(b) > 6 else 14, (255, 210, 120))
    im.save(f"{OUT}/combat_{stage}.png")
for stage, (a, b) in enumerate([("GOAL", "BOSSES"), ("GOAL", "ALL LVLS")]):
    im, d = tile((30, 40, 30), (80, 130, 80))
    ctext(d, 12, a, 13); ctext(d, 32, b, 12, (200, 255, 170))
    im.save(f"{OUT}/goal_{stage}.png")
im, d = tile((28, 36, 48), (80, 110, 150))
ctext(d, 12, "AUTO", 13); ctext(d, 32, "MAP", 14, (170, 210, 255))
im.save(f"{OUT}/auto_tab.png")
# check marker images (opened/closed) for locations
for name, col in (("check", (220, 180, 60)), ("check_done", (90, 90, 90))):
    im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((3, 8, 29, 27), 4, fill=col + (255,), outline=(0, 0, 0, 255), width=2)
    d.rectangle((3, 8, 29, 14), fill=tuple(int(c * 0.7) for c in col) + (255,), outline=(0, 0, 0, 255), width=2)
    im.save(f"{OUT}/{name}.png")
# pack icon / sheet preview
names = sorted(os.listdir(OUT))
sheet = Image.new("RGBA", (S * 12, S * ((len(names) + 11) // 12)), (20, 20, 20, 255))
for i, n in enumerate(names):
    sheet.alpha_composite(Image.open(f"{OUT}/{n}").convert("RGBA").resize((S, S)), ((i % 12) * S, (i // 12) * S))
sheet.save(os.path.join(TOOLS, "icon_sheet.png"))
print(len(names), "icons")
