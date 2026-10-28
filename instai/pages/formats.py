"""Format registry: the platform is not limited to the three launch formats. Each format declares its wizard defaults,
default techniques and content-policy flags. Add a format here and the wizard, planner and policy notices pick it up."""
from __future__ import annotations

ANIME = "anime_whatif"
CHARACTER = "recurring_character"
EXPLAINER = "concept_explainer"
CUSTOM = "custom"

FORMATS: dict[str, dict] = {
    ANIME: {
        "label_fa": "انیمه «چه می‌شد اگر…»", "label_en": "Anime What-If",
        "description_fa": "یک داستان را با تغییر یک رویداد کلیدی بازروایت می‌کند: تصمیم دیگر، نقش جابه‌جا، پایان متفاوت.",
        "needs": ["premise", "branch_point", "alternative_timeline", "characters", "episode_goals", "cliffhangers"],
        "default_techniques": ["still_kenburns", "parallax_25d", "wan_i2v"],
        "default_series": {"episodes": 5, "episode_length_sec": 45},
        "policy": {"original_default": True, "fan_notice": True, "sourced": False, "synthetic_presenter_only": False},
        "idea_hint_fa": "مثلاً: اگر قهرمانِ جهانی خیالی در لحظه‌ی نبرد آخر متحدش را نجات نمی‌داد…",
    },
    CHARACTER: {
        "label_fa": "شخصیت کارتونیِ تکرارشونده", "label_en": "Recurring 2D character",
        "description_fa": "یک شخصیت ثابت در موقعیت‌های مختلف: کمدی روزمره، فعالیت‌ها، شوخی‌های تکرارشونده و داستان کوتاه.",
        "needs": ["characters", "reference_sheet", "voice", "recurring_jokes", "backgrounds"],
        "default_techniques": ["puppet_2d", "still_kenburns"],
        "default_series": {"episodes": 6, "episode_length_sec": 30},
        "policy": {"original_default": True, "fan_notice": False, "sourced": False, "synthetic_presenter_only": False},
        "idea_hint_fa": "مثلاً: یک گربه‌ی کارتونی که هر روز با یک وسیله‌ی خانگی دردسر پیدا می‌کند.",
    },
    EXPLAINER: {
        "label_fa": "توضیح مفاهیم", "label_en": "Concept explainer",
        "description_fa": "مجری (کارتونی ۲بعدی، سه‌بعدی سبک‌دار یا واقع‌نما در صورت مجاز بودن) مفاهیم سخت را ساده توضیح می‌دهد؛ با منبع و راستی‌آزمایی.",
        "needs": ["research", "sources", "analogies", "visual_metaphors", "fact_check"],
        "default_techniques": ["motion_graphics", "still_kenburns", "puppet_2d"],
        "default_series": {"episodes": 5, "episode_length_sec": 60},
        "policy": {"original_default": False, "fan_notice": False, "sourced": True, "synthetic_presenter_only": True},
        "idea_hint_fa": "مثلاً: سرمایه‌داری چیست؟ چندجهانی در فیزیک یعنی چه؟ فاشیسم چگونه تعریف می‌شود؟",
    },
    CUSTOM: {
        "label_fa": "قالب دلخواه", "label_en": "Custom",
        "description_fa": "قالب عمومی برای ایده‌هایی که در سه قالب بالا نمی‌گنجد.",
        "needs": ["premise", "characters"],
        "default_techniques": ["still_kenburns", "parallax_25d"],
        "default_series": {"episodes": 5, "episode_length_sec": 45},
        "policy": {"original_default": True, "fan_notice": False, "sourced": False, "synthetic_presenter_only": False},
        "idea_hint_fa": "ایده‌ی خودتان را بنویسید.",
    },
}

FAN_NOTICE_FA = ("هشدار: استفاده از شخصیت‌ها، نام‌ها یا آثار هنریِ یک فرانچایز، حق تجاری به شما نمی‌دهد و ممکن است باعث ادعای کپی‌رایت "
                 "یا حذف محتوا در شبکه‌های اجتماعی شود. حالت پیش‌فرض: شخصیت‌های اورجینال و جهان‌های «الهام‌گرفته».")
EXPLAINER_NOTICE_FA = ("محتوای ایدئولوژی، سیاست، تاریخ و علم باید بی‌طرف و مستند باشد؛ ادعاهای مناقشه‌برانگیز برچسب می‌خورند و منابع کنار قسمت ذخیره می‌شوند.")
PRESENTER_NOTICE_FA = "مجریِ واقع‌نما فقط با هویت ساختگی یا با رضایت صاحب چهره مجاز است؛ تقلید از افراد واقعی ممنوع است."

STYLES = [
    {"key": "anime_soft", "label_fa": "انیمه‌ی نرم و رنگارنگ", "prompt": "anime style, soft cel shading, warm colours, clean line art"},
    {"key": "anime_dark", "label_fa": "انیمه‌ی تیره و سینمایی", "prompt": "dark cinematic anime, dramatic lighting, high contrast"},
    {"key": "cartoon_flat", "label_fa": "کارتون تخت و ساده", "prompt": "flat 2D cartoon, bold shapes, limited palette"},
    {"key": "storybook", "label_fa": "تصویرسازی کتاب کودک", "prompt": "storybook illustration, watercolour textures"},
    {"key": "infographic", "label_fa": "اینفوگرافیک و نمودار", "prompt": "clean infographic style, vector shapes, minimal icons"},
]

PRESETS = {
    "preview": {"label_fa": "پیش‌نمایش سریع", "note_fa": "تصویر ثابت، وضوح کم، بدون ویدئوی Wan"},
    "balanced": {"label_fa": "متعادل", "note_fa": "ترکیب تکنیک‌ها؛ فقط چند شات اصلی با Wan"},
    "quality": {"label_fa": "کیفیت بالا", "note_fa": "شات‌های بیشتر با Wan؛ زمان GPU بسیار بیشتر"},
    "overnight": {"label_fa": "شبانه", "note_fa": "صف طولانی برای اجرای شبانه"},
}


def get_format(key: str) -> dict:
    return FORMATS.get(key) or FORMATS[CUSTOM]


def choices() -> list[tuple[str, str]]:
    return [(k, v["label_en"]) for k, v in FORMATS.items()]


def public_registry() -> dict:
    return {"formats": [{"key": k, **v} for k, v in FORMATS.items()], "styles": STYLES, "presets": PRESETS,
            "notices": {"fan": FAN_NOTICE_FA, "explainer": EXPLAINER_NOTICE_FA, "presenter": PRESENTER_NOTICE_FA}}
