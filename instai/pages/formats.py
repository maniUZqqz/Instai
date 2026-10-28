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
        "description_en": 'Retells a story with one key event changed: another decision, a swapped role, a different ending.', "idea_hint_en": 'e.g. what if the hero had not saved their ally in the final battle...',
    },
    CHARACTER: {
        "label_fa": "شخصیت کارتونیِ تکرارشونده", "label_en": "Recurring 2D character",
        "description_fa": "یک شخصیت ثابت در موقعیت‌های مختلف: کمدی روزمره، فعالیت‌ها، شوخی‌های تکرارشونده و داستان کوتاه.",
        "needs": ["characters", "reference_sheet", "voice", "recurring_jokes", "backgrounds"],
        "default_techniques": ["puppet_2d", "still_kenburns"],
        "default_series": {"episodes": 6, "episode_length_sec": 30},
        "policy": {"original_default": True, "fan_notice": False, "sourced": False, "synthetic_presenter_only": False},
        "idea_hint_fa": "مثلاً: یک گربه‌ی کارتونی که هر روز با یک وسیله‌ی خانگی دردسر پیدا می‌کند.",
        "description_en": 'One steady character in many situations: everyday comedy, activities, running gags and short stories.', "idea_hint_en": 'e.g. a cartoon cat who gets into trouble with a household gadget every day.',
    },
    EXPLAINER: {
        "label_fa": "توضیح مفاهیم", "label_en": "Concept explainer",
        "description_fa": "مجری (کارتونی ۲بعدی، سه‌بعدی سبک‌دار یا واقع‌نما در صورت مجاز بودن) مفاهیم سخت را ساده توضیح می‌دهد؛ با منبع و راستی‌آزمایی.",
        "needs": ["research", "sources", "analogies", "visual_metaphors", "fact_check"],
        "default_techniques": ["motion_graphics", "still_kenburns", "puppet_2d"],
        "default_series": {"episodes": 5, "episode_length_sec": 60},
        "policy": {"original_default": False, "fan_notice": False, "sourced": True, "synthetic_presenter_only": True},
        "idea_hint_fa": "مثلاً: سرمایه‌داری چیست؟ چندجهانی در فیزیک یعنی چه؟ فاشیسم چگونه تعریف می‌شود؟",
        "description_en": 'A presenter (2D cartoon, stylised 3D, or a real-looking presenter where permitted) explains hard ideas simply, with sources and fact-checking.', "idea_hint_en": 'e.g. what is capitalism? what does multiverse mean in physics? how is fascism defined?',
    },
    CUSTOM: {
        "label_fa": "قالب دلخواه", "label_en": "Custom",
        "description_fa": "قالب عمومی برای ایده‌هایی که در سه قالب بالا نمی‌گنجد.",
        "needs": ["premise", "characters"],
        "default_techniques": ["still_kenburns", "parallax_25d"],
        "default_series": {"episodes": 5, "episode_length_sec": 45},
        "policy": {"original_default": True, "fan_notice": False, "sourced": False, "synthetic_presenter_only": False},
        "idea_hint_fa": "ایده‌ی خودتان را بنویسید.",
        "description_en": 'A general format for ideas that do not fit the three above.', "idea_hint_en": 'Write your own idea.',
    },
}

FAN_NOTICE_FA = ("هشدار: استفاده از شخصیت‌ها، نام‌ها یا آثار هنریِ یک فرانچایز، حق تجاری به شما نمی‌دهد و ممکن است باعث ادعای کپی‌رایت "
                 "یا حذف محتوا در شبکه‌های اجتماعی شود. حالت پیش‌فرض: شخصیت‌های اورجینال و جهان‌های «الهام‌گرفته».")
EXPLAINER_NOTICE_FA = ("محتوای ایدئولوژی، سیاست، تاریخ و علم باید بی‌طرف و مستند باشد؛ ادعاهای مناقشه‌برانگیز برچسب می‌خورند و منابع کنار قسمت ذخیره می‌شوند.")
PRESENTER_NOTICE_FA = "مجریِ واقع‌نما فقط با هویت ساختگی یا با رضایت صاحب چهره مجاز است؛ تقلید از افراد واقعی ممنوع است."

FAN_NOTICE_EN = ("Warning: using a franchise's characters, names or artwork does not give you commercial rights and may cause copyright claims or "
                 "takedowns on social networks. Default: original characters and 'inspired-by' worlds.")
EXPLAINER_NOTICE_EN = ("Ideology, politics, history and science content must be neutral and sourced; contested claims are labelled and the sources are stored with the episode.")
PRESENTER_NOTICE_EN = "A real-looking presenter is allowed only with a synthetic identity or with the face owner's consent; imitating real people is forbidden."


class _LiveStyles(list):
    """`formats.STYLES`: the built-in style presets plus the owner's own (database), looked up at iteration time.

    Production code finds a page's style with `next(s["prompt"] for s in formats.STYLES if s["key"] == style_key)`; iterating a live
    list means presets the owner adds or duplicates in the library work there without any change to that code.
    """

    def __iter__(self):
        from instai.styles import library

        try:
            return iter(library.live_style_entries())
        except Exception:  # noqa: BLE001 - the registry must never break a page
            return iter(list.__iter__(self))

    def __len__(self):
        return len(list(iter(self)))


STYLES = _LiveStyles()

PRESETS = {
    "preview": {"label_fa": "پیش‌نمایش سریع", "note_fa": "تصویر ثابت، وضوح کم، بدون ویدئوی Wan",
                "label_en": "Quick preview", "note_en": "Still images, low resolution, no Wan video"},
    "balanced": {"label_fa": "متعادل", "note_fa": "ترکیب تکنیک‌ها؛ فقط چند شات اصلی با Wan",
                 "label_en": "Balanced", "note_en": "A mix of techniques; Wan only for a few hero shots"},
    "quality": {"label_fa": "کیفیت بالا", "note_fa": "شات‌های بیشتر با Wan؛ زمان GPU بسیار بیشتر",
                "label_en": "High quality", "note_en": "More Wan shots; much more GPU time"},
    "overnight": {"label_fa": "شبانه", "note_fa": "صف طولانی برای اجرای شبانه",
                  "label_en": "Overnight", "note_en": "A long queue meant to run overnight"},
}


def get_format(key: str) -> dict:
    return FORMATS.get(key) or FORMATS[CUSTOM]


def choices() -> list[tuple[str, str]]:
    return [(k, v["label_en"]) for k, v in FORMATS.items()]


def public_registry() -> dict:
    return {"formats": [{"key": k, **v} for k, v in FORMATS.items()], "styles": list(STYLES), "presets": PRESETS,
            "notices": {"fan": FAN_NOTICE_FA, "explainer": EXPLAINER_NOTICE_FA, "presenter": PRESENTER_NOTICE_FA},
            "notices_en": {"fan": FAN_NOTICE_EN, "explainer": EXPLAINER_NOTICE_EN, "presenter": PRESENTER_NOTICE_EN}}
