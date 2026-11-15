"""The cover engine: a spec -> the final layered picture, drawn with Pillow (no browser, no Django).

Flow: ``clean_spec`` checks the user's input -> ``render(spec, inputs)`` builds a ``Ctx`` (size, safe area, palette, texts) and the layout function
(``styles.STYLES[key].fn``) places the layers in order: background -> cut-out subject -> title -> decoration -> logo -> grain / vignette.
Every layer has a name and a box in the report (``RenderResult.layers``); ``keep_layers`` also keeps the layers themselves for a layered export.

The pictures (subject, background, logo) are prepared by the caller (``Inputs``); this module reads nothing from the database.

SOURCE: ported from NMarketing:backend/apps/thumbs/render.py @ v3.02 (c23f861), adapted for series/episode covers
(fields: series, episode, hook line, characters, channel; no price / product / store; both languages; warnings as fa+en pairs; layer names in English).
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from . import formats as F
from . import palette as pal_mod
from . import primitives as P
from . import typo
from .formats import Format

#: warnings of a render as (code -> (Persian, English)); the report carries the code and both texts
WARNINGS = {
    "no_subject": ("شخصیتی برای این کاور انتخاب نشده؛ به‌جایش یک تزئینِ ساده گذاشته شد. برای نتیجهٔ حرفه‌ای‌تر یک شخصیت (ترجیحاً بدونِ پس‌زمینه) انتخاب کنید.",
                   "No character is chosen for this cover; a plain decoration was used instead. For a more professional result pick a character (ideally without a background)."),
    "low_res_subject": ("کیفیتِ تصویرِ شخصیت برای این اندازه پایین است؛ تصویرِ بزرگ‌تر بهتر می‌شود.",
                        "The character picture is too small for this size; a larger picture will look better."),
}
MAX_TITLE, MAX_SUB, MAX_SHORT = 110, 140, 40
CONTENT_LIMITS = {"title": MAX_TITLE, "subtitle": MAX_SUB, "kicker": 34, "number": 6, "badge": 26, "tagline": 90, "credits": 260, "channel": 40,
                  "label_a": 24, "label_b": 24}
LOGO_POSITIONS = ("auto", "tl", "tr", "bl", "br", "bc", "tc")
BG_KINDS = ("auto", "gradient", "texture", "photo", "ai")
TEXTURES = ("", "halftone", "rays", "grid", "stripes", "grain")
SUBJECT_MODES = ("auto", "cutout", "photo")
SIDES = ("auto", "left", "right", "center")
LANGS = ("fa", "en")
#: words some layouts print by themselves when the user gave none: (Persian, English)
WORDS = {"after": ("بعد", "AFTER"), "before": ("قبل", "BEFORE"), "special": ("ویژه", "SPECIAL"), "versus": ("VS", "VS"), "qmark": ("؟", "?"),
         "episode": ("قسمت", "EPISODE"), "tbc": ("ادامه دارد…", "TO BE CONTINUED…"), "or": ("یا", "OR"), "letter_a": ("الف", "A"), "letter_b": ("ب", "B")}


class SpecError(ValueError):
    """An invalid input. ``fa`` / ``en`` carry the user-facing text; ``str()`` is the English one."""

    def __init__(self, fa: str, en: str):
        super().__init__(en)
        self.fa, self.en = fa, en


@dataclass
class Inputs:
    subject: Image.Image | None = None
    subject_is_cutout: bool = False
    subject2: Image.Image | None = None
    subject2_is_cutout: bool = False
    background: Image.Image | None = None
    logo: Image.Image | None = None
    brand_colors: list[str] = field(default_factory=list)
    channel_name: str = ""
    heading_font: str = ""            # the headline font of the series look's theme typography (when it maps to a bundled font)
    theme_roles: list[str] = field(default_factory=list)      # the 6 colour roles of the series look (background, primary, secondary, accent, shadow, highlight)
    extra: list[Image.Image] = field(default_factory=list)


@dataclass
class RenderResult:
    image: Image.Image
    layers: list[dict]
    warnings: list[str]
    size: tuple[int, int]
    texts: list[dict]
    palette: dict
    kept: list[dict] = field(default_factory=list)


# ───────────────────────────── the spec

def default_spec() -> dict:
    return {
        "format": F.DEFAULT_FORMAT, "style": "character_face", "lang": "fa",
        "content": {k: "" for k in CONTENT_LIMITS},
        "colors": {"mood": "", "primary": "", "secondary": "", "accent": "", "use_brand": True, "variation": 0},
        "font": typo.AUTO_FONT,
        "background": {"kind": "auto", "asset": None, "texture": "", "darken": 0.0, "blur": 0, "job": ""},
        "subject": {"asset": None, "character": None, "expression": "", "mode": "auto", "side": "auto", "scale": 1.0, "outline": True},
        "subject2": {"asset": None, "character": None, "expression": ""},
        "extra_assets": [],
        "logo": {"show": True, "position": "auto", "asset": None},
        "accents": {"arrow": True},
        "seed": 1,
        "guides": False,
    }


def _int_or_none(v):
    try:
        return int(v) if v not in (None, "", False) else None
    except (TypeError, ValueError):
        return None


def _expr(v) -> str:
    """The facial expression a stick character is drawn with (the engine only carries it; the caller draws the character)."""
    v = str(v or "").strip().lower()
    return v if re.fullmatch(r"[a-z_]{1,16}", v) else ""


def _num(v, lo, hi, default):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def clean_spec(raw, styles_registry) -> dict:
    """The user's input -> a clean spec (an unknown key is dropped; an unknown format / layout -> SpecError)."""
    d = raw if isinstance(raw, dict) else {}
    out = default_spec()
    fk = str(d.get("format") or out["format"])
    if fk not in F.FORMATS:
        raise SpecError("قالبِ ناشناخته است؛ از فهرستِ قالب‌ها یکی را انتخاب کنید.", "Unknown format; pick one from the list of formats.")
    out["format"] = fk
    sk = str(d.get("style") or out["style"])
    if sk not in styles_registry:
        raise SpecError("سبکِ ناشناخته است؛ از فهرستِ سبک‌ها یکی را انتخاب کنید.", "Unknown layout; pick one from the list of layouts.")
    out["style"] = sk
    out["lang"] = str(d.get("lang") or "fa") if str(d.get("lang") or "fa") in LANGS else "fa"
    c = d.get("content") if isinstance(d.get("content"), dict) else {}
    for k, lim in CONTENT_LIMITS.items():
        v = c.get(k)
        out["content"][k] = typo.clean(v if isinstance(v, (str, int, float)) and not isinstance(v, bool) else "")[:lim]
    col = d.get("colors") if isinstance(d.get("colors"), dict) else {}
    oc = out["colors"]
    oc["mood"] = col.get("mood") if col.get("mood") in pal_mod.MOODS else ""
    for k in ("primary", "secondary", "accent"):
        v = str(col.get(k) or "").strip().lower()
        oc[k] = v if pal_mod.colorx.is_hex(v) else ""
    oc["use_brand"] = bool(col.get("use_brand", True))
    oc["variation"] = int(_num(col.get("variation"), 0, 7, 0))
    f = str(d.get("font") or typo.AUTO_FONT)
    out["font"] = f if f in typo.FONT_CHOICES else typo.AUTO_FONT
    b = d.get("background") if isinstance(d.get("background"), dict) else {}
    ob = out["background"]
    ob["kind"] = b.get("kind") if b.get("kind") in BG_KINDS else "auto"
    ob["asset"] = _int_or_none(b.get("asset"))
    ob["texture"] = b.get("texture") if b.get("texture") in TEXTURES else ""
    ob["darken"] = round(_num(b.get("darken"), 0.0, 0.85, 0.0), 2)
    ob["blur"] = int(_num(b.get("blur"), 0, 40, 0))
    ob["job"] = str(b.get("job") or "")[:40]
    s = d.get("subject") if isinstance(d.get("subject"), dict) else {}
    os_ = out["subject"]
    os_["asset"] = _int_or_none(s.get("asset"))
    os_["mode"] = s.get("mode") if s.get("mode") in SUBJECT_MODES else "auto"
    os_["side"] = s.get("side") if s.get("side") in SIDES else "auto"
    os_["scale"] = round(_num(s.get("scale"), 0.5, 1.4, 1.0), 2)
    os_["outline"] = bool(s.get("outline", True))
    os_["character"] = _int_or_none(s.get("character"))
    os_["expression"] = _expr(s.get("expression"))
    s2 = d.get("subject2") if isinstance(d.get("subject2"), dict) else {}
    out["subject2"]["asset"] = _int_or_none(s2.get("asset"))
    out["subject2"]["character"] = _int_or_none(s2.get("character"))
    out["subject2"]["expression"] = _expr(s2.get("expression"))
    ex = d.get("extra_assets") if isinstance(d.get("extra_assets"), list) else []
    out["extra_assets"] = [i for i in (_int_or_none(x) for x in ex[:4]) if i]
    lg = d.get("logo") if isinstance(d.get("logo"), dict) else {}
    out["logo"]["show"] = bool(lg.get("show", True))
    out["logo"]["position"] = lg.get("position") if lg.get("position") in LOGO_POSITIONS else "auto"
    out["logo"]["asset"] = _int_or_none(lg.get("asset"))
    ac = d.get("accents") if isinstance(d.get("accents"), dict) else {}
    out["accents"]["arrow"] = bool(ac.get("arrow", True))
    out["seed"] = int(_num(d.get("seed"), 0, 99999, 1))
    out["guides"] = bool(d.get("guides", False))
    return out


# ───────────────────────────── the drawing context

class Placed:
    """Where a text / shape sat: the ink box and the nominal box."""

    def __init__(self, ink, nominal, block=None):
        self.ink, self.nominal, self.block = ink, nominal, block

    @property
    def bottom(self) -> float:
        return self.nominal[3]


class Ctx:
    def __init__(self, fmt: Format, spec: dict, inp: Inputs, size: tuple[int, int], keep: bool = False):
        self.fmt, self.spec, self.inp = fmt, spec, inp
        self.W, self.H = size
        self.k = self.W / 1080.0                       # scale factor relative to a width of 1080
        self.orient = fmt.orient
        self.comp = P.Composer(size, keep)
        self.warnings: list[dict] = []
        self.texts: list[dict] = []
        self.rnd = random.Random(spec.get("seed", 1))
        self.safe = F.safe_rect(fmt, size)
        self.avoid = F.avoid_rects(fmt, size)
        self.lang = spec.get("lang") if spec.get("lang") in LANGS else "fa"
        self.rtl = self.lang == "fa"
        self.content = {k: (typo.to_fa_digits(typo.clean(v)) if self.rtl else typo.clean(v)) for k, v in spec["content"].items()}
        self.font_key = "lalezar"
        self.pal: pal_mod.Palette = pal_mod.build("vivid")
        self.subject_side = "left"

    # --- sizes
    def u(self, v: float) -> float:
        """v pixels on a 1080-wide canvas -> pixels of this canvas."""
        return v * self.k

    @property
    def size(self):
        return (self.W, self.H)

    @property
    def start(self) -> str:
        """The side a line of text starts on: right for Persian, left for English."""
        return "right" if self.rtl else "left"

    def word(self, key: str) -> str:
        """A word a layout prints when the user gave none (AFTER / BEFORE / SPECIAL ...) in the language of the cover."""
        fa, en = WORDS[key]
        return fa if self.rtl else en

    def has(self, key: str) -> bool:
        return bool(typo.plain(self.content.get(key, "")))

    def rect(self, x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (x0 * self.W, y0 * self.H, x1 * self.W, y1 * self.H)

    # --- areas
    def avoid_rect(self, r: tuple[float, float, float, float], min_frac: float = 0.55):
        """Move r away from the avoid zones (the largest piece that is left)."""
        cur = tuple(r)
        for a in self.avoid:
            if not (cur[0] < a[2] and cur[2] > a[0] and cur[1] < a[3] and cur[3] > a[1]):
                continue
            cands = [(cur[0], cur[1], min(cur[2], a[0]), cur[3]), (max(cur[0], a[2]), cur[1], cur[2], cur[3]),
                     (cur[0], cur[1], cur[2], min(cur[3], a[1])), (cur[0], max(cur[1], a[3]), cur[2], cur[3])]
            cands = [c for c in cands if c[2] - c[0] > 4 and c[3] - c[1] > 4]
            if not cands:
                continue
            best = max(cands, key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
            if (best[2] - best[0]) * (best[3] - best[1]) >= min_frac * (cur[2] - cur[0]) * (cur[3] - cur[1]):
                cur = best
        return cur

    def clear_of_avoid(self, center: tuple[float, float], radius: float) -> tuple[float, float]:
        """Move the centre of a round badge out of the avoid zones (up or down, whichever is nearer)."""
        cx, cy = center
        for _ in range(4):
            hit = next((a for a in self.avoid if cx + radius > a[0] and cx - radius < a[2] and cy + radius > a[1] and cy - radius < a[3]), None)
            if hit is None:
                break
            cy = (hit[1] - radius - 4) if (hit[1] + hit[3]) / 2 > self.H / 2 else (hit[3] + radius + 4)
        return (min(max(cx, radius), self.W - radius), min(max(cy, radius), self.H - radius))

    def zones(self, sub_frac: float = 0.47, text_h: float = 0.40, overlap: float = 0.0) -> dict:
        """-> {text, subject, side}: the text area and the subject area (the subject reaches the canvas edge)."""
        x0, y0, x1, y1 = self.safe
        W, H = self.W, self.H
        side = self.subject_side
        if self.orient == "wide":
            sw = (x1 - x0) * sub_frac
            if side == "right":
                subj = (x1 - sw, 0.0, float(W), float(H))
                text = (x0, y0, x1 - sw + overlap * W, y1)
            else:
                subj = (0.0, 0.0, x0 + sw, float(H))
                text = (x0 + sw - overlap * W, y0, x1, y1)
        else:
            th = (y1 - y0) * text_h
            text = (x0, y0, x1, y0 + th)
            subj = (0.0, y0 + th * (0.95 - overlap * 0.4), float(W), float(H))   # the subject's head must not fall on the subtitle
        return {"text": self.avoid_rect(text), "subject": subj, "side": side}

    # --- layers
    def add(self, name, kind, img, xy=(0, 0), **kw):
        return self.comp.add(name, kind, img, xy, **kw)

    def center_add(self, name, kind, img, center, **kw):
        return self.comp.add(name, kind, img, (center[0] - img.width / 2, center[1] - img.height / 2), **kw)

    def text(self, name: str, text: str, rect, st: typo.TextStyle, *, max_lines: int = 3, min_f: float = 0.03, max_f: float = 0.16,
             ax: str = "center", ay: str = "middle", avoid: bool = True, opacity: float = 1.0, blend: str = "normal",
             deco: bool = False, post=None, ink_center: bool = False) -> Placed | None:
        """``deco=True`` -> decorative text (a giant question mark ...): the logo / badge may sit on it and it does not count in collisions."""
        text = typo.clean(text)
        if not typo.plain(text):
            return None
        if avoid:
            rect = self.avoid_rect(rect)
        bw, bh = rect[2] - rect[0], rect[3] - rect[1]
        if bw < 8 or bh < 8:
            return None
        if not st.font_key:
            st.font_key = self.font_key
        blk = typo.render_text(text, bw, bh, st, max_lines=max_lines, min_px=max(8, int(min_f * self.W)), max_px=max(10, int(max_f * self.W)))
        if blk is None:
            return None
        if post is not None:                          # a layout may reshape the finished text picture (e.g. fade the end of the last line)
            blk.img = post(blk.img, blk)
        xy = typo.place(blk, rect, ax, ay)
        if ink_center and blk.ink:                    # centre the visible ink (not the font's line box) in rect: digits and letters inside a disc
            xy = (int(round((rect[0] + rect[2]) / 2 - (blk.ink[0] + blk.ink[2]) / 2)), int(round((rect[1] + rect[3]) / 2 - (blk.ink[1] + blk.ink[3]) / 2)))
        bbox = self.comp.add(name, "text", blk.img, xy, opacity=opacity, blend=blend)
        nominal = (xy[0] + blk.origin[0], xy[1] + blk.origin[1], xy[0] + blk.origin[0] + blk.nominal[0], xy[1] + blk.origin[1] + blk.nominal[1])
        if bbox:
            self.texts.append({"name": name, "bbox": list(bbox), "px": blk.px, "lines": blk.lines, "text": typo.plain(text),
                               **({"deco": True} if deco else {})})
        return Placed(bbox, nominal, blk)

    def stack(self, rect, items: list[tuple[str, float]]) -> dict[str, tuple[float, float, float, float]]:
        """Split rect vertically between the NON-EMPTY items (by weight). -> {key: rect}."""
        used = [(k, w) for k, w in items if (k.startswith("_") and w > 0) or self.has(k)]
        if not used:
            return {}
        tot = sum(w for _, w in used)
        y = rect[1]
        out = {}
        for k, w in used:
            h = (rect[3] - rect[1]) * w / tot
            out[k] = (rect[0], y, rect[2], y + h)
            y += h
        return out

    def label(self, name: str, text: str, center=None, xy=None, px: float = 40, **kw):
        img = typo.label(text, int(px), **kw)
        if img is None:
            return None
        if center is not None:
            bb = self.center_add(name, "badge", img, center)
        else:
            bb = self.comp.add(name, "badge", img, xy or (0, 0))
        return img, bb

    # --- collisions
    def obstacles(self) -> list[tuple[tuple[float, float, float, float], float, bool]]:
        """-> [(box, weight, hard?)]: texts and badges are "hard" (nothing may sit on them), the subject and the arrow are "soft".
        Decorative text (``deco``) does not count."""
        out: list[tuple[tuple[float, float, float, float], float, bool]] = []
        for t in self.texts:
            if not t.get("deco"):
                out.append((tuple(t["bbox"]), 1.0, True))
        for lay in self.comp.report:
            k, bb = lay["kind"], tuple(lay["bbox"])
            if k == "badge":
                out.append((bb, 1.0, True))
            elif k in ("subject", "photo"):
                out.append((bb, 0.12, False))
            elif k == "accent" and "arrow" in lay["name"]:
                out.append((bb, 0.5, False))
        return out

    @staticmethod
    def _overlap(a, b) -> float:
        ix = min(a[2], b[2]) - max(a[0], b[0])
        iy = min(a[3], b[3]) - max(a[1], b[1])
        return ix * iy if ix > 0 and iy > 0 else 0.0

    def fit_badge(self, center: tuple[float, float], radius: float) -> tuple[float, float]:
        """Move a round badge (when it falls on a text or another badge) to the nearest free place; always outside the avoid zones."""
        hard = [b for b, _, h in self.obstacles() if h]
        reach = radius + self.u(6)                                 # a little distance from the text

        def hits(pt) -> float:
            """Total "depth of intrusion" of the circle into the hard boxes (0 = no collision anywhere)."""
            tot = 0.0
            for o in hard:
                dx = max(o[0] - pt[0], 0.0, pt[0] - o[2])
                dy = max(o[1] - pt[1], 0.0, pt[1] - o[3])
                d = math.hypot(dx, dy)
                if d < reach:
                    tot += reach - d
            return tot

        base = self.clear_of_avoid(center, radius)
        if hits(base) == 0:
            return base
        x0, y0, x1, y1 = self.safe
        cands = [base]
        step = radius * 0.55
        for ring in range(1, 8):
            for k in range(16):
                ang = k * math.pi / 8
                cands.append(self.clear_of_avoid((center[0] + math.cos(ang) * ring * step, center[1] + math.sin(ang) * ring * step), radius))
        for pt in ((x0 + radius, y0 + radius), (x1 - radius, y0 + radius), (x0 + radius, y1 - radius), (x1 - radius, y1 - radius)):
            cands.append(self.clear_of_avoid(pt, radius))
        free = [pt for pt in cands if hits(pt) == 0]
        if free:
            return min(free, key=lambda pt: (pt[0] - center[0]) ** 2 + (pt[1] - center[1]) ** 2)
        return min(cands, key=lambda pt: (hits(pt), (pt[0] - center[0]) ** 2 + (pt[1] - center[1]) ** 2))

    # --- backgrounds
    def bg_wants_photo(self) -> bool:
        return self.spec["background"]["kind"] in ("photo", "ai") and self.inp.background is not None

    def bg_photo(self, *, darken: float = 0.0, blur: float = 0.0, tint: str | None = None, saturate: float = 1.0, grade: float = 0.0,
                 vign: float = 0.0, focus=(0.5, 0.5)) -> None:
        bg = P.cover(self.inp.background.convert("RGB"), self.size, focus)
        ub = self.spec["background"]
        dark = max(darken, ub.get("darken", 0.0))
        bl = max(blur, ub.get("blur", 0))
        if bl:
            from PIL import ImageFilter

            bg = bg.filter(ImageFilter.GaussianBlur(self.u(bl)))
        if grade:
            bg = P.grade_teal_orange(bg, grade)
        if saturate != 1.0:
            bg = P.adjust(bg, saturation=saturate)
        if tint:
            bg = P.darken(bg, 0.18, tint)
        if dark:
            bg = P.darken(bg, dark)
        if vign:
            bg = P.vignette(bg, vign)
        self.add("background photo", "background", bg)

    def scrim(self, rect, strength: float = 0.55, grow: float = 0.05, color: str = "#000000") -> None:
        """A soft shade behind the text area when the background is a photo. When it is busy under the text (a picture with its own text or many
        details) that area is also blurred a little like frosted glass so the title stays readable."""
        import numpy as np
        from PIL import ImageFilter

        x0, y0, x1, y1 = rect
        pad = int(min(self.W, self.H) * grow)
        feather = max(4, int(min(self.W, self.H) * 0.06))
        bw, bh = int(x1 - x0) + 2 * pad, int(y1 - y0) + 2 * pad
        if bw < 16 or bh < 16:
            return
        m = Image.new("L", (bw + 4 * feather, bh + 4 * feather), 0)
        ImageDraw.Draw(m).rectangle([2 * feather, 2 * feather, 2 * feather + bw, 2 * feather + bh], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(feather))
        ox, oy = int(x0) - pad - 2 * feather, int(y0) - pad - 2 * feather
        # how busy it is: the mean size of the brightness gradient in the area itself
        box = (max(0, int(x0)), max(0, int(y0)), min(self.W, int(x1)), min(self.H, int(y1)))
        busy = 0.0
        if box[2] - box[0] > 8 and box[3] - box[1] > 8:
            arr = np.asarray(self.comp.canvas.crop(box).convert("L"), dtype=np.float32)
            gy, gx = np.gradient(arr)
            busy = float(np.hypot(gx, gy).mean()) * (1080.0 / max(1, self.W))
        if busy > 4.5:
            strength = min(0.8, strength + 0.18)
            soft = self.comp.canvas.filter(ImageFilter.GaussianBlur(max(2.0, self.W * 0.011)))
            self.comp.canvas.paste(soft, (0, 0), self._full_mask(m, (ox, oy)))
        self.add("text scrim", "fx", P.solid(m.size, color, m, strength), (ox, oy))

    def _full_mask(self, m: Image.Image, xy: tuple[int, int]) -> Image.Image:
        full = Image.new("L", self.size, 0)
        full.paste(m, xy)
        return full

    def bg_gradient(self, angle: float = 35.0, stops=None, name: str = "background") -> None:
        stops = stops or [(0.0, self.pal.bg1), (1.0, self.pal.bg2)]
        self.add(name, "background", P.gradient(self.size, stops, angle))

    def texture(self, kind: str, color: str | None = None, alpha: float = 0.16, center=None, **kw) -> None:
        col = color or self.pal.text
        if kind == "halftone":
            self.add("texture halftone", "texture", P.halftone(self.size, col, alpha, spacing=self.u(kw.get("spacing", 22)), angle=kw.get("angle", 30),
                                                            direction=kw.get("direction", 90)))
        elif kind == "rays":
            self.add("rays", "texture", P.rays(self.size, center or (self.W * 0.5, self.H * 0.5), kw.get("n", 18), col, alpha, kw.get("rot", 0)))
        elif kind == "stripes":
            self.add("texture stripes", "texture", P.stripes(self.size, col, alpha * 0.6, self.u(kw.get("width", 46)), kw.get("angle", 35)))
        elif kind == "grid":
            self.add("texture grid", "texture", self._grid(col, alpha))
        elif kind == "grain":
            pass                                     # the grain is applied to the whole canvas at the end

    def _grid(self, color: str, alpha: float) -> Image.Image:
        img = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        step = max(8, int(self.u(54)))
        a = int(255 * alpha)
        for x in range(0, self.W, step):
            d.line([(x, 0), (x, self.H)], fill=P.rgba(color, a), width=max(1, int(self.u(1.4))))
        for y in range(0, self.H, step):
            d.line([(0, y), (self.W, y)], fill=P.rgba(color, a), width=max(1, int(self.u(1.4))))
        return img

    def auto_texture(self, default: str, **kw) -> None:
        kind = self.spec["background"]["texture"] or default
        self.texture(kind, **kw)

    # --- subject
    def subject_rgba(self, which: int = 1) -> tuple[Image.Image | None, bool]:
        img = self.inp.subject if which == 1 else self.inp.subject2
        cut = self.inp.subject_is_cutout if which == 1 else self.inp.subject2_is_cutout
        if img is None:
            return None, False
        mode = self.spec["subject"]["mode"] if which == 1 else "auto"
        if mode == "photo":
            cut = False
        elif mode == "cutout" and not cut:
            cut = False       # an uncut picture also comes as a photo (the exact cut is the cutout step before rendering)
        return img, cut

    def put_cutout(self, name: str, img: Image.Image, rect, *, valign: str = "bottom", halign: str = "center", scale: float = 1.0,
                   flip: bool = False, outline: str | None = None, ow: float = 0.0, shadow: bool = True, glow: tuple | None = None,
                   rim: str | None = None, max_w_frac: float = 1.0) -> tuple[int, int, int, int] | None:
        """Put the cut-out subject in rect (sized to fit, times ``scale``) -> the visible box."""
        sub = P.crop_to_alpha(img, pad=0)
        if flip:
            sub = sub.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        rw, rh = rect[2] - rect[0], rect[3] - rect[1]
        s = scale * self.spec["subject"]["scale"]
        tw, th = rw * max_w_frac * s, rh * s
        src_w = sub.width
        sub = P.contain(sub, tw, th)
        if sub.width / max(1.0, float(src_w)) > 1.9:
            self._warn_once("low_res_subject")
        if ow > 0 or shadow or glow or rim:
            sub, off = P.sticker(sub, ow, outline or "#ffffff", shadow=(self.u(6), self.u(10), self.u(14), "#000000", 0.45) if shadow else None,
                                 glow=glow, rim=rim)
        else:
            off = (0, 0)
        if halign == "left":
            x = rect[0]
        elif halign == "right":
            x = rect[2] - (sub.width - off[0] * 2)
        else:
            x = (rect[0] + rect[2]) / 2 - (sub.width - off[0] * 2) / 2
        y = rect[3] - (sub.height - off[1] * 2) if valign == "bottom" else (rect[1] if valign == "top" else (rect[1] + rect[3]) / 2 - (sub.height - off[1] * 2) / 2)
        return self.comp.add(name, "subject", sub, (x - off[0], y - off[1]))

    def put_photo(self, name: str, img: Image.Image, rect, *, fade: str | None = None, extent: float = 0.35, focus=(0.5, 0.35),
                  radius: float = 0.0, border: str | None = None, bw: float = 0.0, rot: float = 0.0, shadow: bool = False):
        """A photo without cutting the subject out (cover in rect) with an edge fade (fade: top/bottom/left/right) or a rounded card."""
        rw, rh = int(rect[2] - rect[0]), int(rect[3] - rect[1])
        if rw < 4 or rh < 4:
            return None
        ph = P.cover(img.convert("RGB"), (rw, rh), focus).convert("RGBA")
        mask = Image.new("L", (rw, rh), 255)
        if radius:
            mask = P.rounded_mask((rw, rh), radius)
        if fade:
            ramp = P.edge_ramp((rw, rh), fade, extent, 0.0, 1.0)
            # the ramp goes to zero from the fade side inwards; we want the fade edge to be transparent
            ramp = ramp.point(lambda v: 255 - v)
            from PIL import ImageChops

            mask = ImageChops.multiply(mask, ramp)
        ph.putalpha(mask)
        if border and bw:
            pad = int(bw)
            frame = Image.new("RGBA", (rw + 2 * pad, rh + 2 * pad), (0, 0, 0, 0))
            fm = P.rounded_mask((rw + 2 * pad, rh + 2 * pad), radius + pad) if radius else Image.new("L", (rw + 2 * pad, rh + 2 * pad), 255)
            frame = Image.alpha_composite(frame, P.solid(frame.size, border, fm))
            frame.alpha_composite(ph, (pad, pad))
            ph = frame
        if shadow:
            m = ph.getchannel("A")
            sh = P.soft_shadow(ph.size, m, self.u(4), self.u(10), self.u(14), "#000000", 0.4)
            canvas = Image.new("RGBA", (ph.width + int(self.u(60)), ph.height + int(self.u(60))), (0, 0, 0, 0))
            o = int(self.u(30))
            canvas.alpha_composite(sh, (o, o))
            canvas.alpha_composite(ph, (o, o))
            ph = canvas
            rect = (rect[0] - o, rect[1] - o, rect[2], rect[3])
        if abs(rot) > 0.01:
            ph = ph.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        return self.center_add(name, "photo", ph, (cx, cy))

    def _warn_once(self, code: str) -> None:
        if all(w["code"] != code for w in self.warnings):
            fa, en = WARNINGS[code]
            self.warnings.append({"code": code, "fa": fa, "en": en})

    def warn_no_subject(self) -> None:
        self._warn_once("no_subject")

    # --- logo
    def _logo_tile(self, scale: float = 1.0) -> Image.Image:
        side = int(self.W * (0.12 if self.orient != "tall" else 0.16) * scale)
        img = P.crop_to_alpha(self.inp.logo.convert("RGBA"))
        logo = P.contain(img, side, side * 0.8)
        pad = max(2, int(self.u(16) * (0.5 + 0.5 * scale)))
        tile = Image.new("RGBA", (logo.width + 2 * pad, logo.height + 2 * pad), (0, 0, 0, 0))
        m = P.rounded_mask(tile.size, pad * 1.1)
        tile = Image.alpha_composite(tile, P.solid(tile.size, "#ffffff", m, 0.92))
        tile.alpha_composite(logo, (pad, pad))
        return tile

    def _logo_xy(self, pos: str, tile: Image.Image) -> tuple[float, float]:
        x0, y0, x1, y1 = self.safe
        cx = {"tl": x0, "bl": x0, "tr": x1 - tile.width, "br": x1 - tile.width, "tc": (self.W - tile.width) / 2, "bc": (self.W - tile.width) / 2}[pos]
        cy = {"tl": y0, "tr": y0, "tc": y0, "bl": y1 - tile.height, "br": y1 - tile.height, "bc": y1 - tile.height}[pos]
        return cx, cy

    def _logo_slides(self, tile: Image.Image, near: tuple[float, float]) -> list[tuple[float, float]]:
        """Other places on the edge of the safe area (beside the corners): slides along the top / bottom / left / right edges; the nearest to the wanted corner first."""
        x0, y0, x1, y1 = self.safe
        pts: list[tuple[float, float]] = []
        for i in range(9):
            x = x0 + (x1 - x0 - tile.width) * i / 8
            pts += [(x, y0), (x, y1 - tile.height)]
        for j in range(1, 6):
            y = y0 + (y1 - y0 - tile.height) * j / 6
            pts += [(x0, y), (x1 - tile.width, y)]
        return sorted(pts, key=lambda q: (q[0] - near[0]) ** 2 + (q[1] - near[1]) ** 2)

    def _auto_logo(self) -> tuple[Image.Image, tuple[float, float]]:
        """The "automatic" logo place: see ``_auto_place`` (the logo tile of each scale; corners first, top-left for wide / square, top-right for tall)."""
        order = ("tl", "tr", "bl", "br", "tc", "bc") if self.orient in ("wide", "square") else ("tr", "tl", "br", "bl", "tc", "bc")
        return self._auto_place(self._logo_tile, order)

    def _auto_place(self, make_tile, order, soft: bool = True) -> tuple[Image.Image, tuple[float, float]]:
        """The "automatic" place of a small tile (logo, channel tag): somewhere that does not fall on the title, subtitle, labels, badges or the platform's avoid zones
        (and preferably not on the subject; ``soft=False`` lets it sit over the subject, like a watermark).

        Order of preference: the corners in ``order`` at full size, the corners at 82%, sliding along the edges, then smaller sizes (66%, 52%, 40%) in the same order.
        A layout that does not fit even at 40% takes the place with the fewest collisions. A square logo makes a taller tile than a wide one and a busy layout
        (the magazine cover at 16:9) has few free corners, which is why sliding and a smaller size are needed. ``make_tile(scale)`` builds the tile."""
        obs = self.obstacles()
        margin = self.u(10)
        stages = [(1.0, False), (0.82, False), (1.0, True), (0.82, True), (0.66, False), (0.66, True), (0.52, False), (0.52, True), (0.4, False), (0.4, True)]
        best: tuple[float, int, Image.Image, tuple[float, float]] | None = None
        tiles: dict[float, Image.Image] = {}
        for si, (scale, slide) in enumerate(stages):
            tile = tiles.setdefault(scale, make_tile(scale))
            area = float(tile.width * tile.height)
            first = self._logo_xy(order[0], tile)
            cands = self._logo_slides(tile, first) if slide else [self._logo_xy(pos, tile) for pos in order]
            for oi, (x, y) in enumerate(cands):
                box = (x, y, x + tile.width, y + tile.height)
                bigger = (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)
                hard = sum(self._overlap(bigger, b) for b, _, h in obs if h)
                hard += sum(self._overlap(box, a) for a in self.avoid)
                soft_hit = sum(self._overlap(box, b) * w for b, w, h in obs if not h) if soft else 0.0
                score = hard + (soft_hit if soft_hit > 0.3 * area * 0.12 else 0.0)
                if score == 0:
                    return tile, (x, y)
                key = (score, si * 100 + oi)
                if best is None or key < (best[0], best[1]):
                    best = (score, si * 100 + oi, tile, (x, y))
        assert best is not None
        return best[2], best[3]

    def put_channel(self) -> None:
        """The channel name as a small label in a free corner of the safe area (never over the title or a badge)."""
        name = typo.plain(self.content.get("channel", ""))
        if not name:
            return
        px = max(10, int(self.W * 0.026))
        bg = P.lerp_hex(self.pal.bg1, "#000000", 0.35) if self.pal.dark else P.lerp_hex(self.pal.paper, "#ffffff", 0.2)
        fg = self.pal.text if self.pal.dark else self.pal.ink

        def tile(scale: float) -> Image.Image:
            return typo.label(name, max(8, int(px * scale)), font_key="sahel", weight=800, fill=fg, bg=bg, pad_x=0.8, pad_y=0.3, shadow=False)

        order = ("bl", "br", "tl", "tr")
        img, xy = self._auto_place(tile, order, soft=False)
        self.comp.add("channel tag", "badge", img, xy)

    def put_logo(self) -> None:
        lg = self.spec["logo"]
        if not lg["show"] or self.inp.logo is None:
            return
        pos = lg["position"]
        if pos == "auto" and getattr(self, "emblem_drawn", False):
            return
        if pos == "auto":
            tile, (cx, cy) = self._auto_logo()
        else:
            tile = self._logo_tile()
            x0, y0, x1, y1 = self.safe
            cx, cy = self._logo_xy(pos, tile)
            box = (cx, cy, cx + tile.width, cy + tile.height)
            for a in self.avoid:                                 # a manual place must not fall on an avoid zone: it goes to the opposite corner
                if box[0] < a[2] and box[2] > a[0] and box[1] < a[3] and box[3] > a[1]:
                    cx = x1 - tile.width if cx < self.W / 2 else x0
                    break
        self.comp.add("logo", "logo", tile, (cx, cy))

    def finish(self, grain_amount: float = 0.0, vign: float = 0.0) -> None:
        if vign:
            self.comp.replace(P.vignette(self.comp.canvas, vign))
        if grain_amount or self.spec["background"]["texture"] == "grain":
            self.comp.replace(P.grain(self.comp.canvas, grain_amount or 0.03, self.spec.get("seed", 1)))


# ───────────────────────────── running

def draw_guides(img: Image.Image, fmt: Format) -> Image.Image:
    """The safe-area guide (green) and the avoid zones (red) drawn on a copy; for the preview only."""
    out = img.convert("RGBA")
    ov = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    x0, y0, x1, y1 = F.safe_rect(fmt, out.size)
    d.rectangle([x0, y0, x1, y1], outline=(34, 197, 94, 230), width=max(2, out.width // 320))
    for a in F.avoid_rects(fmt, out.size):
        d.rectangle(a, fill=(239, 68, 68, 70), outline=(239, 68, 68, 230), width=max(2, out.width // 320))
    return Image.alpha_composite(out, ov).convert("RGB")


def render(spec: dict, inputs: Inputs | None = None, *, scale: float = 1.0, keep_layers: bool = False, guides: bool | None = None
           ) -> RenderResult:
    from . import styles

    inp = inputs or Inputs()
    fmt = F.get(spec["format"])
    sd = styles.STYLES[spec["style"]]
    size = F.scaled(fmt, scale)
    c = Ctx(fmt, spec, inp, size, keep_layers)
    oc = spec["colors"]
    brand = inp.brand_colors if oc.get("use_brand", True) else []
    mood = oc.get("mood") or sd.mood
    ov = {"primary": oc.get("primary"), "secondary": oc.get("secondary"), "accent": oc.get("accent")}
    if oc.get("use_brand", True) and inp.theme_roles and not (oc.get("primary") or oc.get("secondary")):
        c.pal = pal_mod.from_theme(inp.theme_roles, mood, {"accent": oc.get("accent")} if oc.get("accent") else None, int(oc.get("variation") or 0))
    else:
        c.pal = pal_mod.build(mood, brand, ov, int(oc.get("variation") or 0))
    if spec["font"] != typo.AUTO_FONT:
        c.font_key = spec["font"]
    elif oc.get("use_brand", True) and inp.heading_font in typo.FONT_CHOICES:
        c.font_key = inp.heading_font
    else:
        c.font_key = sd.font
    side = spec["subject"]["side"]
    if side == "auto":
        base = "left" if c.rtl else "right"                       # Persian reads right to left: the text on the right, the subject on the left
        side = base if int(oc.get("variation") or 0) % 2 == 0 else ("right" if base == "left" else "left")      # version B puts the subject on the other side
    c.subject_side = "left" if side == "center" else side
    sd.fn(c)
    if inp.subject is None and sd.subject == "recommended":
        c.warn_no_subject()
    c.put_channel()
    c.put_logo()
    img = c.comp.canvas
    if (guides if guides is not None else spec.get("guides")):
        img = draw_guides(img, fmt)
    return RenderResult(image=img, layers=c.comp.report, warnings=c.warnings, size=size, texts=c.texts, palette=c.pal.public(),
                        kept=c.comp.layers)


def to_jpeg_bytes(img: Image.Image, quality: int = 86, max_kb: int = 0) -> bytes:
    import io

    q = quality
    while True:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 88 else 2)
        data = buf.getvalue()
        if not max_kb or len(data) <= max_kb * 1024 or q <= 50:
            return data
        q -= 8
