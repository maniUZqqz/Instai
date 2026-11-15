"""The fixed vocabulary of motion: easing curves, springs, camera moves, exits, enters, transitions, and the «safe area» of every platform.

SOURCE: ported from NMarketing:backend/apps/motion/motionlib.py @ motion v2, adapted for InstAI: platform names are the networks of an animation / film
channel (YouTube, Shorts, Reels, story, TikTok, Telegram, Aparat, ...) with labels in Persian and English; the transition and enter names are the ones
remotion/src/components/anim.ts draws.

A model NEVER writes a curve or spring numbers: it picks a NAME from these lists. Every name also exists in remotion/src/components/presets.ts / anim.ts
and tests/test_motion_plan.py compares the two sides.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = json.loads((ROOT / "remotion" / "src" / "components" / "adapter.json").read_text(encoding="utf-8"))

EASES = ("linear", "smooth", "out", "in", "out-soft", "out-expo", "in-out-expo", "snap", "back", "in-back", "elastic", "bounce")
SPRINGS = ("gentle", "smooth", "snappy", "crisp", "bouncy", "elastic", "heavy", "slow-reveal")
CAMERA_MOVES = ("none", "push-in", "pull-out", "pan-left", "pan-right", "pan-up", "pan-down", "drift", "parallax", "rise")
EXIT_KINDS = ("none", "fade", "slide", "zoom", "drop")
ENTER_KINDS = ("pop", "rise", "drop", "slide", "wipe", "type", "scan", "flip", "unfold", "spin", "blur", "bloom", "stamp", "swing", "build",
               "glitch", "sweep", "squash", "zoompunch", "float", "slam", "lightup", "grow", "fade")
TRANS_KINDS = ("cut", "fade", "dip", "slide", "push", "cover", "wipe", "wipe-diag", "zoom", "iris", "curtain", "flip", "spin", "whip", "glitch", "roll",
               "blocks", "flash", "ink")
TRANSITION_PACK = ("wipe", "push", "zoom", "ink", "glitch", "iris")
ALIGNS = ("center", "start", "end")

#: the safe area of each platform: the fraction of the frame that the app's own UI (name, buttons, caption) covers. Approximate figures from the
#: platforms' published guides (labelled approximate in the page); the layout keeps text out of these margins and qa.py measures the same numbers.
PLATFORMS = {
    "shorts": {"fa": "یوتیوب شورتس", "en": "YouTube Shorts", "size": "vertical", "safe": {"top": 0.10, "right": 0.12, "bottom": 0.20, "left": 0.06}},
    "reels": {"fa": "ریلز اینستاگرام", "en": "Instagram Reels", "size": "vertical", "safe": {"top": 0.14, "right": 0.10, "bottom": 0.22, "left": 0.06}},
    "story": {"fa": "استوری", "en": "Story", "size": "vertical", "safe": {"top": 0.14, "right": 0.06, "bottom": 0.14, "left": 0.06}},
    "tiktok": {"fa": "تیک‌تاک", "en": "TikTok", "size": "vertical", "safe": {"top": 0.12, "right": 0.14, "bottom": 0.24, "left": 0.06}},
    "feed": {"fa": "پست مربع", "en": "Square post", "size": "square", "safe": {"top": 0.05, "right": 0.05, "bottom": 0.07, "left": 0.05}},
    "youtube": {"fa": "یوتیوب (افقی)", "en": "YouTube (landscape)", "size": "landscape", "safe": {"top": 0.05, "right": 0.05, "bottom": 0.09, "left": 0.05}},
    "telegram": {"fa": "تلگرام / آپارات (افقی)", "en": "Telegram / Aparat (landscape)", "size": "landscape", "safe": {"top": 0.04, "right": 0.04, "bottom": 0.06, "left": 0.04}},
    "": {"fa": "بدون پلتفرم", "en": "No platform", "size": "", "safe": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0}},
}
DEFAULT_PLATFORM = {"vertical": "shorts", "square": "feed", "landscape": "youtube"}
SIZES = {"landscape": (1920, 1080), "vertical": (1080, 1920), "square": (1080, 1080)}

# typography and timing rules (the reference of qa.py and of the model's guide)
READ_S_PER_WORD = 0.32          # the least time to read one Persian word (seconds): Persian is read more slowly than English
READ_S_PER_WORD_EN = 0.26
ENTRANCE_S = 0.7                # elements enter for this long; reading time starts after it
MIN_FONT_FRAC = 0.018           # smallest wanted text size relative to the frame height (about 35 px of 1920); below 1.65 % a warning, below 1.3 % an error
MIN_FONT_WARN = 0.0165
MIN_FONT_ERROR = 0.013
MIN_CONTRAST = 3.0              # WCAG for large text; below it the colour is fixed (small text: 4.5)
MIN_CONTRAST_SMALL = 4.5
MAX_SIMULTANEOUS = 12           # more moving things than this = crowded
MAX_WORDS_PER_SCENE = 38        # a scene with more words is split


def platform_safe(platform: str, size: str = "") -> dict:
    """The safe-area fractions; an unknown platform = zero (the engine's default layout)."""
    return dict((PLATFORMS.get(platform or "") or PLATFORMS[""])["safe"])


def platform_label(platform: str, lang: str = "fa") -> str:
    return (PLATFORMS.get(platform or "") or PLATFORMS[""])[lang if lang in ("fa", "en") else "fa"]


# ───────────────────────────────────────────── the style adapter (python side): StyleKit -> the motion tokens the Remotion side derives
# One table (remotion/src/components/adapter.json) is read by the Remotion bundle (ctx.tsx styleFromKit) and here, so the timeline the python side
# computes (transition overlaps) is the one the renderer draws.

def personality(kit: dict) -> dict:
    """{enter, spring, trans: {kind, frames}} of the kit's animation style."""
    return ADAPTER["personalities"].get((kit or {}).get("animation") or "", ADAPTER["personalities"]["motion_graphics"])


def style_trans(kit: dict) -> tuple[str, int]:
    t = personality(kit)["trans"]
    return str(t["kind"]), int(t["frames"])
