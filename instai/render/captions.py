"""Word-by-word captions for an episode: seven presets (big and punchy, dark box, karaoke marker, clean, neon, typewriter, quiet lower band) plus the plain
look InstAI always had ("classic"), as an ASS script for ffmpeg's libass, and the same words as an .srt file.

SOURCE: ported from NMarketing:backend/services/editing/captions.py (group_words, caption_clips, soft_cues, write_soft_srt) and
backend/services/editing/director/tools.py (CAPTION_STYLES) @ v3.02 (c23f861), adapted for a channel / series producer: the node speech-recognition
plumbing is left out (InstAI already KNOWS the text of every cue); word times come from the real narration audio of each shot (see `shot_words`);
the colours come from the series' look and are checked for contrast; the vertical formats keep captions out of the platform's own interface
(`safezones`); the text can be Persian (right to left) or English (left to right).

How a caption is made, in order:
  1. `shot_words`   the known text of a shot + the real duration of its narration -> [{w, s, e}] word times. Estimated from the characters when no recogniser
                    gave real times (flagged `estimated`); real times (the `words` of a shot, in seconds from the start of its audio) are aligned onto OUR
                    spelling, so a recogniser's mistakes never reach the screen.
  2. `group_words`  the word stream -> screen-sized lines (never more lines than the preset allows at this frame size).
  3. `resolve_style` a preset + the look -> every colour, with the contrast checked (text 4.5:1 against its own surface).
  4. `plan`         everything above for a whole timeline -> {ass, srt, cues, info}; `titles_ass` writes the ASS.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re

from . import contrast, safezones, srt, titles_ass

# ------------------------------------------------------------------ presets

DEFAULT_PRESET = "classic"
MODES = {"burned": ("روی تصویر", "On the picture", "زیرنویس داخل خودِ ویدئو دیده می‌شود (و فایل SRT هم کنارش ساخته می‌شود).",
                    "The captions are part of the video (an SRT file is made beside it too)."),
         "soft": ("فایل جدا (SRT)", "Separate file (SRT)", "تصویر تمیز می‌ماند و زیرنویس فقط فایل SRT است (یوتیوب، آپارات و تلگرام آن را می‌پذیرند).",
                  "The picture stays clean and the captions travel only as an SRT file (YouTube, Aparat and Telegram take it)."),
         "none": ("بدون زیرنویس", "No captions", "نه روی تصویر و نه فایل جدا.", "Neither on the picture nor as a file.")}
DEFAULT_MODE = "burned"
DEFAULT_CONFIG = {"preset": DEFAULT_PRESET, "mode": DEFAULT_MODE, "zone": safezones.AUTO}

#: The eight looks. `size` is a % of the frame height (the NM values, tuned on 9:16); `weight` is the font weight before the theme's own `title_weight`
#: moves it one step; the colours are NOT here - they come from the series look (`resolve_style`). `max_words` / `lines` shape the screen lines.
PRESETS: dict[str, dict] = {
    "classic": {"fa": "کلاسیک", "en": "Classic",
                "hint_fa": "همان زیرنویسِ ساده و ثابتِ همیشگیِ InstAI؛ کلمهٔ در حالِ گفتن نشان داده نمی‌شود.",
                "hint_en": "The plain, fixed InstAI subtitle it always had; the word being spoken is not marked.", "legacy": True},
    "pop": {"fa": "درشت و پرانرژی", "en": "Big and punchy",
            "hint_fa": "کلمه‌های درشت با لبهٔ ضخیم؛ کلمهٔ در حالِ گفتن رنگی می‌شود و کمی بزرگ‌تر. برای شورتس و ریلز.",
            "hint_en": "Big words with a thick edge; the word being spoken takes the accent colour and swells a little. For Shorts and Reels.",
            "weight": "black", "size": 7.2, "stroke": 14.0, "shadow": 10.0, "box": False, "hl_mode": "scale", "anim_in": "pop", "anim_dur": 0.18,
            "max_words": 4, "lines": 2},
    "box": {"fa": "کادرِ تیره", "en": "Dark box",
            "hint_fa": "متن روی یک کادرِ تیره؛ در هر پس‌زمینه‌ای خوانده می‌شود.",
            "hint_en": "The text on a dark box; reads on any background.",
            "weight": "bold", "size": 5.6, "stroke": 0.0, "shadow": 0.0, "box": True, "box_opacity": 0.62, "box_pad": 22.0, "hl_mode": "color",
            "max_words": 6, "lines": 2},
    "karaoke": {"fa": "کارائوکه (ماژیک)", "en": "Karaoke (marker)",
                "hint_fa": "کلمهٔ در حالِ گفتن با یک ماژیکِ رنگی هایلایت می‌شود.",
                "hint_en": "The word being spoken is marked with a coloured highlighter.",
                "weight": "black", "size": 6.6, "stroke": 12.0, "shadow": 8.0, "box": False, "hl_mode": "box", "max_words": 5, "lines": 2},
    "clean": {"fa": "ساده و تمیز", "en": "Clean",
              "hint_fa": "ساده با لبهٔ نازک و سایه؛ کلمهٔ در حالِ گفتن رنگی می‌شود.",
              "hint_en": "Simple with a thin edge and a shadow; the word being spoken takes the accent colour.",
              "weight": "bold", "size": 5.2, "stroke": 6.0, "shadow": 14.0, "box": False, "hl_mode": "color", "max_words": 7, "lines": 2},
    "neon": {"fa": "نئونی", "en": "Neon",
             "hint_fa": "کلمهٔ در حالِ گفتن با رنگِ درخشانِ سریال روشن می‌شود و کمی بزرگ‌تر.",
             "hint_en": "The word being spoken lights up in the series' bright accent colour and swells a little.",
             "weight": "black", "size": 6.8, "stroke": 12.0, "shadow": 12.0, "box": False, "hl_mode": "scale", "anim_in": "pop", "anim_dur": 0.14,
             "max_words": 4, "lines": 2},
    "typewriter": {"fa": "ماشین‌تحریر", "en": "Typewriter",
                   "hint_fa": "هر خط حرف‌به‌حرف تایپ می‌شود؛ کلمهٔ در حالِ گفتن رنگی است.",
                   "hint_en": "Each line types itself in; the word being spoken is coloured.",
                   "weight": "bold", "size": 5.8, "stroke": 8.0, "shadow": 10.0, "box": False, "hl_mode": "color", "anim_in": "typewriter", "anim_dur": 0.3,
                   "max_words": 6, "lines": 2},
    "lower": {"fa": "آرام (گفتگو و روایت)", "en": "Quiet lower band",
              "hint_fa": "کوچک‌تر، روی یک نوار کم‌رنگ و بدون چشمک؛ برای روایت و گفتگوی طولانی.",
              "hint_en": "Smaller, on a soft band and without flashing; for long narration and dialogue.",
              "weight": "regular", "size": 4.6, "stroke": 4.0, "shadow": 0.0, "box": True, "box_opacity": 0.55, "box_pad": 16.0, "hl_mode": "color",
              "anim_in": "fade", "anim_dur": 0.2, "max_words": 9, "lines": 2, "quiet": True},
}
ORDER = list(PRESETS)
NEW_PRESETS = [k for k in ORDER if not PRESETS[k].get("legacy")]          # the seven of NM
_WEIGHTS = ("light", "regular", "bold", "black")
_WEIGHT_FONT = {"light": ("vazir_light", False), "regular": ("vazir", False), "bold": ("vazir", True), "black": ("vazir_black", False)}
_TITLE_WEIGHT_SHIFT = {"regular": -1, "bold": 0, "black": 1}
DEFAULT_PALETTE = {"background": "#14181F", "primary": "#3B4A5C", "secondary": "#B9824B", "accent": "#E8C98F", "shadow": "#05070A", "highlight": "#F3E9D8"}
#: signal colours tried (in this order) when the series' own palette has no accent that reads and differs from the text
FALLBACK_HIGHLIGHTS = ("#FFD400", "#39FF88", "#FFB703", "#00E5FF")


def normalize_config(raw) -> dict:
    """{preset, mode, zone} from whatever arrives (a profile, a request body): unknown values fall back to the defaults."""
    raw = raw if isinstance(raw, dict) else {}
    preset = str(raw.get("preset") or DEFAULT_PRESET)
    mode = str(raw.get("mode") or DEFAULT_MODE)
    zone = str(raw.get("zone") or safezones.AUTO)
    return {"preset": preset if preset in PRESETS else DEFAULT_PRESET, "mode": mode if mode in MODES else DEFAULT_MODE,
            "zone": zone if zone in safezones.KEYS else safezones.AUTO}


def merge_config(*layers) -> dict:
    """Later layers win key by key; an empty / missing key leaves the earlier value (the episode override sits on top of the page's setting)."""
    out = dict(DEFAULT_CONFIG)
    for layer in layers:
        for k, v in (layer or {}).items():
            if k in out and v not in (None, ""):
                out[k] = v
    return normalize_config(out)


def is_default(cfg: dict) -> bool:
    return normalize_config(cfg) == DEFAULT_CONFIG


def catalogue() -> dict:
    return {"presets": [{"key": k, "fa": v["fa"], "en": v["en"], "hint_fa": v["hint_fa"], "hint_en": v["hint_en"], "legacy": bool(v.get("legacy"))}
                        for k, v in PRESETS.items()],
            "modes": [{"key": k, "fa": v[0], "en": v[1], "hint_fa": v[2], "hint_en": v[3]} for k, v in MODES.items()],
            "zones": [{"key": safezones.AUTO, "fa": "خودکار (از شکل قاب و پلتفرمِ صفحه)", "en": "Automatic (from the frame shape and the page's platform)",
                       "hint_fa": "اندازه و پلتفرم انتشارِ صفحه را می‌بیند و ناحیهٔ امنِ درست را برمی‌دارد.",
                       "hint_en": "Looks at the frame and the platform the page publishes to and takes the right safe zone.", "margins": None}, *safezones.catalogue()]}


# ------------------------------------------------------------------ the look -> colours

def palette_of(look: dict | None) -> dict:
    """The six palette roles of a look (kit.style_kit()["palette"]); a missing / invalid one falls back to the default."""
    pal = (look or {}).get("palette") if isinstance(look, dict) else None
    pal = pal if isinstance(pal, dict) else {}
    return {k: contrast.norm(pal.get(k), v) for k, v in DEFAULT_PALETTE.items()}


def weight_font(weight: str, title_weight: str = "bold") -> tuple[str, bool]:
    """(font key, bold flag) for a preset weight moved one step by the theme's `title_weight` (regular lighter, black heavier, bold unchanged)."""
    i = _WEIGHTS.index(weight) if weight in _WEIGHTS else 2
    i = max(0, min(len(_WEIGHTS) - 1, i + _TITLE_WEIGHT_SHIFT.get(title_weight, 0)))
    return _WEIGHT_FONT[_WEIGHTS[i]]


def fit_contrast(color: str, bg: str, minimum: float = contrast.TEXT_MIN) -> str:
    """`color` as it is when it passes against `bg`, else pulled toward white or black (whichever reads) until it does."""
    color = contrast.norm(color, contrast.WHITE)
    return contrast.accent_on(bg, color, minimum)


MIN_CHROMA = 0.30      # a highlight that is a grey, or white's pale cousin, does not stand out from the plain words


def pick_highlight(candidates, surface: str, text: str) -> str:
    """The first candidate that reads on `surface` (as it is, else brightened with its hue kept, else mixed toward the readable plain colour), is clearly another colour
    than `text` AND is a real colour (not a grey); else the first signal colour that is. A look whose own colours are all pale or grey gets a signal colour: a
    highlight nobody can tell from the plain words is not a highlight."""
    for c in [*candidates, *FALLBACK_HIGHLIGHTS]:
        c = contrast.norm(c, "")
        if not c:
            continue
        options = [c] if contrast.contrast(c, surface) >= contrast.TEXT_MIN else []
        if not options and contrast.chroma(c) >= 0.25:
            vivid = contrast.vivid_on(surface, c)
            if vivid:
                options.append(vivid)
        options.append(fit_contrast(c, surface))
        for o in options:
            if contrast.contrast(o, surface) >= contrast.TEXT_MIN and contrast.distance(o, text) >= 0.30 and contrast.chroma(o) >= MIN_CHROMA:
                return o
    return FALLBACK_HIGHLIGHTS[0]


def resolve_style(preset: str, look: dict | None = None, *, language: str = "fa") -> dict:
    """Every parameter of a preset's caption clip, with colours from the series look and contrast guaranteed:
         text      against its own surface (the outline, or the box)      >= 4.5
         highlight against the same surface, and clearly not the text colour
         marker    (karaoke) the letters on the marker                   >= 4.5
       Returns the `titles_ass.clean` keys plus `max_words`, `lines`, `contrast` ({text, highlight, marker?} ratios) and `surface`."""
    p = PRESETS.get(preset)
    if p is None or p.get("legacy"):
        raise ValueError(f"unknown caption preset: {preset}")
    look = look if isinstance(look, dict) else {}
    pal = palette_of(look)
    typo = look.get("typography") if isinstance(look.get("typography"), dict) else {}
    font, bold = weight_font(p["weight"], str(typo.get("title_weight") or "bold"))
    boxed = bool(p["box"])
    accent, other = pal["accent"], [pal["secondary"], pal["highlight"], pal["primary"]]
    if boxed:
        surface = pal["background"] if contrast.luminance(pal["background"]) <= 0.06 else contrast.dark_of(pal["background"])
        stroke_color = surface
    elif preset == "neon":
        surface = contrast.mix(accent, contrast.BLACK, 0.88)
        surface = surface if contrast.luminance(surface) <= 0.06 else contrast.dark_of(surface)
        stroke_color = surface
    else:
        surface = contrast.dark_of(pal["background"])
        stroke_color = surface
    text = contrast.readable_on(surface, [typo.get("subtitle_color") or "", contrast.WHITE])
    if p.get("quiet"):
        highlight = text                           # the quiet band never flashes: the spoken word is not marked
    else:
        highlight = pick_highlight([accent, *other], surface, text)
    if preset == "neon":                           # it should look LIT: the colour of the look at its brightest that still reads (8:1), else a little brighter than the accent
        for lit in (contrast.vivid_on(surface, highlight, 8.0), contrast.mix(highlight, contrast.WHITE, 0.2)):
            if lit and contrast.distance(lit, text) >= 0.30 and contrast.contrast(lit, surface) >= contrast.TEXT_MIN and contrast.chroma(lit) >= MIN_CHROMA:
                highlight = lit
                break
    marker_text = contrast.readable_on(highlight) if p["hl_mode"] == "box" else None
    shadow_color = contrast.dark_of(pal["shadow"], 0.02)
    opacity = float(p.get("box_opacity", 0.45))
    if boxed:                                      # a translucent box over a pure white picture is a lighter box: the box gets as solid as the letters need, even there
        over_white = lambda o: contrast.mix(surface, contrast.WHITE, 1 - o)  # noqa: E731
        while opacity < 1.0 and (contrast.contrast(text, over_white(opacity)) < contrast.TEXT_MIN
                                 or contrast.contrast(highlight, over_white(opacity)) < contrast.TEXT_MIN):
            opacity = min(1.0, round(opacity + 0.02, 2))
    st = {"font": font, "bold": bold, "size": p["size"], "color": text, "stroke_color": stroke_color, "stroke": p["stroke"], "shadow": p["shadow"],
          "shadow_color": shadow_color, "box": boxed, "box_color": surface, "box_opacity": opacity, "box_pad": p.get("box_pad", 20.0), "hl_color": highlight, "hl_text": marker_text, "hl_mode": p["hl_mode"],
          "anim_in": p.get("anim_in", "none"), "anim_dur": p.get("anim_dur", 0.4), "align": "center", "direction": "ltr" if language == "en" else "rtl",
          "max_words": p["max_words"], "lines": p["lines"], "surface": surface}
    ratios = {"text": round(contrast.contrast(text, surface), 2), "highlight": round(contrast.contrast(highlight, surface), 2)}
    if marker_text:
        ratios["marker"] = round(contrast.contrast(marker_text, highlight), 2)
    if boxed:
        ratios["worst_text"] = round(contrast.contrast(text, over_white(opacity)), 2)          # on the paler possible picture: pure white
        ratios["worst_highlight"] = round(contrast.contrast(highlight, over_white(opacity)), 2)
    st["contrast"] = ratios
    return st


# ------------------------------------------------------------------ word times

_PUNCT = re.compile(r"[\s.,!?؟،؛:;…«»\"'()\[\]{}\-–—_*/\\|‌‏‎]+")
_SENTENCE_END = re.compile(r"[.!?؟…]+[\"'»)\]]*$")
_SOFT_BREAK = re.compile(r"[,،؛;:]+$")
_FOLD = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ئ": "ی", "ؤ": "و"})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MARKS = re.compile("[ً-ٰٟـۖ-ۭ]")        # short vowels, tashdid, hamza above/below, tatweel: spelling aids, not letters


def tokens_of(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", str(text or "").replace("\r", " ").replace("\n", " ").strip()) if t]


def _fold(word: str) -> str:
    return _PUNCT.sub("", _MARKS.sub("", str(word)).translate(_FOLD).translate(_DIGITS)).lower()


def estimated_words(text: str, start: float, duration: float) -> list[dict]:
    """[{w, s, e}] for the words of `text` spread over [start, start + duration] by their length. A word followed by a full stop or a comma is followed by a
    short silence too (the narration breathes there), so the highlight does not run ahead after every sentence. ESTIMATES: the true times need a recogniser."""
    words = tokens_of(text)
    if not words or duration <= 0:
        return []
    speech = [len(_fold(w)) + 0.6 for w in words]
    pause = [(3.0 if _SENTENCE_END.search(w) else 1.4 if _SOFT_BREAK.search(w) else 0.0) for w in words]
    pause[-1] = 0.0                                              # the audio ends with the last word
    total = sum(speech) + sum(pause)
    t, out = float(start), []
    for w, sp, pa in zip(words, speech, pause):
        s_dur = duration * sp / total
        out.append({"w": w, "s": round(t, 3), "e": round(t + s_dur, 3)})
        t += s_dur + duration * pa / total
    return out


def align_words(text: str, heard: list[dict], start: float, duration: float) -> tuple[list[dict], int]:
    """Our words on the recogniser's clock: `heard` = [{w, s, e}] in seconds from the start of the shot's audio. Words are matched in order (difflib on the
    folded spelling), every matched word takes the heard time, and the words between two matches are spread over the gap. Returns (words, matched)."""
    known = tokens_of(text)
    ok = [h for h in (heard or []) if isinstance(h, dict) and str(h.get("w", h.get("word", ""))).strip()]
    heard_w = []
    for h in ok:
        try:
            s, e = float(h.get("s", h.get("start"))), float(h.get("e", h.get("end")))
        except (TypeError, ValueError):
            continue
        heard_w.append({"w": str(h.get("w", h.get("word"))).strip(), "s": max(0.0, s), "e": max(s, e)})
    if not known or not heard_w:
        return estimated_words(text, start, duration), 0
    sm = difflib.SequenceMatcher(None, [_fold(w) for w in known], [_fold(h["w"]) for h in heard_w], autojunk=False)
    times: list[tuple[float, float] | None] = [None] * len(known)
    matched = 0
    for a, b, n in sm.get_matching_blocks():
        for i in range(n):
            if _fold(known[a + i]):
                times[a + i] = (heard_w[b + i]["s"], heard_w[b + i]["e"])
                matched += 1
    if not matched:
        return estimated_words(text, start, duration), 0
    # fill the unmatched words between two anchors, proportionally to their length
    i = 0
    while i < len(known):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(known) and times[j] is None:
            j += 1
        lo = times[i - 1][1] if i > 0 else 0.0
        hi = times[j][0] if j < len(known) else max(duration, lo)
        hi = max(hi, lo + 0.05 * (j - i))
        weights = [len(_fold(known[k])) + 0.6 for k in range(i, j)]
        tot = sum(weights)
        t = lo
        for k, wgt in zip(range(i, j), weights):
            span = (hi - lo) * wgt / tot
            times[k] = (t, t + span)
            t += span
        i = j
    out = []
    prev_end = 0.0
    for w, (s, e) in zip(known, times):
        s = max(s, prev_end)                       # a word never starts before the one before it ended
        e = max(e, s)
        out.append({"w": w, "s": round(start + s, 3), "e": round(start + e, 3)})
        prev_end = e
    return out, matched


def shot_words(text: str, start: float, duration: float, heard: list[dict] | None = None) -> tuple[list[dict], dict]:
    """(words, {estimated, words, aligned}) for one shot. `heard` is the recogniser's word list when there is one (the narration engine or a speech
    recogniser gave it); without it the times are estimated from the characters and the result says so."""
    if heard:
        words, matched = align_words(text, heard, start, duration)
        n = len(words)
        return words, {"estimated": matched < n, "words": n, "aligned": matched}
    words = estimated_words(text, start, duration)
    return words, {"estimated": True, "words": len(words), "aligned": 0}


def speech_span(path, *, drop_db: float = 38.0, window: float = 0.01, pad: float = 0.02) -> tuple[float, float] | None:
    """(first, last) second at which a narration WAV is audible, or None when the file is not a readable 16-bit PCM WAV (an mp3 from an online voice, no audio).

    A voice engine's file starts and ends with silence (a breath, a tail); spreading the estimated word times over the WHOLE file lets the highlight lag at the start and run
    ahead at the end. The span is found from the loudness itself: 10 ms windows, audible = within `drop_db` of the loudest window. Stdlib only (`wave`)."""
    import array
    import math
    import sys
    import wave

    try:
        with wave.open(str(path), "rb") as w:
            channels, rate, frames, width = w.getnchannels(), w.getframerate(), w.getnframes(), w.getsampwidth()
            if width != 2 or frames <= 0 or rate <= 0 or frames > rate * 900:
                return None
            raw = w.readframes(frames)
    except (OSError, EOFError, wave.Error, ValueError):
        return None
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    step = max(1, int(rate * window)) * max(1, channels)
    levels = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        levels.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)) if chunk else 0.0)
    loudest = max(levels) if levels else 0.0
    if loudest < 150:                                              # a silent or near-silent file: nothing to trim by
        return None
    floor = loudest * 10 ** (-drop_db / 20.0)
    loud = [i for i, v in enumerate(levels) if v >= floor]
    first, last = loud[0] * window, (loud[-1] + 1) * window
    return max(0.0, round(first - pad, 3)), round(min(frames / rate, last + pad), 3)


# ------------------------------------------------------------------ grouping

def group_words(words: list[dict], *, max_words: int = 7, max_chars: int = 40, max_gap: float = 0.7, max_dur: float = 4.5, fits=None) -> list[dict]:
    """Words -> screen-sized lines: [{text, s, e, words}] (absolute seconds). A new line starts at a long gap, a sentence end, after a comma once there are
    four words, at the limits, and when `fits(text)` says the line would no longer fit the allowed number of lines."""
    groups: list[dict] = []
    current: list[dict] = []

    def flush():
        if current:
            groups.append({"text": " ".join(w["w"] for w in current), "s": current[0]["s"], "e": current[-1]["e"], "words": [dict(w) for w in current]})
            current.clear()

    for word in words:
        if current:
            joined = " ".join(w["w"] for w in current) + " " + word["w"]
            prev = current[-1]
            if (word["s"] - prev["e"] > max_gap or len(current) >= max_words or len(joined) > max_chars or word["e"] - current[0]["s"] > max_dur
                    or _SENTENCE_END.search(prev["w"]) or (len(current) >= 4 and _SOFT_BREAK.search(prev["w"])) or (fits is not None and not fits(joined))):
                flush()
        current.append(word)
    flush()
    return groups


# ------------------------------------------------------------------ the clips

def place(clip: dict, width: int, height: int, zone: str, position: str = "bottom") -> dict:
    """Put a cleaned clip inside the platform's safe zone: the wrap region is the zone's width (and shifted away from a button column), the block sits just
    above the bottom band (or just under the top band; `middle` is the centre of the frame)."""
    m = safezones.margins(zone)
    clip = dict(clip)
    clip["region"] = round(1 - m["left"] - m["right"], 4)
    clip["x"] = round((m["left"] + 1 - m["right"]) / 2, 4)
    clip["y"] = 0.5
    it = titles_ass.clean({**clip, "position": "middle"})
    g = titles_ass.geometry(it, width, height)
    half = (g["block_h"] + 2 * g["pad"]) / 2
    if position == "top":
        y = m["top"] * height + half + 0.012 * height
    elif position == "middle":
        y = height / 2
    else:
        y = (1 - m["bottom"]) * height - half - 0.012 * height
    clip["y"] = round(min(max(y / height, 0.0), 1.0), 4)
    clip["position"] = position
    return clip


def caption_clips(groups: list[dict], style: dict, width: int, height: int, *, zone: str, position: str = "bottom") -> list[dict]:
    """Word groups -> cleaned, placed caption clips on the timeline. Clips never overlap (a clip ends where the next line starts) and last at least 0.3 s."""
    keys = ("font", "bold", "size", "color", "stroke_color", "stroke", "shadow", "shadow_color", "box", "box_color", "box_opacity", "box_pad", "hl_color",
            "hl_text", "hl_mode", "anim_in", "anim_dur", "align", "direction")
    base = {k: style[k] for k in keys if style.get(k) is not None}
    clips = []
    for i, group in enumerate(groups):
        start = group["s"]
        end = group["e"] + 0.2
        if i + 1 < len(groups):
            nxt = groups[i + 1]["s"]
            if nxt - start >= 0.1:
                end = min(end, nxt)
        end = max(end, start + 0.3)
        words = [{"w": w["w"], "s": round(max(0.0, w["s"] - group["s"]), 3), "e": round(max(0.0, w["e"] - group["s"]), 3)} for w in group["words"]]
        clip = titles_ass.clean({**base, "text": group["text"], "at": round(start, 3), "duration": round(end - start, 3), "words": words}, i)
        clips.append(place(clip, width, height, zone, position))
    return clips


def _line_fit(style: dict, width: int, height: int, zone: str):
    """A `fits(text)` for `group_words`: does the text stay within the preset's number of lines at this frame size and zone?"""
    m = safezones.margins(zone)
    em = style["size"] / 100.0 * height
    pad = em * style["box_pad"] / 100.0 if style["box"] else 0.0
    wrap = max(20.0, (1 - m["left"] - m["right"]) * width - 2 * pad)

    def fits(text: str) -> bool:
        return titles_ass.estimate_lines(text, em, titles_ass.wrap_budget(wrap, em, style["stroke"], style["hl_mode"], True), style["font"], style["bold"]) <= style["lines"]

    return fits


# ------------------------------------------------------------------ the whole timeline

def segments_words(segments: list[dict]) -> tuple[list[dict], dict]:
    """[{text, start, duration, heard?}] (one per shot, in timeline seconds) -> (all words, {estimated, words, aligned, segments, trimmed})."""
    words: list[dict] = []
    info = {"estimated": False, "words": 0, "aligned": 0, "segments": 0, "trimmed": 0}
    for seg in segments:
        if not str(seg.get("text") or "").strip():
            continue
        w, i = shot_words(seg["text"], float(seg["start"]), float(seg["duration"]), seg.get("heard"))
        words += w
        info["estimated"] = info["estimated"] or i["estimated"]
        info["words"] += i["words"]
        info["aligned"] += i["aligned"]
        info["segments"] += 1
        info["trimmed"] += 1 if seg.get("trimmed") else 0           # the estimate was spread over the audible part of the narration, not over its silences
    return words, info


def srt_cues(segments: list[dict]) -> list[srt.SrtCue]:
    """The soft copy: tidy two-line cues from the same word times as the burned captions. Words are grouped per shot, never across a shot boundary."""
    groups: list[dict] = []
    for seg in segments:
        w, _ = segments_words([seg])
        groups += group_words(w, max_words=14, max_chars=srt.MAX_LINE * srt.MAX_LINES, max_gap=0.9, max_dur=6.5)
    return srt.cues_from_groups(groups)


def plan(segments: list[dict], cfg: dict, width: int, height: int, *, look: dict | None = None, language: str = "fa", platform: str = "instagram",
         position: str = "bottom") -> dict:
    """The captions of a whole timeline. `segments` = [{text, start, duration, heard?}]; `cfg` = {preset, mode, zone}.
    Returns {ass (None for classic / soft / none), srt (None for none), cues, clips, info} - `info` is what the job result and the screens show:
    preset, mode, zone, language, `estimated` (True unless EVERY word time came from a recogniser), contrast ratios."""
    cfg = normalize_config(cfg)
    zone = safezones.zone_for(width, height, platform, cfg["zone"])
    words, winfo = segments_words(segments)
    info = {"preset": cfg["preset"], "mode": cfg["mode"], "zone": zone, "language": language, **winfo}
    out = {"ass": None, "srt": None, "cues": 0, "clips": [], "info": info}
    if cfg["mode"] == "none" or not words:
        return out
    cues = srt_cues(segments)
    out["srt"] = srt.to_srt(cues)
    out["cues"] = len(cues)
    if cfg["mode"] != "burned" or PRESETS[cfg["preset"]].get("legacy"):
        return out
    style = resolve_style(cfg["preset"], look, language=language)
    fits = _line_fit(style, width, height, zone)
    groups: list[dict] = []
    for seg in segments:
        w, _ = segments_words([seg])
        groups += group_words(w, max_words=style["max_words"], max_chars=48, max_gap=0.7, max_dur=4.5, fits=fits)
    clips = caption_clips(groups, style, width, height, zone=zone, position=position)
    out["clips"] = clips
    out["ass"] = titles_ass.build_ass(clips, width, height)
    out["cues"] = len(clips)
    info["contrast"] = style["contrast"]
    info["colors"] = {"text": style["color"], "highlight": style["hl_color"], "surface": style["surface"]}
    return out


def config_hash(cfg: dict, look: dict | None, language: str, platform: str, position: str) -> str:
    """Changes whenever anything that changes the captions changes (so a render made with other captions counts as stale)."""
    blob = json.dumps([normalize_config(cfg), palette_of(look), ((look or {}).get("typography") or {}), language, platform, position, "captions@1"],
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
