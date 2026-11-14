"""The identity of a stick-figure character, as data.

A stick figure is the strongest answer to "keep the character identical on every page, image and video": it is DRAWN by code from this
spec (colours, head, accessories), so the same spec gives the same character in every pose, scene, still and video clip - by
construction, not by hoping a model remembers. The spec also yields the English identity anchor and the colour key that the image-model
route uses when the owner prefers an AI picture of the same character (see instai/identity).

Characters are always ORIGINAL: the library offers colours and accessories, never a named character.
"""
from __future__ import annotations

import hashlib
from typing import Any

PALETTE_NAMES = {
    "#1f2430": "ink", "#d94a3d": "red", "#2f7fd1": "blue", "#2e9e5b": "green", "#e8a22b": "amber", "#8a4fd1": "violet", "#e0568f": "pink",
    "#1ba0a8": "teal", "#f26b21": "orange", "#6b7280": "grey", "#ffffff": "white", "#f4f1ea": "paper", "#b0763c": "brown",
}
LIMB_COLOURS = ["#1f2430", "#d94a3d", "#2f7fd1", "#2e9e5b", "#e8a22b", "#8a4fd1", "#e0568f", "#1ba0a8", "#f26b21"]
HEAD_STYLES = ("round", "tall", "wide")
EYE_STYLES = ("dots", "round", "sleepy")
HATS = ("none", "cap", "beanie", "headband", "tophat", "hood")
HAIRS = ("none", "tuft", "spikes", "bob", "ponytail")
NECK = ("none", "scarf", "tie", "bowtie")
EXTRAS = ("none", "glasses", "backpack", "mask")
PROPS = ("none", "torch", "phone", "key", "bat", "sign", "map")
EXPRESSIONS = ("neutral", "happy", "laugh", "sad", "angry", "scared", "surprised", "smirk")

DEFAULTS: dict[str, Any] = {
    "name": "", "limb_colour": "#1f2430", "head_fill": "#ffffff", "outline": "#1f2430", "line_width": 17,
    "head_style": "round", "eye_style": "round", "hat": "none", "hat_colour": "#d94a3d", "hair": "none", "hair_colour": "#1f2430",
    "neck": "none", "neck_colour": "#d94a3d", "extra": "none", "extra_colour": "#2f7fd1", "prop": "none", "prop_colour": "#e8a22b",
}
CHOICES = {"head_style": HEAD_STYLES, "eye_style": EYE_STYLES, "hat": HATS, "hair": HAIRS, "neck": NECK, "extra": EXTRAS, "prop": PROPS}
COLOUR_KEYS = ("limb_colour", "head_fill", "outline", "hat_colour", "hair_colour", "neck_colour", "extra_colour", "prop_colour")


def _hex(v: Any, default: str) -> str:
    s = str(v or "").strip().lower()
    if len(s) == 4 and s[0] == "#":
        s = "#" + "".join(c * 2 for c in s[1:])
    ok = len(s) == 7 and s[0] == "#" and all(c in "0123456789abcdef" for c in s[1:])
    return s if ok else default


def normalize(data: dict | None, *, name: str = "") -> dict:
    """A complete, safe spec: unknown keys dropped, choices clamped, colours validated; a missing look is derived from the name so that
    two characters of one page do not come out identical."""
    d = dict(data or {})
    out = dict(DEFAULTS)
    out["name"] = str(d.get("name") or name or "")[:80]
    seed = int(hashlib.sha256((out["name"] or "x").encode("utf-8")).hexdigest()[:8], 16)
    if "limb_colour" not in d:
        out["limb_colour"] = LIMB_COLOURS[seed % len(LIMB_COLOURS)]
    for k in COLOUR_KEYS:
        if k in d:
            out[k] = _hex(d[k], out[k])
    for k, allowed in CHOICES.items():
        if d.get(k) in allowed:
            out[k] = d[k]
    if "hat" not in d and "neck" not in d and "extra" not in d and name:      # a first look for a brand-new character
        out["neck"] = ("scarf", "tie", "none")[(seed >> 3) % 3]
        out["hat"] = ("none", "cap", "beanie")[(seed >> 5) % 3]
        out["neck_colour"] = LIMB_COLOURS[(seed >> 7) % len(LIMB_COLOURS) or 1] if out["neck"] != "none" else out["neck_colour"]
    try:
        out["line_width"] = max(10, min(26, int(d.get("line_width", out["line_width"]))))
    except (TypeError, ValueError):
        pass
    return out


def hex_rgba(h: str, a: int = 255) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a


def colour_name(h: str) -> str:
    """The nearest named colour of the small studio palette (for prompts and the model sheet)."""
    r, g, b, _ = hex_rgba(h)
    best, dist = "ink", 10 ** 9
    for k, nm in PALETTE_NAMES.items():
        kr, kg, kb, _ = hex_rgba(k)
        d = (r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2
        if d < dist:
            best, dist = nm, d
    return best


def palette(spec: dict) -> list[dict]:
    """The colour key of the character: [{role, hex, name}] for every colour that is really used."""
    s = normalize(spec)
    rows = [("limbs", s["limb_colour"]), ("head", s["head_fill"]), ("outline", s["outline"])]
    if s["hat"] != "none":
        rows.append(("hat", s["hat_colour"]))
    if s["hair"] != "none":
        rows.append(("hair", s["hair_colour"]))
    if s["neck"] != "none":
        rows.append(("neck", s["neck_colour"]))
    if s["extra"] != "none":
        rows.append(("extra", s["extra_colour"]))
    seen, out = set(), []
    for role, hx in rows:
        out.append({"role": role, "hex": hx, "name": colour_name(hx)})
        seen.add(hx)
    return out


def _a(word: str) -> str:
    """The English indefinite article for the word that follows ("an amber beanie", "a blue cap")."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def anchor_text(spec: dict) -> str:
    """The English identity descriptor of the character: the same words every time, for every prompt that must show this character."""
    s = normalize(spec)
    limb, head = colour_name(s["limb_colour"]), colour_name(s["head_fill"])
    bits = [f"{_a(limb)} {limb}-limbed stick figure with {_a(head)} {head} {s['head_style']} head, thick {colour_name(s['outline'])} outlines,"
            f" {'dot' if s['eye_style'] == 'dots' else s['eye_style']} eyes"]
    if s["hat"] != "none":
        hat = colour_name(s["hat_colour"])
        bits.append(f"{_a(hat)} {hat} {s['hat']}")
    if s["hair"] != "none":
        bits.append(f"{colour_name(s['hair_colour'])} {s['hair']} hair")
    if s["neck"] != "none":
        neck = colour_name(s["neck_colour"])
        bits.append(f"{_a(neck)} {neck} {s['neck']}")
    if s["extra"] != "none":
        bits.append(f"{s['extra']}")
    return ", ".join(bits)


def spec_hash(spec: dict) -> str:
    s = normalize(spec)
    return hashlib.sha256(repr(sorted(s.items())).encode()).hexdigest()[:12]
