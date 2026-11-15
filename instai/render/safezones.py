"""Safe zones: the parts of a frame that the platform's own interface covers (profile name, caption text, like/share buttons, reply bar, the player's
control bar). Captions and titles must stay out of them.

SOURCE: ported from NMarketing:backend/services/editing/safezones.py @ v3.02 (c23f861), adapted for series/episode producers: hint texts in Persian and
English, the landscape zones of Telegram / Aparat / YouTube added, and `zone_for` picks the zone from the frame shape and the page's publishing platform.

Values are fractions of the frame, measured on the public layouts of each app - approximate on purpose (apps move their buttons), so the screens label them
"approximate". Vertical frames keep captions between the top and bottom bands (and away from the button column); landscape frames only keep the bottom
band clear of the player's control bar.
"""
from __future__ import annotations

ZONES: dict[str, dict] = {
    "reels": {"fa": "ریلز اینستاگرام", "en": "Instagram Reels",
              "hint_fa": "بالا: نام و دوربین؛ پایین: کپشن و دکمه‌ها؛ راست: لایک و کامنت",
              "hint_en": "Top: name and camera; bottom: caption and buttons; right: like and comment column",
              "margins": {"top": 0.13, "bottom": 0.22, "left": 0.05, "right": 0.14}},
    "story": {"fa": "استوریِ اینستاگرام", "en": "Instagram Story",
              "hint_fa": "بالا: نوارِ پروفایل؛ پایین: جوابِ استوری",
              "hint_en": "Top: the profile bar; bottom: the reply bar",
              "margins": {"top": 0.13, "bottom": 0.13, "left": 0.05, "right": 0.05}},
    "tiktok": {"fa": "تیک‌تاک", "en": "TikTok",
               "hint_fa": "پایین: توضیح و موسیقی؛ راست: ستونِ دکمه‌ها",
               "hint_en": "Bottom: description and music; right: the button column",
               "margins": {"top": 0.11, "bottom": 0.24, "left": 0.05, "right": 0.17}},
    "shorts": {"fa": "شورتسِ یوتیوب", "en": "YouTube Shorts",
               "hint_fa": "پایین: عنوان و کانال؛ راست: دکمه‌ها",
               "hint_en": "Bottom: title and channel; right: buttons",
               "margins": {"top": 0.10, "bottom": 0.20, "left": 0.05, "right": 0.14}},
    "feed": {"fa": "پست و مربع", "en": "Feed post / square",
             "hint_fa": "حاشیهٔ امنِ معمول",
             "hint_en": "The usual safe margin",
             "margins": {"top": 0.05, "bottom": 0.05, "left": 0.05, "right": 0.05}},
    "youtube": {"fa": "یوتیوب (افقی)", "en": "YouTube (landscape)",
                "hint_fa": "پایین: نوارِ پخش‌کننده",
                "hint_en": "Bottom: the player's control bar",
                "margins": {"top": 0.04, "bottom": 0.12, "left": 0.05, "right": 0.05}},
    "telegram": {"fa": "تلگرام (افقی)", "en": "Telegram (landscape)",
                 "hint_fa": "پایین: نوارِ پخش‌کننده",
                 "hint_en": "Bottom: the player's control bar",
                 "margins": {"top": 0.04, "bottom": 0.10, "left": 0.05, "right": 0.05}},
    "aparat": {"fa": "آپارات (افقی)", "en": "Aparat (landscape)",
               "hint_fa": "پایین: نوارِ پخش‌کننده",
               "hint_en": "Bottom: the player's control bar",
               "margins": {"top": 0.04, "bottom": 0.12, "left": 0.05, "right": 0.05}},
}
AUTO = "auto"
KEYS = [AUTO, *ZONES]
#: where each publishing platform's vertical video is shown
_VERTICAL = {"instagram": "reels", "tiktok": "tiktok", "youtube": "shorts", "telegram": "feed", "aparat": "feed"}
_LANDSCAPE = {"telegram": "telegram", "aparat": "aparat", "youtube": "youtube"}


def catalogue() -> list[dict]:
    return [{"key": k, "fa": v["fa"], "en": v["en"], "hint_fa": v["hint_fa"], "hint_en": v["hint_en"], "margins": dict(v["margins"])} for k, v in ZONES.items()]


def zone_for(width: int, height: int, platform: str = "instagram", choice: str = AUTO) -> str:
    """The zone key for a frame: the named one, or (auto) from the frame shape and the platform the page publishes to."""
    if choice in ZONES:
        return choice
    plat = (platform or "instagram").strip().lower()
    ratio = width / float(height or 1)
    if ratio < 0.7:                      # 9:16
        return _VERTICAL.get(plat, "reels")
    if ratio <= 1.2:                     # 4:5 and 1:1
        return "feed"
    return _LANDSCAPE.get(plat, "youtube")


def margins(key: str) -> dict:
    return dict(ZONES.get(key, ZONES["feed"])["margins"])


def inside(key: str, y: float, pad: float = 0.0) -> bool:
    """Is a vertical centre `y` (0..1 of the height) clear of the top and bottom bands?"""
    m = margins(key)
    return m["top"] + pad <= y <= 1 - m["bottom"] - pad
