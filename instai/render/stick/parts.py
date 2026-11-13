"""Draw the parts of a stick-figure rig (Pillow only) in the format of instai.render.puppet.rig.

Part names are the ones the puppet motion library already drives (body, head, arm_l/arm_r, leg_l/leg_r, eyes_*, brows_*, mouth_*), plus
forearm_*/shin_* children (elbows and knees) that older motions simply ignore. The figure faces right; the renderer flips it for left.
Everything is drawn at 3x and shrunk, so edges are smooth at any size.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from instai.render.puppet.rig import MOUTH_SHAPES

from . import spec as S

SS = 3
DESIGN = (600, 900)
HIP = (300, 540)
ANCHOR = (300, 862)
TORSO, UPPER, FORE, THIGH, SHIN = 240, 118, 108, 160, 150

_EXPR = {   # expression -> (brows, eyes, mouth X variant, mouth shape for talking-less stills)
    "neutral": ("flat", "round", "flat", "X"), "happy": ("up", "round", "smile", "X"), "laugh": ("up", "happy", "smile", "D"),
    "sad": ("sad", "down", "frown", "X"), "angry": ("angry", "narrow", "clench", "X"), "scared": ("worry", "wide", "flat", "E"),
    "surprised": ("high", "wide", "flat", "F"), "smirk": ("smirk", "round", "smirk", "X"),
}


def expression_parts(expression: str) -> tuple[str, str, str, str]:
    return _EXPR.get(expression) or _EXPR["neutral"]


def _canvas(w: int, h: int):
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _done(im: Image.Image, w: int, h: int) -> Image.Image:
    return im.resize((w, h), Image.LANCZOS)


def _s(pts):
    return [(x * SS, y * SS) for x, y in pts]


def _line(d, pts, width, fill):
    """A polyline with round caps and round joints."""
    d.line(_s(pts), fill=fill, width=int(width * SS), joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=fill)


def _ell(d, box, fill=None, outline=None, width=0):
    d.ellipse([v * SS for v in box], fill=fill, outline=outline, width=int(width * SS))


def _rr(d, box, r, fill=None, outline=None, width=0):
    d.rounded_rectangle([v * SS for v in box], radius=r * SS, fill=fill, outline=outline, width=int(width * SS))


def _poly(d, pts, fill=None, outline=None, width=0):
    d.polygon(_s(pts), fill=fill, outline=outline)
    if outline and width:
        d.line(_s(pts + [pts[0]]), fill=outline, width=int(width * SS), joint="curve")


def _head_dims(style: str) -> tuple[float, float]:
    return {"round": (78, 78), "tall": (68, 90), "wide": (90, 70)}[style]


# ------------------------------------------------------------------ limbs and body

def _body(s: dict) -> Image.Image:
    w, h = 220, 300
    im, d = _canvas(w, h)
    c, W = S.hex_rgba(s["limb_colour"]), s["line_width"]
    top, hip = 40, 40 + TORSO
    cx = 110
    if s["extra"] == "backpack":                                   # behind the torso
        _rr(d, (cx - 62, top + 14, cx - 6, top + 150), 14, S.hex_rgba(s["extra_colour"]), S.hex_rgba(s["outline"]), 5)
        _line(d, [(cx - 10, top + 30), (cx - 8, top + 110)], 8, S.hex_rgba(s["outline"]))
    _line(d, [(cx, top), (cx, hip)], W, c)
    if s["neck"] == "scarf":
        nc = S.hex_rgba(s["neck_colour"])
        _rr(d, (cx - 24, top - 4, cx + 24, top + 26), 12, nc, S.hex_rgba(s["outline"]), 4)
        _poly(d, [(cx - 12, top + 20), (cx - 40, top + 62), (cx - 22, top + 70), (cx - 2, top + 28)], nc, S.hex_rgba(s["outline"]), 4)
    elif s["neck"] == "tie":
        nc = S.hex_rgba(s["neck_colour"])
        _poly(d, [(cx - 11, top + 8), (cx + 11, top + 8), (cx + 7, top + 22), (cx + 16, top + 86), (cx, top + 104), (cx - 16, top + 86), (cx - 7, top + 22)],
              nc, S.hex_rgba(s["outline"]), 3)
    elif s["neck"] == "bowtie":
        nc = S.hex_rgba(s["neck_colour"])
        _poly(d, [(cx, top + 14), (cx - 30, top - 2), (cx - 30, top + 30)], nc, S.hex_rgba(s["outline"]), 3)
        _poly(d, [(cx, top + 14), (cx + 30, top - 2), (cx + 30, top + 30)], nc, S.hex_rgba(s["outline"]), 3)
        _ell(d, (cx - 8, top + 6, cx + 8, top + 22), nc, S.hex_rgba(s["outline"]), 3)
    return _done(im, w, h)


def _limb(s: dict, length: float, *, hand: bool = False, foot: bool = False, shin_taper: bool = False) -> Image.Image:
    w, h = 80, int(length + 36)
    im, d = _canvas(w, h)
    c, W = S.hex_rgba(s["limb_colour"]), s["line_width"]
    x = 40
    y0, y1 = 14, 14 + length
    _line(d, [(x, y0), (x, y1)], W, c)
    if hand:
        _ell(d, (x - 11, y1 - 5, x + 11, y1 + 17), S.hex_rgba(s["head_fill"]), S.hex_rgba(s["outline"]), 4)
    if foot:
        _line(d, [(x, y1), (x + 34, y1 + 2)], W, c)
    return _done(im, w, h)


def _prop(s: dict) -> Image.Image | None:
    kind = s["prop"]
    if kind == "none":
        return None
    w, h = 220, 220
    im, d = _canvas(w, h)
    pc, oc = S.hex_rgba(s["prop_colour"]), S.hex_rgba(s["outline"])
    cx = 110
    if kind == "torch":
        _rr(d, (cx - 12, 70, cx + 12, 160), 8, S.hex_rgba("#4b5563"), oc, 4)
        _poly(d, [(cx - 22, 70), (cx + 22, 70), (cx + 36, 30), (cx - 36, 30)], pc, oc, 4)
    elif kind == "phone":
        _rr(d, (cx - 22, 40, cx + 22, 130), 8, S.hex_rgba("#2b3040"), oc, 4)
        _rr(d, (cx - 16, 50, cx + 16, 116), 4, S.hex_rgba("#bfe3ff"))
    elif kind == "key":
        _ell(d, (cx - 22, 30, cx + 22, 74), None, pc, 9)
        _line(d, [(cx, 74), (cx, 150)], 9, pc)
        _line(d, [(cx, 128), (cx + 20, 128)], 8, pc)
        _line(d, [(cx, 144), (cx + 14, 144)], 8, pc)
    elif kind == "bat":
        _poly(d, [(cx - 8, 150), (cx + 8, 150), (cx + 18, 20), (cx - 18, 20)], S.hex_rgba("#b0763c"), oc, 4)
    elif kind == "sign":
        _line(d, [(cx, 70), (cx, 190)], 9, S.hex_rgba("#b0763c"))
        _rr(d, (cx - 56, 10, cx + 56, 80), 8, S.hex_rgba("#f4f1ea"), oc, 5)
    elif kind == "map":
        _poly(d, [(cx - 44, 50), (cx + 44, 40), (cx + 44, 140), (cx - 44, 150)], S.hex_rgba("#f4f1ea"), oc, 4)
        _line(d, [(cx - 26, 80), (cx - 4, 100), (cx + 24, 76)], 5, pc)
    return _done(im, w, h)


# ------------------------------------------------------------------ head and face

def _head(s: dict) -> Image.Image:
    w, h = 230, 230
    im, d = _canvas(w, h)
    rx, ry = _head_dims(s["head_style"])
    cx, cy = 115, 120
    oc, fill = S.hex_rgba(s["outline"]), S.hex_rgba(s["head_fill"])
    hair = S.hex_rgba(s["hair_colour"])
    if s["hair"] == "ponytail":
        _line(d, [(cx - rx + 8, cy - 10), (cx - rx - 30, cy + 20), (cx - rx - 26, cy + 56)], 20, hair)
    if s["extra"] == "mask":
        pass
    _ell(d, (cx - rx, cy - ry, cx + rx, cy + ry), fill, oc, 6)
    if s["extra"] == "mask":
        _poly(d, [(cx - rx + 6, cy + 4), (cx + rx - 6, cy + 4), (cx + rx - 18, cy + ry - 12), (cx - rx + 18, cy + ry - 12)], S.hex_rgba(s["extra_colour"]), oc, 4)
    top = cy - ry
    if s["hair"] == "tuft":
        _line(d, [(cx - 6, top + 6), (cx - 12, top - 22), (cx + 6, top - 10), (cx + 10, top - 30)], 8, hair)
    elif s["hair"] == "spikes":
        for dx in (-34, -12, 12, 34):
            _poly(d, [(cx + dx - 10, top + 16), (cx + dx, top - 22), (cx + dx + 10, top + 16)], hair, oc, 3)
    elif s["hair"] == "bob":
        _poly(d, [(cx - rx - 2, cy + 10), (cx - rx + 6, top + 8), (cx, top - 8), (cx + rx - 6, top + 8), (cx + rx + 2, cy + 10),
                  (cx + rx - 14, cy + 8), (cx + rx - 22, top + 30), (cx - rx + 22, top + 30), (cx - rx + 14, cy + 8)], hair, oc, 4)
    hat, hc = s["hat"], S.hex_rgba(s["hat_colour"])
    if hat == "cap":
        d.pieslice([(cx - rx - 3) * SS, (top - 24) * SS, (cx + rx + 3) * SS, (top + 74) * SS], 180, 360, fill=hc, outline=oc, width=4 * SS)
        _rr(d, (cx + 8, top + 22, cx + rx + 34, top + 36), 7, hc, oc, 4)
    elif hat == "beanie":
        d.pieslice([(cx - rx - 3) * SS, (top - 30) * SS, (cx + rx + 3) * SS, (top + 70) * SS], 180, 360, fill=hc, outline=oc, width=4 * SS)
        _rr(d, (cx - rx - 4, top + 22, cx + rx + 4, top + 40), 6, hc, oc, 4)
        _ell(d, (cx - 12, top - 44, cx + 12, top - 20), hc, oc, 4)
    elif hat == "headband":
        _rr(d, (cx - rx - 2, top + 28, cx + rx + 2, top + 48), 8, hc, oc, 4)
    elif hat == "tophat":
        _rr(d, (cx - rx - 10, top + 6, cx + rx + 10, top + 24), 6, hc, oc, 4)
        _rr(d, (cx - rx + 14, top - 50, cx + rx - 14, top + 12), 6, hc, oc, 4)
    elif hat == "hood":
        _poly(d, [(cx - rx - 8, cy + 30), (cx - rx + 4, top - 6), (cx, top - 22), (cx + rx - 4, top - 6), (cx + rx + 8, cy + 30),
                  (cx + rx - 14, cy - 8), (cx - rx + 14, cy - 8)], hc, oc, 4)
    return _done(im, w, h)


def _eyes(s: dict, kind: str) -> Image.Image:
    w, h = 160, 56
    im, d = _canvas(w, h)
    oc = S.hex_rgba(s["outline"])
    style = s["eye_style"]
    for cx in (46, 116):
        if kind == "closed" or kind == "happy":
            d.arc([(cx - 17) * SS, (12 if kind == "closed" else 18) * SS, (cx + 17) * SS, (38 if kind == "closed" else 46) * SS],
                  20 if kind == "closed" else 200, 160 if kind == "closed" else 340, fill=oc, width=6 * SS)
            continue
        if style == "dots":
            r = 8 if kind != "wide" else 6
            _ell(d, (cx - r, 28 - r, cx + r, 28 + r), oc)
            continue
        er = {"round": 17, "sleepy": 15}[style]
        ry = er
        py = 28
        if kind == "wide":
            er, ry = 21, 23
        elif kind == "narrow":
            ry = er * 0.55
        elif kind == "down":
            py = 32
        _ell(d, (cx - er, 28 - ry, cx + er, 28 + ry), S.hex_rgba("#ffffff"), oc, 4)
        pr = 7 if kind != "wide" else 4.5
        _ell(d, (cx + 4 - pr, py - pr, cx + 4 + pr, py + pr), oc)
        if style == "sleepy" and kind not in ("wide",):
            d.rectangle([(cx - er - 2) * SS, (28 - ry - 2) * SS, (cx + er + 2) * SS, 26 * SS], fill=S.hex_rgba(s["head_fill"]))
            _line(d, [(cx - er, 26), (cx + er, 26)], 4, oc)
    return _done(im, w, h)


def _brows(s: dict, kind: str) -> Image.Image:
    w, h = 170, 40
    im, d = _canvas(w, h)
    c = S.hex_rgba(s["outline"])
    spec = {   # (left brow: inner->outer), (right brow)
        "flat": ([(22, 22), (58, 22)], [(112, 22), (148, 22)]), "up": ([(22, 18), (58, 14)], [(112, 14), (148, 18)]),
        "sad": ([(22, 12), (58, 22)], [(112, 22), (148, 12)]), "angry": ([(22, 10), (60, 24)], [(110, 24), (148, 10)]),
        "worry": ([(24, 26), (60, 12)], [(110, 12), (146, 26)]), "high": ([(22, 12), (58, 8)], [(112, 8), (148, 12)]),
        "smirk": ([(22, 20), (58, 20)], [(112, 24), (148, 12)]),
    }[kind]
    for pts in spec:
        _line(d, pts, 7, c)
    return _done(im, w, h)


def _mouth(s: dict, shape: str, variant: str = "flat") -> Image.Image:
    w, h = 110, 70
    im, d = _canvas(w, h)
    oc, red, white = S.hex_rgba(s["outline"]), S.hex_rgba("#9b2c3a"), S.hex_rgba("#ffffff")
    cx, cy = 55, 34
    if shape == "X":
        if variant == "smile":
            d.arc([(cx - 28) * SS, (cy - 24) * SS, (cx + 28) * SS, (cy + 14) * SS], 20, 160, fill=oc, width=7 * SS)
        elif variant == "frown":
            d.arc([(cx - 24) * SS, (cy - 2) * SS, (cx + 24) * SS, (cy + 34) * SS], 200, 340, fill=oc, width=7 * SS)
        elif variant == "smirk":
            _line(d, [(cx - 22, cy + 4), (cx + 6, cy + 6), (cx + 24, cy - 8)], 7, oc)
        elif variant == "clench":
            _rr(d, (cx - 24, cy - 8, cx + 24, cy + 10), 5, white, oc, 5)
            _line(d, [(cx - 24, cy + 1), (cx + 24, cy + 1)], 4, oc)
        else:
            _line(d, [(cx - 18, cy), (cx + 18, cy)], 7, oc)
    elif shape == "A":
        _line(d, [(cx - 24, cy), (cx + 24, cy)], 8, oc)
    elif shape == "B":
        _ell(d, (cx - 22, cy - 7, cx + 22, cy + 9), red, oc, 5)
    elif shape == "C":
        _ell(d, (cx - 24, cy - 13, cx + 24, cy + 15), red, oc, 5)
    elif shape == "D":
        _ell(d, (cx - 28, cy - 18, cx + 28, cy + 22), red, oc, 5)
        _rr(d, (cx - 20, cy - 17, cx + 20, cy - 8), 3, white)
    elif shape == "E":
        _ell(d, (cx - 16, cy - 20, cx + 16, cy + 20), red, oc, 5)
    elif shape == "F":
        _ell(d, (cx - 10, cy - 10, cx + 10, cy + 10), red, oc, 5)
    elif shape == "G":
        _ell(d, (cx - 22, cy - 9, cx + 22, cy + 11), red, oc, 5)
        _rr(d, (cx - 17, cy - 8, cx + 17, cy), 3, white)
    elif shape == "H":
        _ell(d, (cx - 23, cy - 12, cx + 23, cy + 14), red, oc, 5)
        _ell(d, (cx - 10, cy, cx + 10, cy + 12), S.hex_rgba("#e0707c"))
    return _done(im, w, h)


def _glasses(s: dict) -> Image.Image:
    w, h = 190, 70
    im, d = _canvas(w, h)
    c = S.hex_rgba(s["extra_colour"])
    for cx in (50, 140):
        _ell(d, (cx - 28, 8, cx + 28, 62), None, c, 7)
    _line(d, [(78, 34), (112, 34)], 7, c)
    return _done(im, w, h)


# ------------------------------------------------------------------ the rig

def make_images(spec: dict, folder: Path, expression: str = "neutral") -> dict[str, Path]:
    """Draw every part of the character into `folder`; the face follows `expression`."""
    s = S.normalize(spec)
    folder.mkdir(parents=True, exist_ok=True)
    brows, eyes, mouth_x, _shape = expression_parts(expression)
    out: dict[str, Image.Image] = {"body": _body(s), "head": _head(s)}
    upper, fore = _limb(s, UPPER), _limb(s, FORE, hand=True)
    out["arm_l"] = out["arm_r"] = upper
    out["forearm_l"] = out["forearm_r"] = fore
    out["leg_l"] = out["leg_r"] = _limb(s, THIGH)
    out["shin_l"] = out["shin_r"] = _limb(s, SHIN, foot=True)
    out["eyes_open"] = _eyes(s, eyes)
    out["eyes_closed"] = _eyes(s, "closed")
    out["brows_neutral"] = _brows(s, brows)
    for shape in MOUTH_SHAPES:
        out[f"mouth_{shape}"] = _mouth(s, shape, mouth_x if shape == "X" else "flat")
    if s["extra"] == "glasses":
        out["glasses"] = _glasses(s)
    prop = _prop(s)
    if prop is not None:
        out["prop"] = prop
    paths: dict[str, Path] = {}
    for name, img in out.items():
        paths[name] = folder / f"{name}.png"
        img.save(paths[name])
    return paths


def make_rig_spec(spec: dict, folder: Path, media_root: Path, expression: str = "neutral") -> dict:
    """The rig JSON (image paths relative to `media_root`) of the character, with its stick spec stored under "stick"."""
    s = S.normalize(spec)
    paths = make_images(s, folder, expression)

    def rel(n: str) -> str:
        return str(paths[n].relative_to(media_root)).replace("\\", "/")

    arm_len, fore_len = UPPER, FORE
    parts: dict[str, dict] = {
        "leg_l": {"image": rel("leg_l"), "pivot": [40, 14], "pos": [HIP[0] - 9, HIP[1]], "z": 5, "parent": None},
        "leg_r": {"image": rel("leg_r"), "pivot": [40, 14], "pos": [HIP[0] + 9, HIP[1]], "z": 6, "parent": None},
        "shin_l": {"image": rel("shin_l"), "pivot": [40, 14], "pos": [40, 14 + THIGH], "z": 5, "parent": "leg_l"},
        "shin_r": {"image": rel("shin_r"), "pivot": [40, 14], "pos": [40, 14 + THIGH], "z": 6, "parent": "leg_r"},
        "body": {"image": rel("body"), "pivot": [110, 40 + TORSO], "pos": list(HIP), "z": 10, "parent": None},
        "arm_l": {"image": rel("arm_l"), "pivot": [40, 14], "pos": [110, 46], "z": 12, "parent": "body"},
        "arm_r": {"image": rel("arm_r"), "pivot": [40, 14], "pos": [110, 46], "z": 30, "parent": "body"},
        "forearm_l": {"image": rel("forearm_l"), "pivot": [40, 14], "pos": [40, 14 + arm_len], "z": 12, "parent": "arm_l"},
        "forearm_r": {"image": rel("forearm_r"), "pivot": [40, 14], "pos": [40, 14 + arm_len], "z": 30, "parent": "arm_r"},
        "head": {"image": rel("head"), "pivot": [115, 120 + _head_dims(s["head_style"])[1]], "pos": [110, 40], "z": 20, "parent": "body"},
        "eyes_open": {"image": rel("eyes_open"), "pivot": [80, 28], "pos": [115, 112], "z": 21, "parent": "head", "group": "eyes", "state": "open"},
        "eyes_closed": {"image": rel("eyes_closed"), "pivot": [80, 28], "pos": [115, 112], "z": 21, "parent": "head", "group": "eyes", "state": "closed"},
        "brows_neutral": {"image": rel("brows_neutral"), "pivot": [85, 20], "pos": [115, 82], "z": 22, "parent": "head", "group": "brows", "state": "neutral"},
    }
    if "glasses" in paths:
        parts["glasses"] = {"image": rel("glasses"), "pivot": [95, 35], "pos": [115, 112], "z": 24, "parent": "head"}
    if "prop" in paths:
        parts["prop"] = {"image": rel("prop"), "pivot": [110, 150], "pos": [40, 14 + fore_len], "z": 31, "parent": "forearm_r"}
    for shape in MOUTH_SHAPES:
        parts[f"mouth_{shape}"] = {"image": rel(f"mouth_{shape}"), "pivot": [55, 34], "pos": [115, 146], "z": 23, "parent": "head", "group": "mouth", "state": shape}
    return {"version": 1, "size": list(DESIGN), "anchor": list(ANCHOR), "parts": parts, "stick": s}
