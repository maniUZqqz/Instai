"""The catalogue of the studio ladder: every stage of the way from idea to delivery, in the order a real animation studio works, with what each one needs,
who makes it (model, derived from other work, or a bridge to something InstAI already has) and the fields the review screen shows.

Phases: development (idea -> bible -> look -> characters), pre-production (beats -> script -> dialogue -> shot list -> storyboard -> animatic -> model sheets -> layout),
production (key art -> animation -> compositing) and post (sound design -> narration -> edit -> grade -> delivery). Terms follow docs/STUDIO_PIPELINE.md.

source:  stored = versions live in the ladder (StageVersion); bridge = the content lives elsewhere in InstAI (the ladder snapshots it, versions it and records the approval).
gen:     llm = a model writes it (task = role name); derive = computed from the other stages; None = made by the owner or by an existing production step.
"""
from __future__ import annotations

T, L, R = "text", "long", "rows"


def col(key: str, fa: str, en: str, kind: str = T, **kw) -> dict:
    return {"key": key, "label_fa": fa, "label_en": en, "type": kind, **kw}


def field(key: str, fa: str, en: str, kind: str = L, **kw) -> dict:
    return {"key": key, "label_fa": fa, "label_en": en, "type": kind, **kw}


SIZES = ["ECU", "CU", "MCU", "MS", "MWS", "WS", "EWS"]
CUES = ["ambience", "foley", "sfx", "music", "silence"]
PRESETS = ["neutral", "warm_dusk", "cold_night", "high_contrast", "faded", "vivid", "desaturated", "tension"]

STAGES: list[dict] = [
    # ---------------------------------------------------------------- development (one per series)
    {"key": "logline", "scope": "series", "phase": "development", "source": "stored", "gen": "llm", "task": "logline", "needs": [],
     "fa": "لاگ‌لاین", "en": "Logline", "term_fa": "یک جمله که کلِ داستان را می‌فروشد", "term_en": "One sentence that sells the whole story",
     "fields": [field("logline", "لاگ‌لاین", "Logline", L), field("hook", "وعدهٔ اصلی", "Hook", T), field("stakes", "چه چیزی در خطر است", "Stakes", T),
                field("alternatives", "نسخه‌های دیگر", "Alternatives", "list")]},
    {"key": "treatment", "scope": "series", "phase": "development", "source": "stored", "gen": "llm", "task": "treatment", "needs": ["logline"],
     "fa": "تریتمنت (خلاصهٔ داستان)", "en": "Treatment", "term_fa": "کل داستان به نثر، پیش از فیلم‌نامه", "term_en": "The whole story in prose, before any script",
     "fields": [field("synopsis", "خلاصه (چند بند)", "Synopsis (paragraphs)", "list"), field("acts", "پرده‌ها", "Acts", R, columns=[col("name", "نام", "Name"), col("summary", "خلاصه", "Summary", L)]),
                field("tone", "لحن", "Tone", T), field("themes", "مضمون‌ها", "Themes", "list")]},
    {"key": "art_style", "scope": "series", "phase": "development", "source": "stored", "gen": None, "task": "", "needs": ["treatment"], "live": "look",
     "fa": "سبک هنری (یک‌بار انتخاب)", "en": "Art style (chosen once)", "term_fa": "سبک از کتابخانه یک بار انتخاب و همه‌جا اعمال می‌شود", "term_en": "Picked once from the library and applied everywhere",
     "fields": [field("style_key", "سبک", "Style", "style"), field("realism", "درجهٔ واقع‌نمایی", "Realism", T), field("theme_key", "تم رنگی", "Colour theme", T), field("notes", "یادداشت", "Notes", L)]},
    {"key": "bible", "scope": "series", "phase": "development", "source": "bridge", "gen": None, "task": "", "needs": ["treatment"],
     "fa": "کتاب سریال", "en": "Series bible", "term_fa": "قوانین جهان، شخصیت‌ها، لحن و ساختار", "term_en": "World rules, characters, tone and structure", "fields": []},
    {"key": "character_models", "scope": "series", "phase": "development", "source": "bridge", "gen": None, "task": "", "needs": ["bible", "art_style"],
     "fa": "برگهٔ مدل شخصیت‌ها (قفل هویت)", "en": "Character model sheets (identity lock)", "term_fa": "برگهٔ مدل و رنگ‌ها یک بار تأیید می‌شود و در هر تصویر و ویدئو می‌آید", "term_en": "Model sheet and colours approved once, reused in every picture and clip",
     "fields": []},
    # ---------------------------------------------------------------- pre-production (one per episode)
    {"key": "beat_sheet", "scope": "episode", "phase": "preproduction", "source": "stored", "gen": "llm", "task": "beat_sheet", "needs": ["bible"],
     "fa": "بیت‌شیت", "en": "Beat sheet", "term_fa": "رویدادهای قسمت، پیش از نوشتن فیلم‌نامه", "term_en": "The episode's story events, before the script",
     "fields": [field("beats", "بیت‌ها", "Beats", R, columns=[col("name", "نام", "Name"), col("summary", "رویداد", "Event", L), col("seconds", "ثانیه", "Seconds", "number"), col("purpose", "حس مخاطب", "Purpose")])]},
    {"key": "script", "scope": "episode", "phase": "preproduction", "source": "bridge", "gen": None, "task": "", "needs": ["beat_sheet"],
     "fa": "فیلم‌نامه", "en": "Script", "term_fa": "متن قسمت", "term_en": "The episode text", "fields": []},
    {"key": "dialogue", "scope": "episode", "phase": "preproduction", "source": "stored", "gen": "llm", "task": "dialogue", "needs": ["script"],
     "fa": "دیالوگ", "en": "Dialogue", "term_fa": "گفتار هر شخصیت با احساس و زیرمتن", "term_en": "Each character's lines with emotion and subtext",
     "fields": [field("lines", "خط‌ها", "Lines", R, columns=[col("speaker", "گوینده", "Speaker"), col("text", "متن", "Text", L), col("emotion", "احساس", "Emotion"), col("subtext", "زیرمتن", "Subtext"),
                                                           col("pause_after", "مکث (ثانیه)", "Pause (s)", "number")])]},
    {"key": "shot_list", "scope": "episode", "phase": "preproduction", "source": "stored", "gen": "llm", "task": "shot_list", "needs": ["dialogue"],
     "fa": "فهرست نماها", "en": "Shot list", "term_fa": "اندازهٔ نما، زاویه، حرکت دوربین و اکشن هر نما", "term_en": "Size, angle, camera move and action of every shot",
     "fields": [field("shots", "نماها", "Shots", R, columns=[col("scene", "صحنه", "Scene", "number"), col("size", "اندازه", "Size", "choice", options=SIZES), col("angle", "زاویه", "Angle"), col("movement", "حرکت", "Move"),
                                                          col("action", "اکشن", "Action", L), col("seconds", "ثانیه", "Seconds", "number"), col("transition", "گذار", "Transition")])]},
    {"key": "storyboard", "scope": "episode", "phase": "preproduction", "source": "bridge", "gen": None, "task": "", "needs": ["shot_list"],
     "fa": "استوری‌بورد", "en": "Storyboard", "term_fa": "نمای‌به‌نمای قسمت", "term_en": "The episode shot by shot", "fields": []},
    {"key": "animatic", "scope": "episode", "phase": "preproduction", "source": "bridge", "gen": None, "task": "", "needs": ["storyboard"],
     "fa": "انیماتیک", "en": "Animatic", "term_fa": "استوری‌بورد زمان‌بندی‌شده با صدا", "term_en": "The board timed to sound", "fields": []},
    {"key": "design", "scope": "episode", "phase": "preproduction", "source": "bridge", "gen": None, "task": "", "needs": ["storyboard", "character_models"],
     "fa": "طراحی (پس‌زمینه، وسایل، اسکریپت رنگ)", "en": "Design (backgrounds, props, colour script)", "term_fa": "برگه‌های طراحی هر قسمت", "term_en": "This episode's design sheets", "fields": []},
    {"key": "layout", "scope": "episode", "phase": "preproduction", "source": "stored", "gen": "llm", "task": "layout", "needs": ["animatic", "design"],
     "fa": "لی‌اوت", "en": "Layout", "term_fa": "جای شخصیت‌ها، دوربین و نور در هر نما", "term_en": "Staging, camera and light of every shot",
     "fields": [field("layouts", "نماها", "Shots", R, columns=[col("shot", "نما", "Shot", "number"), col("background", "پس‌زمینه", "Background", L), col("staging", "صحنه‌آرایی", "Staging", L), col("camera", "دوربین", "Camera"),
                                                            col("lighting", "نور", "Lighting")])]},
    # ---------------------------------------------------------------- production
    {"key": "key_art", "scope": "episode", "phase": "production", "source": "bridge", "gen": None, "task": "", "needs": ["layout"],
     "fa": "تصویرهای کلیدی", "en": "Key art", "term_fa": "تصویر نهایی هر نما با شخصیت‌های قفل‌شده", "term_en": "The finished picture of every shot with the locked characters", "fields": []},
    {"key": "animation", "scope": "episode", "phase": "production", "source": "bridge", "gen": None, "task": "", "needs": ["key_art"],
     "fa": "انیمیشن", "en": "Animation", "term_fa": "حرکت: عروسک، پارالاکس یا ویدئوی مدل", "term_en": "Motion: puppet, parallax or model video", "fields": []},
    {"key": "compositing", "scope": "episode", "phase": "production", "source": "bridge", "gen": None, "task": "", "needs": ["animation"],
     "fa": "ترکیب‌بندی (کامپوزیت)", "en": "Compositing", "term_fa": "لایه‌ها و دوربین روی هم و ویدئوی مونتاژشده", "term_en": "Layers and camera put together into the assembled video", "fields": []},
    # ---------------------------------------------------------------- post
    {"key": "sound_design", "scope": "episode", "phase": "post", "source": "stored", "gen": "llm", "task": "sound_design", "needs": ["animatic"],
     "fa": "طراحی صدا", "en": "Sound design", "term_fa": "فضا، افکت، فولی و موسیقی", "term_en": "Ambience, effects, foley and music",
     "fields": [field("cues", "نشانه‌های صدا", "Cues", R, columns=[col("kind", "نوع", "Kind", "choice", options=CUES), col("shot", "نما", "Shot", "number"), col("start_sec", "از", "From", "number"),
                                                              col("end_sec", "تا", "To", "number"), col("description", "توضیح", "Description", L), col("prompt", "پرامپت انگلیسی", "English prompt", L),
                                                              col("gain_db", "dB", "dB", "number")]), field("mix_notes", "یادداشت میکس", "Mix notes", L), field("loudness_target", "هدف بلندی (LUFS)", "Loudness target (LUFS)", "number")]},
    {"key": "narration", "scope": "episode", "phase": "post", "source": "stored", "gen": "derive", "task": "", "needs": ["dialogue"],
     "fa": "گویندگی", "en": "Narration / voice", "term_fa": "برنامهٔ ضبط صدا: گوینده، سرعت، تلفظ", "term_en": "Recording plan: voice, pace, pronunciation",
     "fields": [field("lines", "خط‌ها", "Lines", R, columns=[col("shot", "نما", "Shot", "number"), col("speaker", "گوینده", "Speaker"), col("text", "متن", "Text", L), col("voice", "صدا", "Voice"),
                                                           col("pace", "سرعت", "Pace"), col("pause_after", "مکث", "Pause", "number"), col("pronunciation", "تلفظ", "Pronunciation")])]},
    {"key": "edit", "scope": "episode", "phase": "post", "source": "stored", "gen": "derive", "task": "", "needs": ["compositing", "sound_design", "narration"],
     "fa": "تدوین", "en": "Edit", "term_fa": "ریتم برش‌ها و گذارها", "term_en": "Cut rhythm and transitions",
     "fields": [field("cuts", "برش‌ها", "Cuts", R, columns=[col("shot", "نما", "Shot", "number"), col("seconds", "ثانیه", "Seconds", "number"), col("transition", "گذار", "Transition"), col("note", "نکته", "Note", L)]),
                field("notes", "یادداشت", "Notes", L)]},
    {"key": "grade", "scope": "episode", "phase": "post", "source": "stored", "gen": "llm", "task": "grade", "needs": ["edit"],
     "fa": "اصلاح رنگ", "en": "Colour grade", "term_fa": "حال‌وهوای رنگیِ هر صحنه", "term_en": "The colour mood of every scene",
     "fields": [field("scenes", "صحنه‌ها", "Scenes", R, columns=[col("scene", "صحنه", "Scene", "number"), col("preset", "پیش‌تنظیم", "Preset", "choice", options=PRESETS), col("mood", "حس", "Mood"),
                                                              col("notes", "نکته", "Note", L)]), field("global_notes", "قاعدهٔ کلی", "Global rule", L)]},
    {"key": "delivery", "scope": "episode", "phase": "post", "source": "stored", "gen": "derive", "task": "", "needs": ["grade"],
     "fa": "تحویل", "en": "Delivery", "term_fa": "نسخه‌ها، کاور، کپشن و فهرست بررسی نهایی", "term_en": "Renditions, cover, caption and the final checklist",
     "fields": [field("renditions", "نسخه‌ها", "Renditions", R, columns=[col("name", "نام", "Name"), col("aspect", "نسبت", "Aspect"), col("use", "کاربرد", "Use")]), field("caption", "کپشن", "Caption", L),
                field("hashtags", "هشتگ‌ها", "Hashtags", "list"), field("cover", "کاور", "Cover", T), field("checklist", "فهرست بررسی", "Checklist", R, columns=[col("item", "مورد", "Item", L), col("done", "انجام شد", "Done", "bool")])]},
]

BY_KEY = {s["key"]: s for s in STAGES}
PHASES = [{"key": "development", "fa": "توسعه", "en": "Development"}, {"key": "preproduction", "fa": "پیش‌تولید", "en": "Pre-production"},
          {"key": "production", "fa": "تولید", "en": "Production"}, {"key": "post", "fa": "پس‌تولید", "en": "Post-production"}]
# stages that must be approved before an episode may go to production (with `production.ladder_gate` on)
PREPRODUCTION_GATE = ["logline", "treatment", "art_style", "bible", "character_models", "beat_sheet", "script", "dialogue", "shot_list", "storyboard", "animatic", "design", "layout"]
# which stages wait for a human at each automation level (the others pass by themselves once they exist and everything before them is approved)
HUMAN = {
    "manual": None,
    "assisted": {"treatment", "art_style", "bible", "character_models", "script", "storyboard", "key_art", "edit", "delivery"},
    "automatic": {"bible", "character_models", "delivery"},
}


def needs_human(page, key: str) -> bool:
    level = page.automation_level if page.automation_level in HUMAN else "manual"
    req = HUMAN[level]
    return True if req is None else key in req


def public() -> dict:
    return {"phases": PHASES, "stages": [{k: v for k, v in s.items() if k != "task"} for s in STAGES], "gate": PREPRODUCTION_GATE}
