"""Synthetic vector pictures for the layout previews and the tests (no photo of a real person and no data of anybody).

* ``person()`` - a cartoon bust (RGBA, cut out) with a smile, standing in for a character face.
* ``prop()``   - a simple bottle / box with a highlight (RGBA), standing in for an object.
* ``scene()``  - a made-up landscape (RGB) for a photo background.

SOURCE: ported from NMarketing:backend/apps/thumbs/fixtures.py @ v3.02 (c23f861), adapted for series/episode covers (product() is prop()).
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from . import primitives as P


def person(size: tuple[int, int] = (640, 820), skin: str = "#f2c29b", shirt: str = "#2563eb", hair: str = "#2b1d14",
           mood: str = "happy") -> Image.Image:
    W, H = size
    k = 3
    big = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    # shoulders
    d.ellipse([W * 0.04 * k, H * 0.62 * k, W * 0.96 * k, H * 1.35 * k], fill=P.rgba(shirt))
    d.rectangle([W * 0.04 * k, H * 0.95 * k, W * 0.96 * k, H * k], fill=P.rgba(shirt))
    # neck
    d.rounded_rectangle([W * 0.4 * k, H * 0.5 * k, W * 0.6 * k, H * 0.7 * k], radius=W * 0.05 * k, fill=P.rgba(P.lerp_hex(skin, "#000000", 0.12)))
    # head
    cx, cy, rw, rh = W * 0.5, H * 0.34, W * 0.27, H * 0.24
    d.ellipse([(cx - rw) * k, (cy - rh) * k, (cx + rw) * k, (cy + rh) * k], fill=P.rgba(skin))
    # hair
    d.chord([(cx - rw * 1.04) * k, (cy - rh * 1.1) * k, (cx + rw * 1.04) * k, (cy - rh * 0.05) * k], 180, 360, fill=P.rgba(hair))
    # ears
    for sx in (-1, 1):
        d.ellipse([(cx + sx * rw * 0.98 - W * 0.03) * k, (cy - H * 0.02) * k, (cx + sx * rw * 0.98 + W * 0.03) * k, (cy + H * 0.06) * k], fill=P.rgba(skin))
    # eyes
    for sx in (-1, 1):
        ex = cx + sx * rw * 0.42
        d.ellipse([(ex - W * 0.045) * k, (cy - H * 0.03) * k, (ex + W * 0.045) * k, (cy + H * 0.045) * k], fill=(255, 255, 255, 255))
        d.ellipse([(ex - W * 0.022) * k, (cy - H * 0.01) * k, (ex + W * 0.022) * k, (cy + H * 0.04) * k], fill=(30, 30, 40, 255))
        d.line([((ex - W * 0.06) * k, (cy - H * 0.06) * k), ((ex + W * 0.05) * k, (cy - H * 0.075) * k)], fill=P.rgba(hair), width=int(W * 0.012 * k))
    # mouth
    if mood == "happy":
        d.chord([(cx - rw * 0.45) * k, (cy + rh * 0.18) * k, (cx + rw * 0.45) * k, (cy + rh * 0.8) * k], 0, 180, fill=(120, 30, 40, 255))
        d.chord([(cx - rw * 0.4) * k, (cy + rh * 0.18) * k, (cx + rw * 0.4) * k, (cy + rh * 0.34) * k], 0, 180, fill=(255, 255, 255, 255))
    else:
        d.arc([(cx - rw * 0.3) * k, (cy + rh * 0.35) * k, (cx + rw * 0.3) * k, (cy + rh * 0.7) * k], 200, 340, fill=(120, 30, 40, 255), width=int(W * 0.014 * k))
    out = big.resize((W, H), Image.Resampling.LANCZOS)
    # a soft light on the face and a shade under the chin
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - rw * 0.7, cy - rh * 0.9, cx + rw * 0.1, cy - rh * 0.1], fill=(255, 255, 255, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.04))
    a = out.getchannel("A")
    out = Image.alpha_composite(out, glow)
    out.putalpha(a)
    return out


def prop(size: tuple[int, int] = (520, 760), color: str = "#e11d48", cap: str = "#111827") -> Image.Image:
    W, H = size
    k = 3
    big = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([W * 0.2 * k, H * 0.2 * k, W * 0.8 * k, H * 0.98 * k], radius=W * 0.12 * k, fill=P.rgba(color))
    d.rounded_rectangle([W * 0.32 * k, H * 0.04 * k, W * 0.68 * k, H * 0.22 * k], radius=W * 0.04 * k, fill=P.rgba(cap))
    d.rounded_rectangle([W * 0.28 * k, H * 0.42 * k, W * 0.72 * k, H * 0.7 * k], radius=W * 0.05 * k, fill=(255, 255, 255, 235))
    d.rounded_rectangle([W * 0.34 * k, H * 0.5 * k, W * 0.66 * k, H * 0.54 * k], radius=W * 0.02 * k, fill=P.rgba(cap))
    d.rounded_rectangle([W * 0.34 * k, H * 0.58 * k, W * 0.56 * k, H * 0.61 * k], radius=W * 0.015 * k, fill=P.rgba(color))
    out = big.resize((W, H), Image.Resampling.LANCZOS)
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle([W * 0.25, H * 0.26, W * 0.33, H * 0.9], radius=W * 0.04, fill=(255, 255, 255, 70))
    hl = hl.filter(ImageFilter.GaussianBlur(W * 0.015))
    a = out.getchannel("A")
    out = Image.alpha_composite(out, hl)
    out.putalpha(a)
    return out


def scene(size: tuple[int, int] = (1280, 800), seed: int = 4, palette: tuple[str, str, str] = ("#0ea5e9", "#a7f3d0", "#f59e0b")
          ) -> Image.Image:
    rnd = random.Random(seed)
    W, H = size
    img = P.gradient(size, [(0.0, palette[0]), (0.55, palette[1]), (1.0, palette[2])], 90).convert("RGBA")
    d = ImageDraw.Draw(img)
    for i in range(3):                                   # hills
        y0 = H * (0.55 + 0.1 * i)
        pts = [(0, H)] + [(x, y0 + math.sin(x / W * 6 + i + rnd.random()) * H * 0.06) for x in range(0, W + 40, 40)] + [(W, H)]
        d.polygon(pts, fill=P.rgba(P.lerp_hex(palette[1], "#14532d", 0.35 + 0.2 * i), 255))
    sun = (int(W * 0.72), int(H * 0.28), int(H * 0.09))
    d.ellipse([sun[0] - sun[2], sun[1] - sun[2], sun[0] + sun[2], sun[1] + sun[2]], fill=(255, 244, 200, 255))
    return img.convert("RGB").filter(ImageFilter.GaussianBlur(1.2))


# ───────────────────────────── a synthetic series for the tests, the self-test and the documentation pictures

#: the colours of the owner's own product (docs/chagher/brand-facts-fa.md of NMarketing): turquoise and navy
CHAGHER_COLORS = ["#126F85", "#163F75"]


def sample_context(lang: str = "fa") -> dict:
    """A made-up mini-series in the style of the owner's product: NO price, statistic or claim; the people are invented. The facts a cover reads (``hooks.make_ctx``)."""
    if lang == "en":
        return {"lang": "en", "kind": "episode", "series": "Chagher Adventures", "episode_number": 1, "episode_title": "The Coach and the Missing Bag",
                "logline": "A coach has to find a lost sports bag before the class starts", "hook": "Where is the coach's bag?", "cliffhanger": "And suddenly the gym door opened",
                "premise": "A coach and an assistant; one small adventure in every episode", "branch_point": "The coach arrives early to the gym",
                "characters": ["Coach", "Assistant"], "channel": "Chagher Channel", "dialogue": [["Coach", "I left it right here a minute ago"]], "choices": ["Go inside", "Go outside"]}
    return {"lang": "fa", "kind": "episode", "series": "ماجراهای چغر", "episode_number": 1, "episode_title": "مربی چغر و رازِ کیفِ گم‌شده",
            "logline": "مربی باید پیش از شروعِ کلاس کیفِ ورزشیِ گم‌شده را پیدا کند", "hook": "کیفِ ورزشیِ مربی کجاست؟", "cliffhanger": "و ناگهان دَرِ باشگاه باز شد",
            "premise": "یک مربی و یک دستیار؛ در هر قسمت یک ماجرای کوچک", "branch_point": "مربی زودتر به باشگاه می‌رسد", "characters": ["مربی چغر", "دستیار"], "channel": "کانال چغر",
            "dialogue": [["مربی چغر", "همین یک دقیقه پیش همین‌جا بود"]], "choices": ["برو توی باشگاه", "برو بیرون"]}


def sample_content(lang: str = "fa") -> dict:
    """Every content field filled (what the matrix tests give each layout)."""
    if lang == "en":
        return {"title": "The *Coach* and the Missing Bag", "subtitle": "The first workout", "kicker": "Chagher Adventures", "number": "1", "badge": "NEW", "tagline": "A sporty adventure",
                "credits": "Voice: Sample Name | Writer: Sample Name", "channel": "Chagher Channel", "label_a": "Go to the gym", "label_b": "Go outside"}
    return {"title": "*مربی* چغر و رازِ کیفِ گم‌شده", "subtitle": "اولین تمرین", "kicker": "ماجراهای چغر", "number": "۱", "badge": "جدید", "tagline": "یک ماجرای ورزشی",
            "credits": "صدا: نام نمونه | نویسنده: نام نمونه", "channel": "کانال چغر", "label_a": "برو تو باشگاه", "label_b": "برو بیرون"}
