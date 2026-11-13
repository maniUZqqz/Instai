"""Conventions of the short stick-figure mini-series genre (survival / escape / choices): FORMAT, LENGTH, PACING and HOOKS only.

Written from the general shape of the genre on Instagram Reels, YouTube Shorts and TikTok, as seen by the owner's list of channels (zombie stickman, ended survived, persianstickverse,
thebinaqsh, plunk_guy, akumadub, stickchoicex). Nothing here is copied from any of them: no character, story, title, catchphrase or joke. This module holds the structural
rules - how long an episode is, how fast it cuts, where the hook and the cliffhanger sit - so InstAI can plan ORIGINAL episodes in the same family of formats.
Honest limit: these are conventions drawn from the format in general; they were not measured against any one channel's analytics (no platform data is available here)."""
from __future__ import annotations

GENRES: dict[str, dict] = {
    "stick_survival": {
        "title_fa": "بقا (آدمک چوبی)", "title_en": "Survival (stick figure)",
        "summary_fa": "قهرمانی با ابزار کم در برابر یک تهدید پیوسته: هر قسمت یک مانع، یک چرخش و یک پایان باز.",
        "summary_en": "A hero with few tools against a running threat: one obstacle, one twist and an open ending per episode.",
        "runtime": {"min": 20, "default": 30, "max": 60}, "hook_sec": 2, "recap_sec": 2, "cliffhanger_sec": 3,
        "beats": [("hook", 0.00, 0.07), ("setup", 0.07, 0.20), ("escalation", 0.20, 0.55), ("twist", 0.55, 0.70), ("crisis", 0.70, 0.93), ("cliffhanger", 0.93, 1.00)],
        "pacing": {"avg_shot_sec": 2.2, "min_shot_sec": 0.8, "max_shot_sec": 4.5, "cuts_per_10s": 4},
    },
    "stick_escape": {
        "title_fa": "فرار (آدمک چوبی)", "title_en": "Escape (stick figure)",
        "summary_fa": "قهرمان در یک مکان بسته گیر افتاده و باید با نقشه و ابزار فرار کند؛ هر قسمت یک اتاق، یک نگهبان یا یک قفل.",
        "summary_en": "The hero is trapped in a closed place and must plan and use items to get out; one room, guard or lock per episode.",
        "runtime": {"min": 20, "default": 35, "max": 60}, "hook_sec": 2, "recap_sec": 2, "cliffhanger_sec": 3,
        "beats": [("hook", 0.00, 0.06), ("setup", 0.06, 0.18), ("escalation", 0.18, 0.50), ("twist", 0.50, 0.68), ("crisis", 0.68, 0.92), ("cliffhanger", 0.92, 1.00)],
        "pacing": {"avg_shot_sec": 2.6, "min_shot_sec": 1.0, "max_shot_sec": 5.0, "cuts_per_10s": 3.5},
    },
    "stick_comedy": {
        "title_fa": "کمدی (آدمک چوبی)", "title_en": "Comedy (stick figure)",
        "summary_fa": "موقعیت‌های بامزه‌ٔ تکرارشونده با شخصیت‌های ثابت؛ پایان هر قسمت یک شوخی یا یک «ادامه دارد».",
        "summary_en": "Recurring funny situations with fixed characters; each episode ends on a gag or a 'to be continued'.",
        "runtime": {"min": 15, "default": 25, "max": 45}, "hook_sec": 2, "recap_sec": 0, "cliffhanger_sec": 3,
        "beats": [("hook", 0.00, 0.08), ("setup", 0.08, 0.25), ("escalation", 0.25, 0.65), ("twist", 0.65, 0.85), ("cliffhanger", 0.85, 1.00)],
        "pacing": {"avg_shot_sec": 2.0, "min_shot_sec": 0.7, "max_shot_sec": 4.0, "cuts_per_10s": 5},
    },
}
DEFAULT_GENRE = "stick_survival"

CONVENTIONS: list[dict] = [
    {"key": "hook", "fa": "قلاب در ۲ ثانیهٔ اول: صحنه را وسط خطر یا یک سؤال شروع کن، نه با معرفی.", "en": "A hook inside the first 2 seconds: open in the middle of the danger or a question, never on an introduction."},
    {"key": "one_location", "fa": "هر قسمت یک مکان و یک هدف روشن؛ بیننده باید در ۵ ثانیه بفهمد قهرمان چه می‌خواهد.", "en": "One location and one clear goal per episode; the viewer must know what the hero wants within 5 seconds."},
    {"key": "show_dont_tell", "fa": "بیشتر تصویر و حرکت و افکت صوتی؛ دیالوگ کم و کوتاه؛ متن روی صفحه برای جملهٔ کلیدی.", "en": "Mostly picture, motion and sound effects; little, short dialogue; on-screen text for the key line."},
    {"key": "fast_cuts", "fa": "برش سریع (متوسط ۲ تا ۳ ثانیه)، هر برش یک اطلاعات تازه یا یک حرکت تازه.", "en": "Fast cutting (about 2-3 seconds per shot); every cut adds a new fact or a new move."},
    {"key": "readable_silhouettes", "fa": "هر شخصیت با یک رنگ و یک نشانهٔ ثابت (شال، کلاه) شناخته می‌شود؛ بدون شخصیتِ هم‌شکل.", "en": "Each character is recognised by one colour and one fixed marker (scarf, cap); no look-alike characters."},
    {"key": "escalation", "fa": "تشدید پله‌پله: هر مانع بزرگ‌تر از قبلی؛ یک چرخشِ غیرمنتظره در نزدیک دو سوم زمان.", "en": "Escalate step by step: each obstacle bigger than the last; one unexpected twist about two thirds in."},
    {"key": "cliffhanger", "fa": "پایان باز در ۳ ثانیهٔ آخر: قطع روی لحظهٔ اوج یا یک سؤال؛ قسمت بعد با پاسخ شروع می‌شود.", "en": "An open ending in the last 3 seconds: cut on the peak moment or a question; the next episode opens with the answer."},
    {"key": "recap", "fa": "شروع قسمت بعد با یادآوری ۲ ثانیه‌ای تنها اگر لازم است؛ هرگز بیش از آن.", "en": "Open the next episode with a 2-second reminder only if needed; never longer."},
    {"key": "numbering", "fa": "شماره و عنوان ثابت روی کارت آغاز («قسمت ۵»)، تا بیننده ترتیب را بداند و دنبال کند.", "en": "A fixed numbered title card ('Episode 5') so viewers know the order and follow it."},
    {"key": "comment_bait", "fa": "گاهی پایان را به سؤالی ختم کن که نظرها پاسخ بدهند (انتخاب A یا B)؛ بدون وعدهٔ دروغ.", "en": "Sometimes end on a question the comments can answer (choose A or B); no false promises."},
    {"key": "sound", "fa": "افکت‌های برجسته (ضربه، شتاب، هشدار) و موسیقیِ حداقلی؛ سکوت کوتاه پیش از افشا.", "en": "Prominent effects (hits, whooshes, alarms) and minimal music; a short silence before the reveal."},
    {"key": "regular_schedule", "fa": "برنامهٔ انتشار ثابت (مثلاً سه بار در هفته) تا مخاطب بداند چه وقت منتظر باشد.", "en": "A fixed posting schedule (for example three times a week) so the audience knows when to expect it."},
]

HOOK_TYPES = [
    {"key": "in_medias_res", "fa": "وسط خطر", "en": "In the middle of danger"}, {"key": "question", "fa": "سؤال", "en": "A question"},
    {"key": "countdown", "fa": "شمارش معکوس", "en": "A countdown"}, {"key": "reveal", "fa": "افشای ناگهانی", "en": "A sudden reveal"},
    {"key": "mistake", "fa": "اشتباه قهرمان", "en": "The hero's mistake"}, {"key": "contrast", "fa": "تضاد", "en": "A contrast"},
]
CLIFFHANGER_TYPES = [
    {"key": "danger_arrives", "fa": "خطر می‌رسد", "en": "Danger arrives"}, {"key": "betrayal", "fa": "خیانت", "en": "A betrayal"},
    {"key": "unknown_door", "fa": "در ناشناخته", "en": "An unknown door"}, {"key": "choice", "fa": "انتخاب دشوار", "en": "A hard choice"},
    {"key": "vanish", "fa": "ناپدید شدن", "en": "A disappearance"}, {"key": "twist_reveal", "fa": "چرخش بزرگ", "en": "A big twist"},
]
CAST_ROLES = ["protagonist", "rival", "ally", "comic", "villain", "mentor"]


def genre(key: str) -> dict:
    return GENRES.get(key) or GENRES[DEFAULT_GENRE]


def beat_plan(genre_key: str, runtime_sec: int) -> list[dict]:
    """The beat template of the genre scaled to `runtime_sec`: [{name, start_sec, end_sec, seconds}]."""
    g = genre(genre_key)
    out = []
    for name, a, b in g["beats"]:
        s, e = round(runtime_sec * a, 1), round(runtime_sec * b, 1)
        out.append({"name": name, "start_sec": s, "end_sec": e, "seconds": round(e - s, 1)})
    return out


def public() -> dict:
    return {"genres": [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "beats"}, "beats": [{"name": n, "from": a, "to": b} for n, a, b in v["beats"]]} for k, v in GENRES.items()],
            "conventions": CONVENTIONS, "hook_types": HOOK_TYPES, "cliffhanger_types": CLIFFHANGER_TYPES, "cast_roles": CAST_ROLES, "default_genre": DEFAULT_GENRE}
