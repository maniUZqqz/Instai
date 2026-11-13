"""Flat vector backgrounds for stick-figure stories (Pillow only): a prison cell, a corridor, a yard, a street at night, a forest, a room, a roof,
a desert, a cave, a lab, a sewer, a bridge and a plain colour. Deterministic: the same key and size give the same pixels.

`pick(text)` chooses a background from a location phrase (Persian or English), so a storyboard that only says "in the prison yard" still
gets a fitting picture.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

INK = (31, 36, 48)

BACKGROUNDS: dict[str, dict] = {
    "plain": {"fa": "ساده", "en": "Plain", "words": ("plain", "void", "empty", "white", "ساده", "خالی")},
    "cell": {"fa": "سلول زندان", "en": "Prison cell", "words": ("cell", "prison", "jail", "inmate", "سلول", "زندان", "بازداشت")},
    "corridor": {"fa": "راهرو", "en": "Corridor", "words": ("corridor", "hall", "hallway", "راهرو", "سالن")},
    "yard": {"fa": "حیاط", "en": "Yard", "words": ("yard", "courtyard", "fence", "حیاط", "محوطه", "حصار")},
    "street": {"fa": "خیابان شبانه", "en": "Night street", "words": ("street", "city", "road", "town", "خیابان", "شهر", "کوچه", "جاده")},
    "forest": {"fa": "جنگل", "en": "Forest", "words": ("forest", "wood", "jungle", "trees", "جنگل", "درخت")},
    "room": {"fa": "اتاق", "en": "Room", "words": ("room", "house", "home", "kitchen", "bedroom", "apartment", "اتاق", "خانه", "آشپزخانه")},
    "rooftop": {"fa": "پشت‌بام", "en": "Rooftop", "words": ("roof", "rooftop", "tower", "پشت بام", "پشت‌بام", "بام", "برج")},
    "desert": {"fa": "بیابان", "en": "Desert", "words": ("desert", "dunes", "sand", "wasteland", "بیابان", "کویر", "صحرا")},
    "cave": {"fa": "غار", "en": "Cave", "words": ("cave", "tunnel", "mine", "underground", "غار", "تونل", "معدن")},
    "lab": {"fa": "آزمایشگاه", "en": "Laboratory", "words": ("lab", "laboratory", "science", "آزمایشگاه", "علمی")},
    "sewer": {"fa": "فاضلاب", "en": "Sewer", "words": ("sewer", "drain", "pipe", "فاضلاب", "لوله", "کانال")},
    "bridge": {"fa": "پل", "en": "Bridge", "words": ("bridge", "river", "پل", "رودخانه")},
}


def keys() -> list[str]:
    return list(BACKGROUNDS)


def pick(text: str, default: str = "plain") -> str:
    low = (text or "").lower()
    best, hit = default, 0
    for k, v in BACKGROUNDS.items():
        n = sum(1 for w in v["words"] if w in low)
        if n > hit:
            best, hit = k, n
    return best


def _grad(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    return ImageOps.colorize(Image.linear_gradient("L").resize((w, h)), top, bottom).convert("RGB")


def _rect(d, box, fill, outline=None, width=0):
    d.rectangle(box, fill=fill, outline=outline, width=width)


def _bars(d, x0, y0, x1, y1, n, col=(70, 78, 96), width=14):
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        d.rectangle([x - width / 2, y0, x + width / 2, y1], fill=col)
    d.rectangle([x0 - width / 2, y0, x1 + width / 2, y0 + width], fill=col)
    d.rectangle([x0 - width / 2, y1 - width, x1 + width / 2, y1], fill=col)


def _stars(d, w, h, n=34, until=0.5):
    for i in range(n):
        x = (i * 9973 % 1000) / 1000 * w
        y = ((i * 7919) % 1000) / 1000 * h * until
        r = 2 + (i % 3)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(235, 238, 255))


def _floor(d, w, h, y, col):
    d.rectangle([0, y, w, h], fill=col)


def draw(key: str, w: int = 1080, h: int = 1350) -> Image.Image:
    key = key if key in BACKGROUNDS else "plain"
    ground = int(h * 0.80)            # where the characters' feet stand (renderer y = 0.93 of the height sits a little below this)
    if key == "plain":
        return _grad(w, h, (244, 241, 234), (226, 222, 212))
    if key == "cell":
        im = Image.new("RGB", (w, h), (120, 124, 132))
        d = ImageDraw.Draw(im)
        for y in range(0, ground, 90):
            d.line([0, y, w, y], fill=(104, 108, 116), width=3)
        for x in range(0, w, 150):
            d.line([x, 0, x, ground], fill=(110, 114, 122), width=2)
        _floor(d, w, h, ground, (84, 88, 96))
        d.rectangle([0, ground, w, ground + 8], fill=(60, 64, 72))
        _rect(d, (int(w * 0.62), int(h * 0.12), int(w * 0.9), int(h * 0.34)), (150, 195, 235), INK, 8)          # barred window
        _bars(d, int(w * 0.64), int(h * 0.12), int(w * 0.88), int(h * 0.34), 4, (52, 58, 74), 9)
        _rect(d, (int(w * 0.04), int(h * 0.58), int(w * 0.40), int(h * 0.66)), (176, 118, 60), INK, 6)           # bunk bed
        _rect(d, (int(w * 0.04), int(h * 0.50), int(w * 0.40), int(h * 0.57)), (150, 98, 52), INK, 6)
        _rect(d, (int(w * 0.05), int(h * 0.57), int(w * 0.08), ground), (60, 64, 72))
        _rect(d, (int(w * 0.36), int(h * 0.57), int(w * 0.39), ground), (60, 64, 72))
        return im
    if key == "corridor":
        im = Image.new("RGB", (w, h), (150, 154, 160))
        d = ImageDraw.Draw(im)
        cx, vy = w // 2, int(h * 0.42)
        d.polygon([(0, 0), (w, 0), (cx + 150, vy - 120), (cx - 150, vy - 120)], fill=(96, 100, 108))
        d.polygon([(0, h), (w, h), (cx + 150, vy + 120), (cx - 150, vy + 120)], fill=(112, 116, 124))
        d.polygon([(0, 0), (cx - 150, vy - 120), (cx - 150, vy + 120), (0, h)], fill=(132, 136, 144))
        d.polygon([(w, 0), (cx + 150, vy - 120), (cx + 150, vy + 120), (w, h)], fill=(124, 128, 136))
        d.rectangle([cx - 150, vy - 120, cx + 150, vy + 120], fill=(60, 64, 74))
        for xo in (-1, 1):                                                                                       # cell doors in perspective
            for k in range(3):
                x0 = cx + xo * (200 + k * 90)
                d.polygon([(x0, vy - 90 + k * 10), (x0 + xo * 40, vy - 100 + k * 8), (x0 + xo * 40, vy + 110 - k * 6), (x0, vy + 100)], fill=(76, 84, 104), outline=INK)
        d.ellipse([cx - 60, 40, cx + 60, 100], fill=(255, 242, 180))
        return im
    if key == "yard":
        im = _grad(w, h, (156, 196, 232), (222, 232, 238))
        d = ImageDraw.Draw(im)
        d.ellipse([w * 0.70, h * 0.07, w * 0.70 + 150, h * 0.07 + 150], fill=(255, 246, 200))
        _rect(d, (0, int(h * 0.38), w, int(h * 0.62)), (160, 150, 140))                                          # prison wall
        for x in range(0, w, 120):
            d.line([x, int(h * 0.38), x, int(h * 0.62)], fill=(140, 130, 120), width=3)
        for x in range(0, w, 60):                                                                                # fence
            d.line([x, int(h * 0.50), x + 30, int(h * 0.74)], fill=(88, 96, 110), width=3)
            d.line([x + 30, int(h * 0.50), x, int(h * 0.74)], fill=(88, 96, 110), width=3)
        d.rectangle([0, int(h * 0.49), w, int(h * 0.51)], fill=INK)
        d.rectangle([0, int(h * 0.74), w, int(h * 0.755)], fill=INK)
        _floor(d, w, h, int(h * 0.755), (186, 170, 140))
        _rect(d, (int(w * 0.80), int(h * 0.22), int(w * 0.96), int(h * 0.40)), (120, 112, 104), INK, 6)
        _rect(d, (int(w * 0.78), int(h * 0.19), int(w * 0.98), int(h * 0.225)), (80, 74, 70), INK, 6)
        return im
    if key == "street":
        im = _grad(w, h, (24, 28, 56), (68, 64, 104))
        d = ImageDraw.Draw(im)
        _stars(d, w, h, 40, 0.4)
        d.ellipse([w * 0.74, h * 0.06, w * 0.74 + 130, h * 0.06 + 130], fill=(250, 246, 214))
        for i, (x0, bw, bh) in enumerate([(0, 210, 620), (190, 260, 480), (430, 200, 700), (610, 280, 540), (860, 240, 640)]):
            y0 = ground - bh
            d.rectangle([x0, y0, x0 + bw, ground], fill=(40 + i * 4, 44 + i * 4, 66 + i * 4))
            for wy in range(y0 + 40, ground - 40, 70):
                for wx in range(x0 + 24, x0 + bw - 30, 54):
                    on = ((wx * 7 + wy * 13 + i) % 5) < 2
                    d.rectangle([wx, wy, wx + 26, wy + 36], fill=(255, 214, 120) if on else (30, 34, 52))
        _floor(d, w, h, ground, (52, 54, 66))
        d.rectangle([0, ground, w, ground + 10], fill=(90, 92, 108))
        for x in range(0, w, 220):
            d.rectangle([x + 40, int(h * 0.88), x + 130, int(h * 0.89)], fill=(210, 206, 150))
        d.rectangle([int(w * 0.84), int(h * 0.50), int(w * 0.845), ground], fill=(30, 32, 40))                   # street lamp
        d.ellipse([int(w * 0.815), int(h * 0.47), int(w * 0.87), int(h * 0.51)], fill=(255, 238, 170))
        return im
    if key == "forest":
        im = _grad(w, h, (176, 214, 196), (222, 238, 214))
        d = ImageDraw.Draw(im)
        for layer, (col, base, hh) in enumerate([((130, 176, 150), 0.74, 0.34), ((86, 140, 110), 0.78, 0.40), ((52, 104, 78), 0.82, 0.48)]):
            for k in range(7):
                x = (k * 190 + layer * 70) % (w + 100) - 40
                tw = 40 + layer * 14
                d.rectangle([x - tw // 2, int(h * (base - hh * 0.0)) - 40, x + tw // 2, int(h * base) + 30], fill=(96, 72, 52))
                d.polygon([(x - 130, int(h * (base - 0.08))), (x + 130, int(h * (base - 0.08))), (x, int(h * (base - hh)))], fill=col)
                d.polygon([(x - 100, int(h * (base - 0.22))), (x + 100, int(h * (base - 0.22))), (x, int(h * (base - hh - 0.1)))], fill=col)
        _floor(d, w, h, int(h * 0.80), (86, 130, 82))
        return im
    if key == "room":
        im = Image.new("RGB", (w, h), (226, 214, 196))
        d = ImageDraw.Draw(im)
        _floor(d, w, h, ground, (176, 132, 92))
        d.rectangle([0, ground - 10, w, ground], fill=(150, 110, 76))
        _rect(d, (int(w * 0.56), int(h * 0.14), int(w * 0.92), int(h * 0.42)), (170, 214, 240), INK, 8)         # window
        d.line([int(w * 0.74), int(h * 0.14), int(w * 0.74), int(h * 0.42)], fill=INK, width=8)
        d.line([int(w * 0.56), int(h * 0.28), int(w * 0.92), int(h * 0.28)], fill=INK, width=8)
        _rect(d, (int(w * 0.05), int(h * 0.30), int(w * 0.30), int(h * 0.55)), (200, 150, 110), INK, 6)         # picture / shelf
        _rect(d, (int(w * 0.08), int(h * 0.34), int(w * 0.27), int(h * 0.51)), (120, 170, 150))
        _rect(d, (int(w * 0.05), int(h * 0.64), int(w * 0.34), ground), (150, 100, 70), INK, 6)                 # table
        return im
    if key == "rooftop":
        im = _grad(w, h, (255, 160, 110), (255, 220, 170))
        d = ImageDraw.Draw(im)
        d.ellipse([w * 0.30, h * 0.30, w * 0.30 + 280, h * 0.30 + 280], fill=(255, 246, 200))
        for i, (x0, bw, bh) in enumerate([(0, 180, 380), (150, 220, 260), (380, 160, 420), (520, 240, 300), (740, 200, 460), (900, 200, 340)]):
            d.rectangle([x0, int(h * 0.62) - bh // 2, x0 + bw, h], fill=(120 - i * 6, 84 - i * 4, 104 - i * 3))
        _floor(d, w, h, ground, (96, 92, 100))
        d.rectangle([0, ground - 30, w, ground], fill=(130, 126, 134))
        for x in range(20, w, 90):
            d.rectangle([x, ground - 90, x + 14, ground - 30], fill=(110, 106, 116))
        d.rectangle([0, ground - 96, w, ground - 82], fill=(110, 106, 116))
        return im
    if key == "desert":
        im = _grad(w, h, (250, 214, 150), (255, 240, 200))
        d = ImageDraw.Draw(im)
        d.ellipse([w * 0.66, h * 0.08, w * 0.66 + 190, h * 0.08 + 190], fill=(255, 250, 220))
        for off, col, amp in ((0.66, (232, 190, 120), 70), (0.72, (222, 170, 98), 90), (0.80, (206, 150, 84), 60)):
            pts = [(0, h)]
            for x in range(0, w + 40, 40):
                pts.append((x, int(h * off - amp * math.sin(x / 190.0 + off * 9))))
            pts.append((w, h))
            d.polygon(pts, fill=col)
        return im
    if key == "cave":
        im = _grad(w, h, (34, 30, 44), (66, 58, 78))
        d = ImageDraw.Draw(im)
        for x in range(0, w, 120):
            hh = 120 + (x * 37 % 190)
            d.polygon([(x, 0), (x + 120, 0), (x + 60, hh)], fill=(54, 48, 66))
        _floor(d, w, h, ground, (46, 42, 56))
        for x in range(60, w, 260):
            d.polygon([(x, ground), (x + 70, ground), (x + 36, ground - 90)], fill=(70, 64, 84))
        d.ellipse([w * 0.36, h * 0.18, w * 0.64, h * 0.30], fill=(255, 214, 120))
        return im
    if key == "lab":
        im = Image.new("RGB", (w, h), (214, 232, 238))
        d = ImageDraw.Draw(im)
        _floor(d, w, h, ground, (176, 196, 206))
        for x in range(0, w, 135):
            d.line([x, 0, x, ground], fill=(198, 218, 226), width=3)
        _rect(d, (int(w * 0.05), int(h * 0.55), int(w * 0.50), ground), (240, 244, 246), INK, 6)                  # bench
        for k, col in enumerate(((220, 90, 100), (90, 180, 120), (110, 150, 230))):                                # flasks
            x = int(w * (0.10 + 0.12 * k))
            d.polygon([(x + 20, int(h * 0.44)), (x + 52, int(h * 0.44)), (x + 74, int(h * 0.55)), (x - 2, int(h * 0.55))], fill=col, outline=INK)
        _rect(d, (int(w * 0.60), int(h * 0.14), int(w * 0.94), int(h * 0.50)), (30, 40, 56), INK, 8)             # screen
        d.line([int(w * 0.63), int(h * 0.40), int(w * 0.72), int(h * 0.30), int(w * 0.80), int(h * 0.36), int(w * 0.90), int(h * 0.20)], fill=(120, 240, 170), width=7)
        return im
    if key == "sewer":
        im = _grad(w, h, (52, 74, 66), (88, 110, 92))
        d = ImageDraw.Draw(im)
        for y in range(0, ground, 80):
            d.line([0, y, w, y], fill=(64, 88, 78), width=3)
        d.ellipse([w * 0.58, h * 0.20, w * 0.58 + 300, h * 0.20 + 300], fill=(30, 44, 40), outline=(100, 120, 112), width=10)   # big pipe
        _floor(d, w, h, ground, (60, 100, 90))
        for y in range(ground + 20, h, 60):
            d.line([0, y, w, y + 6], fill=(78, 124, 112), width=4)
        return im
    if key == "bridge":
        im = _grad(w, h, (170, 208, 240), (236, 244, 250))
        d = ImageDraw.Draw(im)
        _floor(d, w, h, int(h * 0.80), (70, 120, 170))
        d.rectangle([0, int(h * 0.66), w, int(h * 0.70)], fill=(96, 92, 100))
        d.rectangle([0, int(h * 0.70), w, int(h * 0.80)], fill=(70, 120, 170))
        for x in range(60, w, 150):
            d.rectangle([x, int(h * 0.70), x + 40, int(h * 0.80)], fill=(110, 106, 116))
            d.line([x + 20, int(h * 0.56), x + 20, int(h * 0.66)], fill=(60, 56, 64), width=8)
        d.line([0, int(h * 0.56), w, int(h * 0.56)], fill=(60, 56, 64), width=8)
        return im
    return _grad(w, h, (244, 241, 234), (226, 222, 212))


def render_file(key: str, folder: Path, w: int, h: int) -> Path:
    """The background as a PNG file (cached by key and size), for the puppet renderer's layers."""
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"bg_{key}_{w}x{h}.png"
    if not p.exists():
        draw(key, w, h).save(p)
    return p
