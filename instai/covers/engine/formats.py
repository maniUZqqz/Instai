"""Sizes and "safe areas" of every platform a cover goes to (YouTube, Aparat, Telegram, Instagram, Reels / Shorts, channel banner, series poster).

Each format has the exact output size, a safe margin for the title and a few "avoid zones": places where the platform itself draws something
over the picture (the video length, the reply bar of a story, the profile-grid crop ...). The layouts keep important text out of these zones
(``render.Ctx``) and the preview can draw them as guide lines.

The numbers are APPROXIMATE (taken from each platform's public guidelines; a platform may change them), so the user is told "approximate".
Nothing was copied from a platform except the sizes.

SOURCE: ported from NMarketing:backend/apps/thumbs/formats.py @ v3.02 (c23f861), adapted for series/episode covers
(pinterest dropped; yt_banner and season_card added; every title and note in Persian and English).
"""
from __future__ import annotations

from dataclasses import dataclass, field

Rect = tuple[float, float, float, float]       # x0, y0, x1, y1 (fractions of the canvas)
#: x0, y0, x1, y1, note (Persian), note (English)
Avoid = tuple[float, float, float, float, str, str]


@dataclass(frozen=True)
class Format:
    key: str
    title_fa: str
    title_en: str
    platform_fa: str              # group in the menu
    platform_en: str
    size: tuple[int, int]
    #: safe margin of the title: left, top, right, bottom (fractions of width / height)
    margin: tuple[float, float, float, float]
    avoid: tuple[Avoid, ...] = ()
    note_fa: str = ""
    note_en: str = ""
    #: JPEG size cap in kilobytes; 0 = no cap
    max_kb: int = 0
    aspect_label: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)

    @property
    def w(self) -> int:
        return self.size[0]

    @property
    def h(self) -> int:
        return self.size[1]

    @property
    def orient(self) -> str:
        return orientation(self.size)

    def public(self) -> dict:
        return {"key": self.key, "title_fa": self.title_fa, "title_en": self.title_en, "platform_fa": self.platform_fa, "platform_en": self.platform_en,
                "width": self.w, "height": self.h, "aspect": self.aspect_label, "orient": self.orient, "note_fa": self.note_fa, "note_en": self.note_en,
                "max_kb": self.max_kb, "margin": list(self.margin),
                "avoid": [{"rect": list(a[:4]), "note_fa": a[4], "note_en": a[5]} for a in self.avoid]}


def orientation(size: tuple[int, int]) -> str:
    """wide: 16:9 and wider · square: close to a square · portrait: 4:5 · tall: 2:3 and taller (story, poster)."""
    w, h = size
    r = w / float(h)
    if r >= 1.3:
        return "wide"
    if r >= 0.95:
        return "square"
    if r >= 0.72:
        return "portrait"
    return "tall"


FORMATS: dict[str, Format] = {f.key: f for f in (
    Format("youtube", "کاور یوتیوب", "YouTube cover", "ویدیو", "Video", (1280, 720), (0.045, 0.06, 0.045, 0.07),
           avoid=((0.82, 0.84, 1.0, 1.0, "مدتِ ویدیو (پایین-راست)", "Video length (bottom right)"),),
           note_fa="۱۲۸۰×۷۲۰ — کمتر از ۲ مگابایت؛ مدتِ ویدیو گوشهٔ پایین-راست را می‌پوشاند (تقریبی).",
           note_en="1280x720 - under 2 MB; the video length covers the bottom-right corner (approximate).", max_kb=2000, aspect_label="16:9",
           keywords=("یوتیوب", "youtube", "ویدیو")),
    Format("aparat", "کاور آپارات", "Aparat cover", "ویدیو", "Video", (1280, 720), (0.045, 0.06, 0.045, 0.08),
           avoid=((0.0, 0.84, 0.16, 1.0, "مدتِ ویدیو (پایین-چپ)", "Video length (bottom left)"),),
           note_fa="۱۲۸۰×۷۲۰ — مدتِ ویدیو گوشهٔ پایین را می‌پوشاند (تقریبی).",
           note_en="1280x720 - the video length covers the bottom corner (approximate).", max_kb=2000, aspect_label="16:9", keywords=("آپارات", "aparat")),
    Format("telegram", "کاور تلگرام", "Telegram cover", "پیام‌رسان", "Messenger", (1280, 720), (0.05, 0.07, 0.05, 0.07),
           avoid=((0.0, 0.0, 0.17, 0.12, "مدتِ ویدیو (بالا-چپ)", "Video length (top left)"),),
           note_fa="۱۲۸۰×۷۲۰ — پیش‌نمایشِ پست و ویدیو در کانال (تقریبی).",
           note_en="1280x720 - the preview of a post or video in a channel (approximate).", max_kb=2000, aspect_label="16:9", keywords=("تلگرام", "telegram")),
    Format("ig_portrait", "پستِ اینستاگرام ۴:۵", "Instagram post 4:5", "اینستاگرام", "Instagram", (1080, 1350), (0.07, 0.06, 0.07, 0.06),
           avoid=((0.0, 0.0, 0.032, 1.0, "بریدهٔ شبکهٔ پروفایل (چپ)", "Profile grid crop (left)"),
                  (0.968, 0.0, 1.0, 1.0, "بریدهٔ شبکهٔ پروفایل (راست)", "Profile grid crop (right)")),
           note_fa="۱۰۸۰×۱۳۵۰ — در شبکهٔ پروفایل از دو طرف کمی بریده می‌شود؛ متنِ مهم را وسط نگه دارید.",
           note_en="1080x1350 - the profile grid crops a little from both sides; keep the important text in the middle.", aspect_label="4:5",
           keywords=("اینستاگرام", "instagram", "پست")),
    Format("ig_square", "پستِ اینستاگرام مربع", "Instagram post square", "اینستاگرام", "Instagram", (1080, 1080), (0.07, 0.07, 0.07, 0.07),
           note_fa="۱۰۸۰×۱۰۸۰ — مربعِ کلاسیک.", note_en="1080x1080 - the classic square.", aspect_label="1:1", keywords=("اینستاگرام", "مربع", "square")),
    Format("story", "کاور ریلز / شورتس", "Reels / Shorts cover", "ریلز و شورتس", "Reels and Shorts", (1080, 1920), (0.07, 0.13, 0.07, 0.18),
           avoid=((0.0, 0.0, 1.0, 0.13, "نوارِ بالا (پروفایل و پیشرفت)", "Top bar (profile and progress)"),
                  (0.0, 0.82, 1.0, 1.0, "نوارِ پاییِ پاسخ/دکمه‌ها", "Bottom bar (reply / buttons)")),
           note_fa="۱۰۸۰×۱۹۲۰ — بالا (۱۳٪) و پایین (۱۸٪) را رابطِ برنامه می‌پوشاند؛ در شبکهٔ پروفایل فقط بخشِ میانی (۳:۴) دیده می‌شود (تقریبی).",
           note_en="1080x1920 - the app interface covers the top (13%) and the bottom (18%); the profile grid shows only the middle part (3:4) (approximate).",
           aspect_label="9:16", keywords=("ریلز", "شورتس", "استوری", "reels", "shorts", "story")),
    Format("poster", "پوستر سریال ۲:۳", "Series poster 2:3", "پوستر", "Poster", (1200, 1800), (0.07, 0.05, 0.07, 0.05),
           note_fa="۱۲۰۰×۱۸۰۰ (۲:۳) — نسبتِ پوستر.", note_en="1200x1800 (2:3) - the poster ratio.", aspect_label="2:3", keywords=("پوستر", "سریال", "poster")),
    Format("yt_banner", "بنر کانال یوتیوب", "YouTube channel banner", "کانال", "Channel", (2560, 1440), (0.198, 0.353, 0.198, 0.353),
           note_fa="۲۵۶۰×۱۴۴۰ — فقط ناحیهٔ مرکزیِ حدودِ ۱۵۴۶×۴۲۳ روی همهٔ دستگاه‌ها دیده می‌شود؛ متن را همان‌جا نگه دارید (تقریبی).",
           note_en="2560x1440 - only the centre area of about 1546x423 shows on every device; keep the text there (approximate).", max_kb=6000,
           aspect_label="16:9", keywords=("بنر", "کانال", "banner", "channel")),
    Format("season_card", "کارت فصل ۱۶:۹", "Season card 16:9", "ویدیو", "Video", (1920, 1080), (0.05, 0.07, 0.05, 0.07),
           note_fa="۱۹۲۰×۱۰۸۰ — کارتِ آغازِ فصل یا فهرستِ قسمت‌ها (بدونِ ناحیهٔ ممنوع).",
           note_en="1920x1080 - the title card of a season or the episode list (no avoid zones).", aspect_label="16:9", keywords=("فصل", "season", "کارت")),
)}

DEFAULT_FORMAT = "youtube"


class UnknownFormat(KeyError):
    pass


def get(key: str) -> Format:
    try:
        return FORMATS[key]
    except KeyError as exc:
        raise UnknownFormat(key) from exc


def scaled(fmt: Format, scale: float) -> tuple[int, int]:
    """Canvas size at a scale (preview = smaller). Always even and at least 80 px."""
    s = max(0.05, float(scale))
    return max(80, int(round(fmt.w * s / 2) * 2)), max(80, int(round(fmt.h * s / 2) * 2))


def px_rect(rect: Rect, size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    return int(round(rect[0] * w)), int(round(rect[1] * h)), int(round(rect[2] * w)), int(round(rect[3] * h))


def safe_rect(fmt: Format, size: tuple[int, int]) -> tuple[int, int, int, int]:
    w, h = size
    l, t, r, b = fmt.margin
    return int(round(w * l)), int(round(h * t)), int(round(w * (1 - r))), int(round(h * (1 - b)))


def avoid_rects(fmt: Format, size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    return [px_rect(a[:4], size) for a in fmt.avoid]
