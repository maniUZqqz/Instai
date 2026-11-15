"""Text clips as an ASS script for ffmpeg's libass: Persian shaping and bidi, wrapping inside the frame, strokes, shadows, a background box, entrance /
exit animations and a karaoke highlight of the word being spoken. Used by the caption presets (`instai/render/captions.py`).

SOURCE: ported from NMarketing:backend/services/editing/titles.py @ v3.02 (c23f861), adapted for InstAI captions: the title templates (lower thirds,
sticker, bubble, quote), the second text line, the motion-track path and the browser preview helpers are left out; fonts are the Vazirmatn files bundled in
instai/render/fonts (SIL OFL, so the picture is the same on every PC, including a Windows PC without the font); text width is measured with the same shaper
as the rest of InstAI's Persian pictures (`fa_text`); an explicit text direction (an RLM / LRM at the start of every line) replaces NM's "first strong
letter" rule so a Persian line that starts with a number or a Latin word keeps its right-to-left order.

**Two jobs.** `clean` turns whatever a caller sends into one fully-populated, clamped dict. `build_ass` turns a list of cleaned dicts into ONE ASS document
that the renderer feeds to the `ass` filter. Nothing else in InstAI knows ASS tags.

**Sizes are fractions of the frame.** `size` 6 = 6 % of the frame height; the ASS is generated against the real render size (PlayRes = width x height), so
the same style renders identically at a 360p preview and 1080p. ASS's own `Fontsize` is the font's *line* height, not its em, and the ratio differs per font
(Vazirmatn's lines are about 1.7 em tall): `FONTS[..]["line"]` holds the measured ratio so `size` keeps meaning "em as % of the frame height"
(tests/test_captions_render.py measures it again on the real libass).

**Animation is piecewise-linear.** Every in/out preset is a function `state(t)` (opacity, scale, offset, blur, revealed characters). The clip's time is cut
at the preset's breakpoints (and at karaoke word boundaries) and each slice becomes one dialogue whose `\\move`/`\\t` interpolates linearly between the
slice's two states: ease-out slides, an overshooting pop, typewriter reveal and the karaoke highlight with one mechanism and no tag soup that libass
versions disagree about.

**User text can never inject ASS.** Braces and backslashes are escaped; `\\N`-style sequences cannot be typed in.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

from . import contrast

FONTS_DIR = Path(__file__).parent / "fonts"
RLM, LRM = "\u200f", "\u200e"       # right-to-left / left-to-right mark: force the paragraph direction of a line


class CaptionError(ValueError):
    """A caption clip that cannot be drawn (no text)."""


# ----------------------------------------------------------------- catalogue

#: key -> `family` is the name libass resolves (from the font file's own name table, found through `fontsdir`); `line` is ASS Fontsize / em (measured by
#: rendering a capital H with libass and with Pillow); `bold` says whether the Bold flag is meaningful (the Black/Light cuts are separate families).
FONTS: dict[str, dict] = {
    "vazir": {"fa": "وزیرمتن", "en": "Vazirmatn", "family": "Vazirmatn", "bold": True, "line": 1.713, "file": "Vazirmatn-Regular.ttf", "bold_file": "Vazirmatn-Bold.ttf"},
    "vazir_black": {"fa": "وزیرمتن سیاه", "en": "Vazirmatn Black", "family": "Vazirmatn Black", "bold": False, "line": 1.713, "file": "Vazirmatn-Black.ttf", "bold_file": "Vazirmatn-Black.ttf"},
    "vazir_light": {"fa": "وزیرمتن نازک", "en": "Vazirmatn Light", "family": "Vazirmatn Light", "bold": False, "line": 1.711, "file": "Vazirmatn-Light.ttf", "bold_file": "Vazirmatn-Light.ttf"},
}
FONT_FILES = sorted({v[k] for v in FONTS.values() for k in ("file", "bold_file")})

ANIMATIONS_IN = ("none", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "pop", "zoom", "typewriter", "blur")
ANIMATIONS_OUT = ANIMATIONS_IN
HL_MODES = ("color", "scale", "box")             # colour of the word / colour + a little bigger / a marker behind it
ALIGNS = ("right", "center", "left")
DIRECTIONS = ("auto", "rtl", "ltr")
POSITION_Y = {"top": 0.12, "middle": 0.5, "bottom": 0.86}
MAX_TEXT = 400
MAX_WORDS = 400
#: libass breaks a line a few pixels earlier than a plain width sum says (the outline and the shaper's own rounding): a line that is within 5 % of the
#: wrap width is counted as too wide, so the estimated number of lines is never LOWER than the number libass draws (measured in tests/test_captions_render.py).
WRAP_SAFETY = 0.95

_BASE: dict = {
    "text": "", "at": 0.0, "duration": 2.5, "font": "vazir", "size": 6.0, "bold": True, "italic": False, "color": "#FFFFFF", "opacity": 1.0,
    "stroke_color": "#000000", "stroke": 0.0, "shadow": 0.0, "shadow_color": "#000000", "box": False, "box_color": "#000000", "box_opacity": 0.45,
    "box_pad": 20.0, "align": "center", "position": "bottom", "x": 0.5, "y": None, "region": None, "scale": 1.0, "anim_in": "none", "anim_out": "none",
    "anim_dur": 0.4, "words": [], "hl_color": "#FFD400", "hl_text": None, "hl_mode": "color", "direction": "auto",
}

_RTL = re.compile("[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]")


def _num(value, lo, hi, default):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, x))


def _clean_text(value, limit: int) -> str:
    """Control characters out, line breaks normalised to \\n, tabs to spaces, length capped."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    text = text.replace("\t", " ")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " " and ch != "\x7f")
    return text[:limit]


def is_rtl(text: str) -> bool:
    """First strong LETTER decides (digits are weak: a line of digits and Latin is LTR)."""
    for ch in text or "":
        if ch.isalpha():
            return bool(_RTL.match(ch))
    return False


def clean(raw: dict, index: int = 0) -> dict:
    """One caption clip from whatever the caller built -> every key, clamped. Raises `CaptionError` for an empty text."""
    if not isinstance(raw, dict):
        raise CaptionError("caption clip is not a dict")
    d = dict(_BASE)

    def pick(key):
        value = raw.get(key)
        return d[key] if value is None else value

    text = _clean_text(raw.get("text"), MAX_TEXT)
    if not text.strip():
        raise CaptionError(f"caption {index + 1}: the text is empty")
    out: dict = {"text": text}
    out["at"] = _num(raw.get("at"), 0, 86400, 0.0)
    out["duration"] = _num(pick("duration"), 0.1, 3600, 2.5)
    font = str(pick("font"))
    out["font"] = font if font in FONTS else "vazir"
    out["size"] = _num(pick("size"), 1, 30, 6.0)
    out["bold"] = bool(pick("bold"))
    out["italic"] = bool(pick("italic"))
    out["color"] = contrast.norm(pick("color"), "#FFFFFF")
    out["opacity"] = _num(pick("opacity"), 0.05, 1, 1.0)
    out["stroke_color"] = contrast.norm(pick("stroke_color"), "#000000")
    out["stroke"] = _num(pick("stroke"), 0, 100, 0.0)
    out["shadow"] = _num(pick("shadow"), 0, 100, 0.0)
    out["shadow_color"] = contrast.norm(pick("shadow_color"), "#000000")
    out["box"] = bool(pick("box"))
    out["box_color"] = contrast.norm(pick("box_color"), "#000000")
    out["box_opacity"] = _num(pick("box_opacity"), 0, 1, 0.45)
    out["box_pad"] = _num(pick("box_pad"), 0, 100, 20.0)
    align = str(pick("align"))
    out["align"] = align if align in ALIGNS else "center"
    position = str(raw.get("position") or "bottom")
    out["position"] = position if position in POSITION_Y else "bottom"
    out["x"] = _num(raw.get("x"), 0, 1, 0.5)
    out["y"] = _num(raw.get("y"), 0, 1, POSITION_Y[out["position"]]) if raw.get("y") is not None else POSITION_Y[out["position"]]
    out["region"] = _num(raw.get("region"), 0.2, 1.0, None) if raw.get("region") is not None else None
    out["scale"] = _num(pick("scale"), 0.1, 4, 1.0)
    anim_in, anim_out = str(pick("anim_in")), str(pick("anim_out"))
    out["anim_in"] = anim_in if anim_in in ANIMATIONS_IN else "none"
    out["anim_out"] = anim_out if anim_out in ANIMATIONS_OUT else "none"
    out["anim_dur"] = _num(pick("anim_dur"), 0.1, 2.0, 0.4)
    out["hl_color"] = contrast.norm(pick("hl_color"), "#FFD400")
    out["hl_text"] = contrast.norm(raw.get("hl_text"), "") or None
    hl_mode = str(pick("hl_mode"))
    out["hl_mode"] = hl_mode if hl_mode in HL_MODES else "color"
    direction = str(pick("direction"))
    out["direction"] = direction if direction in DIRECTIONS else "auto"
    out["words"] = _clean_words(raw.get("words"), out["duration"])
    return out


def _clean_words(raw, duration: float) -> list[dict]:
    words = []
    for item in (raw if isinstance(raw, list) else [])[:MAX_WORDS]:
        if not isinstance(item, dict):
            continue
        w = _clean_text(item.get("w", item.get("word", item.get("text"))), 60).replace("\n", " ").strip()
        if not w:
            continue
        s = _num(item.get("s", item.get("start")), 0, 3600, None)
        e = _num(item.get("e", item.get("end")), 0, 3600, None)
        if s is None or e is None:
            continue
        s = min(s, duration)
        e = max(s, min(e, duration))
        words.append({"w": w, "s": round(s, 3), "e": round(e, 3)})
    words.sort(key=lambda w: w["s"])
    return words


def _mark(it: dict) -> str:
    """The direction mark that starts every line of the clip ('' = let libass decide from the first strong letter)."""
    d = it["direction"]
    if d == "auto":
        return ""
    return RLM if d == "rtl" else LRM


# ---------------------------------------------------------------- ASS pieces

def _esc(text: str) -> str:
    """Text -> ASS text that carries exactly these characters and no tags."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\u200b")        # a backslash followed by N/n/h would be an escape; a zero-width space breaks it
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ch == "\n":
            out.append("\\N")
        else:
            out.append(ch)
    return "".join(out)


def _c(color: str) -> str:
    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _a(opacity: float) -> str:
    """ASS alpha (00 opaque ... FF transparent) for an opacity 0..1."""
    return "&H%02X&" % int(round(255 * (1 - max(0.0, min(1.0, opacity)))))


def _ts(seconds: float) -> str:
    cs = max(0, int(round(seconds * 100)))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _f(value: float, digits: int = 2) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def ass_filter(filename: str = "sub.ass", fontsdir: str = "fonts") -> str:
    """The `ass` filter for a script and the bundled fonts folder. Both are RELATIVE: the caller runs ffmpeg inside the work folder (a Windows drive letter
    or a space in a path is a filter-graph escaping trap, a relative name is not)."""
    return f"ass={filename}:fontsdir={fontsdir}"


# ------------------------------------------------------------------ geometry

@functools.lru_cache(maxsize=64)
def _pil_font(path: str, size: int, raqm: bool):
    from PIL import ImageFont

    engine = ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC
    return ImageFont.truetype(path, size, layout_engine=engine)


def font_file(key: str, bold: bool = True) -> Path:
    f = FONTS[key if key in FONTS else "vazir"]
    return FONTS_DIR / (f["bold_file"] if (bold and f["bold"]) else f["file"])


def text_width(text: str, em: float, font_key: str, bold: bool = True) -> float:
    """Width of one line in px, measured with the font and the shaper the rest of InstAI uses for Persian (libraqm when it works, else the built-in one),
    so a line is measured as libass draws it; half an em per character when the font file cannot be opened."""
    path = font_file(font_key, bold)
    if path.is_file():
        try:
            from . import fa_text

            return float(fa_text.text_width(text, _pil_font(str(path), max(8, int(round(em))), fa_text.RAQM_OK)))
        except Exception:  # noqa: BLE001 - no raqm, odd glyphs
            pass
    return len(text) * em * 0.52


def estimate_lines(text: str, em: float, width: float, font_key: str = "vazir", bold: bool = True) -> int:
    """How many lines libass will break `text` into at `width` px (greedy; good enough for sizing a box)."""
    count = 0
    for paragraph in (text or "").split("\n"):
        line = ""
        n = 1
        for word in paragraph.split():
            trial = (line + " " + word).strip()
            if line and text_width(trial, em, font_key, bold) > width:
                n += 1
                line = word
            else:
                line = trial
        count += n
    return max(1, count)


def wrap_budget(wrap: float, em: float, stroke: float, hl_mode: str, timed: bool) -> float:
    """The width a line can really use inside a wrap region of `wrap` px. libass breaks a line earlier than a plain sum of glyph widths says: by the safety margin, by the outline
    on both sides, by the marker that grows around the spoken word (`box` mode: 0.16 em each side) and by the spoken word swelling (`scale` mode, 12 % on one word)."""
    budget = wrap * WRAP_SAFETY - 2 * em * stroke / 100.0
    if timed and hl_mode == "box":
        budget -= 0.32 * em
    elif timed and hl_mode == "scale":
        budget *= 0.95
    return max(20.0, budget)


def geometry(it: dict, W: int, H: int) -> dict:
    """Where the clip's text block sits: wrap region, anchor, the estimated block height, and the anchor's y pulled inside the frame (a bottom caption that
    wraps to four lines would otherwise hang off the edge)."""
    font = FONTS[it["font"]]
    em = it["size"] / 100.0 * H
    x, y = it["x"] * W, it["y"] * H
    frac = it["region"] if it["region"] else min(0.88, 2 * min(it["x"], 1 - it["x"]) * 0.96)
    region = frac * W
    left, right = x - region / 2, x + region / 2
    anchor = {"left": left, "center": (left + right) / 2, "right": right}[it["align"]]
    pad = em * it["box_pad"] / 100.0 if it["box"] else 0.0
    g = {"font": font, "em": em, "x": x, "y": y, "left": left, "right": right, "region": region, "anchor_x": anchor,
         "an": {"left": 4, "center": 5, "right": 6}[it["align"]], "pad": pad, "wrap": max(20.0, right - left - 2 * pad)}
    g["lines"] = estimate_lines(it["text"], em, wrap_budget(g["wrap"], em, it["stroke"], it["hl_mode"], bool(it["words"])), it["font"], it["bold"])
    g["block_h"] = g["lines"] * em * font["line"]
    half = g["block_h"] / 2 + pad + 0.01 * H
    lo, hi = half + 0.02 * H, H - half - 0.02 * H
    g["y"] = min(max(y, lo), hi) if lo <= hi else H / 2.0
    return g


# ----------------------------------------------------------------- animation

def _ease_out(u: float) -> float:
    return 1 - (1 - u) ** 3


def _ease_in(u: float) -> float:
    return u ** 3


def _back_out(u: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (u - 1) ** 3 + c1 * (u - 1) ** 2


_DIRS = {"slide_up": (0, -1), "slide_down": (0, 1), "slide_left": (-1, 0), "slide_right": (1, 0)}


def _apply(kind: str, u: float, mode: str, W: int, H: int) -> dict:
    """The change one animation makes at progress u (0..1 of its own window)."""
    st = {"alpha": 1.0, "scale": 1.0, "dx": 0.0, "dy": 0.0, "blur": 0.0, "reveal": 1.0}
    entering = mode == "in"
    p = _ease_out(u) if entering else _ease_in(u)        # 0 -> 1: arrived / departed
    gone = (1 - p) if entering else p                      # how far from the resting state
    if kind == "fade":
        st["alpha"] = 1 - gone
    elif kind in _DIRS:
        dirx, diry = _DIRS[kind]
        sign = -1 if entering else 1            # in: start behind the direction of travel; out: end ahead of it
        st["dx"], st["dy"] = sign * dirx * 0.10 * W * gone, sign * diry * 0.06 * H * gone
        st["alpha"] = 1 - gone
    elif kind == "pop":
        if entering:
            st["scale"] = 0.45 + 0.55 * _back_out(u)
            st["alpha"] = min(1.0, u * 3)
        else:
            st["scale"] = 1 - 0.4 * p
            st["alpha"] = 1 - p
    elif kind == "zoom":
        st["scale"] = 1 + (0.6 * gone if entering else 0.4 * p)
        st["alpha"] = 1 - gone
    elif kind == "blur":
        st["blur"] = gone * 0.008 * H
        st["alpha"] = 1 - gone
    elif kind == "typewriter":
        st["reveal"] = u if entering else 1 - u
    return st


def _windows(it: dict, n_chars: int) -> tuple[float, float]:
    """(in, out) animation lengths, never eating more than 90 % of the clip together."""
    dur = it["duration"]
    d_in = it["anim_dur"] if it["anim_in"] != "none" else 0.0
    d_out = it["anim_dur"] if it["anim_out"] != "none" else 0.0
    if it["anim_in"] == "typewriter":
        d_in = max(d_in, 0.045 * n_chars)
    if d_in + d_out > dur * 0.9:
        k = dur * 0.9 / (d_in + d_out)
        d_in, d_out = d_in * k, d_out * k
    return d_in, d_out


def entrance_seconds(it: dict) -> float:
    """How long the entrance animation of a cleaned clip lasts (a preview picture is taken after it)."""
    return _windows(it, len(it["text"]))[0]


def _state(it: dict, t: float, d_in: float, d_out: float, W: int, H: int) -> dict:
    st = {"alpha": 1.0, "scale": 1.0, "dx": 0.0, "dy": 0.0, "blur": 0.0, "reveal": 1.0}
    dur = it["duration"]
    parts = []
    if d_in > 0 and t < d_in:
        parts.append(_apply(it["anim_in"], max(0.0, t / d_in), "in", W, H))
    if d_out > 0 and t > dur - d_out:
        parts.append(_apply(it["anim_out"], min(1.0, (t - (dur - d_out)) / d_out), "out", W, H))
    for part in parts:
        st["alpha"] *= part["alpha"]
        st["scale"] *= part["scale"]
        st["dx"] += part["dx"]
        st["dy"] += part["dy"]
        st["blur"] = max(st["blur"], part["blur"])
        st["reveal"] = min(st["reveal"], part["reveal"])
    return st


# ------------------------------------------------------------- karaoke words

def _word_plan(it: dict) -> tuple[str, list[tuple[float, float]]]:
    """(text to show, [(active_from, active_to)] per word). With `words`, the text is mapped word by word; when the counts differ the words' own spelling
    wins (their timing is what we have)."""
    text = it["text"]
    words = it["words"]
    if not words:
        return text, []
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    if len(tokens) != len(words):
        text = " ".join(w["w"] for w in words)
    spans = []
    for i, w in enumerate(words):
        nxt = words[i + 1]["s"] if i + 1 < len(words) else it["duration"]
        end = max(w["s"] + 0.05, min(nxt, w["e"] + 0.25))
        spans.append((w["s"], end))
    return text, spans


def _pieces(text: str, spans) -> tuple[list, int]:
    """The clip's text as pieces: ("t", text, word_index|None) | ("nl",). Returns (pieces, n_chars)."""
    pieces: list = []
    widx = 0
    chars = 0
    for li, line in enumerate(text.split("\n")):
        if li:
            pieces.append(("nl",))
        for part in re.split(r"(\s+)", line):
            if not part:
                continue
            if part.isspace():
                pieces.append(("t", " ", None))
                chars += 1
            else:
                pieces.append(("t", part, widx if spans else None))
                widx += 1
                chars += len(part)
    return pieces, chars


# Marks that hang BELOW the baseline (kasra, kasratan, subscript alef, hamza below, wavy hamza below). The marker / box layer is the OUTLINE of the glyphs thickened by the padding, so one of
# these at the end of a line pulls a small stub out of the bottom edge of the box (found by viewing a real 1080x1920 frame). The box layer is drawn without them; the text layer keeps them.
BELOW_MARKS = "".join(chr(c) for c in (0x064D, 0x0650, 0x0655, 0x0656, 0x065F))
_BELOW_TABLE = {ord(c): None for c in BELOW_MARKS}


def _render(pieces, *, mark: str, reveal_chars: int | None, active: int | None, hl_open: str, hl_close: str, hide: str, strip_below: bool = False) -> str:
    """Pieces -> ASS text. `reveal_chars` hides the rest (typewriter); `active` marks one word (karaoke); `strip_below` leaves out the marks under the baseline (the box layer)."""
    out: list[str] = [mark] if mark else []
    shown = 0
    cut = False
    for piece in pieces:
        if piece[0] == "nl":
            out.append("\\N" + mark)
            continue
        text, widx = piece[1], piece[2]
        if strip_below:
            text = text.translate(_BELOW_TABLE)
        if cut:
            out.append(_esc(text))
            continue
        if reveal_chars is not None and shown + len(text) > reveal_chars:
            keep = max(0, reveal_chars - shown)
            if keep:
                out.append(_esc(text[:keep]))
            out.append(hide)
            out.append(_esc(text[keep:]))
            cut = True
            continue
        shown += len(text)
        if active is not None and widx == active:
            out.append(hl_open + _esc(text) + hl_close)
        else:
            out.append(_esc(text))
    return "".join(out)


# ---------------------------------------------------------------- the writer

_HEADER = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
    "YCbCr Matrix: TV.709\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
    "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
    "MarginV, Encoding\n"
)
_EVENTS = "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"


def _style(name: str, it: dict, g: dict, *, box_layer: bool) -> str:
    font = g["font"]
    bold = -1 if (it["bold"] and font["bold"]) else 0
    outline = g["em"] * it["stroke"] / 100.0
    shadow = g["em"] * it["shadow"] / 100.0 * 0.6
    pad = g["em"] * it["box_pad"] / 100.0
    if box_layer:
        border, out_w, shad = 3, pad, 0
    else:
        border, out_w, shad = 1, outline, shadow
    return (f"Style: {name},{font['family']},{_f(g['em'] * font['line'])},{_c(it['color'])},{_c(it['color'])},"
            f"{_c(it['stroke_color'])},{_c(it['shadow_color'])},{bold},{-1 if it['italic'] else 0},0,0,100,100,0,0,"
            f"{border},{_f(out_w)},{_f(shad)},{g['an']},0,0,0,-1")


def _item_ass(n: int, it: dict, W: int, H: int, offset: float) -> tuple[list[str], list[str]]:
    g = geometry(it, W, H)
    em = g["em"]
    dur = it["duration"]
    text, spans = _word_plan(it)
    pieces, n_chars = _pieces(text, spans)
    d_in, d_out = _windows(it, n_chars)
    mark = _mark(it)

    base_scale = it["scale"] * 100.0
    box_on = it["box"]
    styles = [_style(f"T{n}", it, g, box_layer=False)]
    if box_on:
        styles.append(_style(f"B{n}", it, g, box_layer=True))

    # --- breakpoints: animation steps and every karaoke word boundary
    marks = {0.0, dur}
    k = 6
    if d_in > 0:
        steps = min(40, max(6, n_chars)) if it["anim_in"] == "typewriter" else k
        marks.update(d_in * i / steps for i in range(steps + 1))
    if d_out > 0:
        steps = min(40, max(6, n_chars)) if it["anim_out"] == "typewriter" else k
        marks.update(dur - d_out + d_out * i / steps for i in range(steps + 1))
    for s, e in spans:
        marks.update((min(s, dur), min(e, dur)))
    cuts = sorted({round(min(max(m, 0.0), dur), 2) for m in marks})

    events: list[str] = []
    ml, mr = int(round(g["left"])), int(round(W - g["right"]))
    hl_mode, hl_color = it["hl_mode"], it["hl_color"]
    hl_text = it["hl_text"] or contrast.readable_on(hl_color)
    stroke_px = em * it["stroke"] / 100.0
    pad_px = g["pad"]

    def motion(st_a, st_b, length_ms):
        """\\pos or \\move between the two states' offsets."""
        ax, ay = g["anchor_x"], g["y"]
        xa, ya = ax + st_a["dx"], ay + st_a["dy"]
        xb, yb = ax + st_b["dx"], ay + st_b["dy"]
        if abs(xa - xb) < 0.3 and abs(ya - yb) < 0.3:
            return f"\\pos({_f(xa, 1)},{_f(ya, 1)})"
        return f"\\move({_f(xa, 1)},{_f(ya, 1)},{_f(xb, 1)},{_f(yb, 1)},0,{length_ms})"

    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.01:
            continue
        mid = (a + b) / 2
        length_ms = int(round((b - a) * 1000))
        sa = _state(it, a, d_in, d_out, W, H)
        sb = _state(it, b, d_in, d_out, W, H)
        sm = _state(it, mid, d_in, d_out, W, H)
        start, end = _ts(a + offset), _ts(b + offset)
        active = next((i for i, (s, e) in enumerate(spans) if s <= mid < e), None) if spans else None
        reveal_chars = None
        if sm["reveal"] < 0.999:
            reveal_chars = int(round(sm["reveal"] * n_chars))

        def layer_tags(layer: str) -> str:
            """Tags that make a dialogue look like st_a at its start and st_b at its end."""
            parts = [f"\\an{g['an']}", motion(sa, sb, length_ms)]
            sc_a, sc_b = base_scale * sa["scale"], base_scale * sb["scale"]
            parts.append(f"\\fscx{_f(sc_a)}\\fscy{_f(sc_a)}")
            tail = []
            if layer == "box":
                fa = lambda s: _a(it["box_opacity"] * s["alpha"])  # noqa: E731
                parts.append("\\1a&HFF&\\shad0\\4a&HFF&")
                parts.append(f"\\bord{_f(pad_px)}\\3c{_c(it['box_color'])}")
                parts.append(f"\\3a{fa(sa)}")
                if sc_a != sc_b:
                    tail.append(f"\\fscx{_f(sc_b)}\\fscy{_f(sc_b)}")
                if fa(sa) != fa(sb):
                    tail.append(f"\\3a{fa(sb)}")
            else:
                parts.append(f"\\1a{_a(it['opacity'] * sa['alpha'])}\\3a{_a(sa['alpha'])}\\4a{_a(0.6 * sa['alpha'])}")
                if sa["blur"] or sb["blur"]:
                    parts.append(f"\\blur{_f(sa['blur'])}")
                if sc_a != sc_b:
                    tail.append(f"\\fscx{_f(sc_b)}\\fscy{_f(sc_b)}")
                if abs(sa["alpha"] - sb["alpha"]) > 1e-3:
                    tail.append(f"\\1a{_a(it['opacity'] * sb['alpha'])}\\3a{_a(sb['alpha'])}\\4a{_a(0.6 * sb['alpha'])}")
                if abs(sa["blur"] - sb["blur"]) > 1e-3:
                    tail.append(f"\\blur{_f(sb['blur'])}")
            if tail:
                parts.append(f"\\t(0,{length_ms},{''.join(tail)})")
            return "{" + "".join(parts) + "}"

        # karaoke tags for the active word (static inside the slice)
        mid_scale = base_scale * sm["scale"]
        if hl_mode == "box":          # a marker behind the word: the outline in the highlight colour, the letters in a colour that reads on it
            hl_open = f"{{\\1c{_c(hl_text)}\\3c{_c(hl_color)}\\bord{_f(stroke_px + em * 0.16)}}}"
            hl_close = f"{{\\1c{_c(it['color'])}\\3c{_c(it['stroke_color'])}\\bord{_f(stroke_px)}}}"
        elif hl_mode == "scale":
            hl_open = f"{{\\1c{_c(hl_color)}\\fscx{_f(mid_scale * 1.12)}\\fscy{_f(mid_scale * 1.12)}}}"
            hl_close = f"{{\\1c{_c(it['color'])}\\fscx{_f(mid_scale)}\\fscy{_f(mid_scale)}}}"
        else:
            hl_open = f"{{\\1c{_c(hl_color)}}}"
            hl_close = f"{{\\1c{_c(it['color'])}}}"
        hide = "{\\1a&HFF&\\3a&HFF&\\4a&HFF&}"

        # --- box layer (layer 0) under the text (layer 1)
        if box_on:
            body = _render(pieces, mark=mark, reveal_chars=reveal_chars, active=None, hl_open="", hl_close="", hide=hide, strip_below=True)
            events.append(f"Dialogue: 0,{start},{end},B{n},,{ml},{mr},0,,{layer_tags('box')}{body}")
        body = _render(pieces, mark=mark, reveal_chars=reveal_chars, active=active, hl_open=hl_open, hl_close=hl_close, hide=hide)
        events.append(f"Dialogue: 1,{start},{end},T{n},,{ml},{mr},0,,{layer_tags('text')}{body}")
    return styles, events


def build_ass(items: list[dict], width: int, height: int) -> str:
    """ONE ASS document for the caption clips (each with `at` and `duration` on the timeline). Items are cleaned here, so a caller may hand raw dicts."""
    W, H = int(width), int(height)
    styles: list[str] = []
    events: list[tuple[float, str]] = []
    for n, raw in enumerate(items):
        it = clean(raw, n)
        s, e = _item_ass(n, it, W, H, it["at"])
        styles += s
        events += [(it["at"], line) for line in e]
    events.sort(key=lambda pair: pair[0])
    return _HEADER.format(w=W, h=H) + "\n".join(styles) + "\n" + _EVENTS + "\n".join(line for _, line in events) + "\n"
