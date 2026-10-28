"""A procedurally drawn demo character and parallax background (Pillow only).

Used for demo mode, tests and as a visible starting point: the owner can render a puppet shot before any character sheet exists.
It is a placeholder, never presented as a generated character.
"""
from __future__ import annotations

import colorsys
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .rig import MOUTH_SHAPES

SS = 3  # supersampling for smooth edges
DESIGN = (600, 900)
ANCHOR = (300, 880)


def _palette(name: str) -> dict:
    h = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:6], 16)
    hue = (h % 360) / 360.0

    def c(hh, s, v):
        r, g, b = colorsys.hsv_to_rgb(hh % 1.0, s, v)
        return int(r * 255), int(g * 255), int(b * 255), 255
    return {"skin": c(0.07 + (h % 5) * 0.004, 0.32, 0.96), "shirt": c(hue, 0.65, 0.85), "pants": c(hue + 0.55, 0.45, 0.45), "hair": c(0.06 + (h % 3) * 0.05, 0.6, 0.28),
            "line": (40, 28, 30, 255), "white": (252, 250, 246, 255), "mouth": (120, 30, 40, 255), "tongue": (226, 100, 110, 255)}


def _canvas(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _done(im: Image.Image, w: int, h: int) -> Image.Image:
    return im.resize((w, h), Image.LANCZOS)


def _rr(d, box, r, fill, outline=None, width=0):
    d.rounded_rectangle([v * SS for v in box], radius=r * SS, fill=fill, outline=outline, width=width * SS)


def _ell(d, box, fill, outline=None, width=0):
    d.ellipse([v * SS for v in box], fill=fill, outline=outline, width=width * SS)


def _mouth(shape: str, pal: dict) -> Image.Image:
    w, h = 90, 60
    im, d = _canvas(w, h)
    L, M, T, W = pal["line"], pal["mouth"], pal["tongue"], pal["white"]
    cx, cy = w / 2, h / 2
    if shape == "X":
        d.line([(cx - 14) * SS, cy * SS, (cx + 14) * SS, cy * SS], fill=L, width=4 * SS)
    elif shape == "A":
        d.line([(cx - 20) * SS, cy * SS, (cx + 20) * SS, cy * SS], fill=L, width=6 * SS)
    elif shape == "B":
        _ell(d, (cx - 20, cy - 6, cx + 20, cy + 8), M, L, 3)
        _rr(d, (cx - 15, cy - 5, cx + 15, cy + 1), 2, W)
    elif shape == "C":
        _ell(d, (cx - 22, cy - 12, cx + 22, cy + 14), M, L, 3)
        _rr(d, (cx - 15, cy - 11, cx + 15, cy - 4), 2, W)
    elif shape == "D":
        _ell(d, (cx - 25, cy - 20, cx + 25, cy + 22), M, L, 3)
        _rr(d, (cx - 17, cy - 19, cx + 17, cy - 10), 2, W)
        _ell(d, (cx - 14, cy + 6, cx + 14, cy + 22), T)
    elif shape == "E":
        _ell(d, (cx - 14, cy - 17, cx + 14, cy + 17), M, L, 3)
    elif shape == "F":
        _ell(d, (cx - 9, cy - 9, cx + 9, cy + 9), M, L, 3)
    elif shape == "G":
        _ell(d, (cx - 20, cy - 8, cx + 20, cy + 10), M, L, 3)
        _rr(d, (cx - 16, cy - 7, cx + 16, cy), 2, W)
        _rr(d, (cx - 14, cy + 1, cx + 14, cy + 6), 3, pal["skin"])
    elif shape == "H":
        _ell(d, (cx - 21, cy - 11, cx + 21, cy + 13), M, L, 3)
        _rr(d, (cx - 15, cy - 10, cx + 15, cy - 4), 2, W)
        _ell(d, (cx - 9, cy - 2, cx + 9, cy + 10), T)
    return _done(im, w, h)


def make_rig_images(name: str, folder: Path) -> dict[str, Path]:
    """Draw every part into `folder` and return {part name: path}."""
    folder.mkdir(parents=True, exist_ok=True)
    pal = _palette(name)
    out: dict[str, Image.Image] = {}

    im, d = _canvas(70, 230)   # legs
    _rr(d, (8, 0, 62, 205), 14, pal["pants"], pal["line"], 3)
    _rr(d, (2, 196, 68, 228), 14, (60, 50, 60, 255), pal["line"], 3)
    out["leg_l"] = out["leg_r"] = _done(im, 70, 230)

    im, d = _canvas(220, 290)  # body
    _rr(d, (10, 10, 210, 285), 46, pal["shirt"], pal["line"], 4)
    _rr(d, (84, 8, 136, 40), 14, pal["skin"], pal["line"], 3)
    out["body"] = _done(im, 220, 290)

    im, d = _canvas(60, 230)   # arm
    _rr(d, (8, 4, 52, 190), 22, pal["shirt"], pal["line"], 3)
    _ell(d, (6, 176, 54, 226), pal["skin"], pal["line"], 3)
    out["arm_l"] = out["arm_r"] = _done(im, 60, 230)

    im, d = _canvas(280, 280)  # head
    _ell(d, (20, 12, 260, 268), pal["skin"], pal["line"], 4)
    _ell(d, (14, 0, 266, 150), pal["hair"], pal["line"], 4)
    _rr(d, (16, 70, 264, 150), 20, pal["hair"])
    _ell(d, (20, 118, 260, 268), pal["skin"])
    _ell(d, (20, 12, 260, 268), None, pal["line"], 4)
    out["head"] = _done(im, 280, 280)

    for state in ("open", "closed"):
        im, d = _canvas(160, 50)
        for cx in (38, 122):
            if state == "open":
                _ell(d, (cx - 20, 4, cx + 20, 46), pal["white"], pal["line"], 3)
                _ell(d, (cx - 9, 14, cx + 9, 38), (50, 40, 30, 255))
                _ell(d, (cx - 4, 17, cx + 2, 23), pal["white"])
            else:
                d.arc([(cx - 20) * SS, 8 * SS, (cx + 20) * SS, 40 * SS], 20, 160, fill=pal["line"], width=5 * SS)
        out[f"eyes_{state}"] = _done(im, 160, 50)

    im, d = _canvas(170, 30)
    for x0 in (14, 98):
        d.line([x0 * SS, 18 * SS, (x0 + 58) * SS, 10 * SS], fill=pal["hair"], width=7 * SS)
    out["brows_neutral"] = _done(im, 170, 30)

    for s in MOUTH_SHAPES:
        out[f"mouth_{s}"] = _mouth(s, pal)
    paths = {}
    for n, img in out.items():
        paths[n] = folder / f"{n}.png"
        img.save(paths[n])
    return paths


def make_rig_spec(name: str, folder: Path, media_root: Path) -> dict:
    """Draw the demo character into `folder` (inside the media folder) and return the rig spec (relative image paths)."""
    paths = make_rig_images(name, folder)

    def rel(n: str) -> str:
        return str(paths[n].relative_to(media_root)).replace("\\", "/")

    parts: dict[str, dict] = {
        "leg_l": {"image": rel("leg_l"), "pivot": [35, 8], "pos": [262, 660], "z": 5, "parent": None},
        "leg_r": {"image": rel("leg_r"), "pivot": [35, 8], "pos": [338, 660], "z": 6, "parent": None},
        "body": {"image": rel("body"), "pivot": [110, 280], "pos": [300, 672], "z": 10, "parent": None},
        "arm_l": {"image": rel("arm_l"), "pivot": [30, 24], "pos": [20, 56], "z": 12, "parent": "body"},
        "arm_r": {"image": rel("arm_r"), "pivot": [30, 24], "pos": [200, 56], "z": 30, "parent": "body"},
        "head": {"image": rel("head"), "pivot": [140, 270], "pos": [110, 24], "z": 20, "parent": "body"},
        "eyes_open": {"image": rel("eyes_open"), "pivot": [80, 25], "pos": [140, 140], "z": 21, "parent": "head", "group": "eyes", "state": "open"},
        "eyes_closed": {"image": rel("eyes_closed"), "pivot": [80, 25], "pos": [140, 140], "z": 21, "parent": "head", "group": "eyes", "state": "closed"},
        "brows_neutral": {"image": rel("brows_neutral"), "pivot": [85, 15], "pos": [140, 98], "z": 22, "parent": "head", "group": "brows", "state": "neutral"},
    }
    for s in MOUTH_SHAPES:
        parts[f"mouth_{s}"] = {"image": rel(f"mouth_{s}"), "pivot": [45, 30], "pos": [140, 212], "z": 23, "parent": "head", "group": "mouth", "state": s}
    return {"version": 1, "size": list(DESIGN), "anchor": list(ANCHOR), "parts": parts}


def make_background(folder: Path, width: int = 1080, height: int = 1920, seed: str = "demo") -> list[dict]:
    """Three parallax layers (sky, hills, grass) as PNG files; returns layer specs for the renderer."""
    folder.mkdir(parents=True, exist_ok=True)
    pal = _palette(seed)
    sky = Image.new("RGB", (width, height))
    px = ImageDraw.Draw(sky)
    top, bot = (110, 170, 235), (250, 225, 190)
    for y in range(height):
        k = y / height
        px.line([(0, y), (width, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    px.ellipse((width * 0.62, height * 0.12, width * 0.62 + 170, height * 0.12 + 170), fill=(255, 245, 205))
    sky_p = folder / "bg_sky.png"
    sky.save(sky_p)
    hills = Image.new("RGBA", (width * SS // 2, height * SS // 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(hills)
    base = int(height * SS / 2 * 0.62)
    import math

    for x in range(0, hills.width, 4):
        y = base - int(60 * SS / 2 * (math.sin(x / (300.0 * SS / 2)) + 0.6 * math.sin(x / (120.0 * SS / 2) + 1.3)))
        d.rectangle((x, y, x + 4, hills.height), fill=(80, 140, 110, 255))
    hills = hills.resize((width, height), Image.LANCZOS)
    hills_p = folder / "bg_hills.png"
    hills.save(hills_p)
    grass = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(grass)
    d.rectangle((0, int(height * 0.9), width, height), fill=pal["pants"][:3] + (255,))
    d.rectangle((0, int(height * 0.9), width, int(height * 0.9) + 14), fill=(60, 110, 70, 255))
    grass = grass.filter(ImageFilter.GaussianBlur(0.6))
    grass_p = folder / "bg_front.png"
    grass.save(grass_p)
    return [{"image": str(sky_p), "parallax": 0.12}, {"image": str(hills_p), "parallax": 0.45}, {"image": str(grass_p), "parallax": 1.25, "front": True}]
