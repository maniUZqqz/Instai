"""The component library of the scene plan: every «scene» of a motion-graphics shot is one of these ready-made components; a model (or the
deterministic fallback in fallback.py) only picks the component and sets its numbers and texts.

SOURCE: ported from NMarketing:backend/apps/motion/components.py @ motion v2, adapted for InstAI: 19 of NMarketing's 33 components (the episode
card, kinetic title, quote, big number + counter, list / steps / checklist, before-after, the three explainer charts, the character name bar, the
word-by-word captions, the series sting, the key-art hero, the subscribe + «next episode» end card, the premiere countdown and the sticker); the
store-sales pieces (product, price card, app, comparison table, testimonial, rating, tags, ticker, feature cards, icon grid, progress pieces) were
left out. Labels exist in Persian AND English (InstAI shows both), fields carry InstAI vocabulary (series, episode number, hook line, source).

Every component: id (the key of remotion/src/components/registry.ts - tests/test_motion_plan.py keeps the two lists identical), labels, group, the
fields with their limits, a valid sample in both languages, which fields must be present (`need`), which fields are read by the viewer (`read`, for
the reading-time rule of qa.py), whether it can also be laid over another scene (`overlay`) and its duration rule (min, typical, max seconds).

Field kinds: str (max length) · num (min / max) · int · bool · enum · ref (an allowed picture) · strs (list of texts) · objs (list of objects).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICON_NAMES: tuple = ()
ICON_LABELS: dict = {}
try:  # the icon list is read from the same file the renderer reads (Lucide, ISC licence: remotion/src/components/ICONS-LICENSE.txt)
    _ic = json.loads((ROOT / "remotion" / "src" / "components" / "icons.generated.json").read_text(encoding="utf-8"))
    ICON_NAMES = tuple(_ic["icons"].keys())
    ICON_LABELS = dict(_ic.get("labels") or {})
except (OSError, ValueError, KeyError):  # pragma: no cover - the generated file is in the repository
    pass

PLATFORM_NAMES = ("youtube", "aparat", "instagram", "telegram", "tiktok", "eitaa", "rubika", "website", "phone")
STICKER_KINDS = ("burst", "circle", "tag")
STICKER_COLORS = ("accent", "accent2", "accent3")
ITEM_MAX = 120


def S(n: int, **kw) -> dict:
    return {"kind": "str", "max": n, **kw}


def N(lo: float, hi: float, **kw) -> dict:
    return {"kind": "num", "min": lo, "max": hi, **kw}


def I(lo: int, hi: int, **kw) -> dict:  # noqa: E743
    return {"kind": "int", "min": lo, "max": hi, **kw}


B = {"kind": "bool"}
REF = {"kind": "ref"}


def E(*choices, **kw) -> dict:
    return {"kind": "enum", "choices": tuple(choices), **kw}


def L(n: int, item: int = 100) -> dict:
    return {"kind": "strs", "max_items": n, "item_max": item}


def O(n: int, **fields) -> dict:  # noqa: E743
    return {"kind": "objs", "max_items": n, "fields": fields}


COMPONENTS: dict = {}
#: components whose numbers a viewer may take as FACT: they carry the honesty chip («example» unless a verified `source` is named)
DATA_IDS = ("stat", "counter", "bar_chart", "line_chart", "donut")
SOURCE_FIELDS = {"source": S(160), "example": B}


def _add(id, fa, en, group, fields, sample, sample_en, *, need=(), read=(), overlay=False, use="", about="", dur=(3, 5, 9), items=None, desc_fa="", desc_en=""):
    if id in DATA_IDS:
        fields = {**fields, **SOURCE_FIELDS}
    COMPONENTS[id] = {"id": id, "label": fa, "label_fa": fa, "label_en": en, "group": group, "fields": fields, "sample": sample, "sample_en": sample_en,
                      "need": tuple(need), "read": tuple(read), "overlay": overlay, "use": use, "about": about, "dur": dur, "items": items,
                      "desc_fa": desc_fa, "desc_en": desc_en}


# ───────────────────────────────────────────── the basic scenes
_add("title", "کارت قسمت", "Episode card", "scene",
     {"kicker": S(60), "series": S(80), "number": I(0, 999), "title": S(140), "hook": S(220)},
     {"type": "title", "duration": 4, "kicker": "فصل اول", "series": "سفر به ستاره‌ها", "number": 1, "title": "نخستین پرواز", "hook": "اما کسی نمی‌داند در آسمان چه منتظر است"},
     {"type": "title", "duration": 4, "kicker": "Season one", "series": "Journey to the Stars", "number": 1, "title": "The first flight", "hook": "but nobody knows what waits in the sky"},
     need=("title",), read=("kicker", "series", "title", "hook"), use="عنوان قسمت شروع معرفی سریال title episode card opening intro series hook cliffhanger",
     about="episode card: series name + number badge, big title, hook line", dur=(3, 4, 6),
     desc_fa="کارت شروع قسمت: نام سریال، شمارهٔ قسمت، عنوان و یک جملهٔ کنجکاوی‌برانگیز.",
     desc_en="The opening card of an episode: series name, episode number, title and a curiosity hook line.")
_add("list", "نکته‌های کلیدی (فهرست)", "Key points (list)", "scene", {"title": S(100), "items": L(6, 120), "numbered": B},
     {"type": "list", "duration": 7, "title": "سه نکتهٔ مهم", "items": ["نکتهٔ اول", "نکتهٔ دوم", "نکتهٔ سوم"], "numbered": True},
     {"type": "list", "duration": 7, "title": "Three key points", "items": ["First point", "Second point", "Third point"], "numbered": True},
     need=("items",), read=("title", "items"), use="فهرست مراحل نکته مزیت خلاصه list steps takeaways key points summary", about="titled list of short lines (numbered or bullets)",
     dur=(4, 7, 11), desc_fa="نکته‌های کلیدی یک قسمت توضیحی به‌صورت فهرست شمارهٔ‌دار.", desc_en="The key takeaways of an explainer as a numbered list.")
_add("quote", "نقل‌قول", "Quote", "scene", {"text": S(320), "author": S(80)},
     {"type": "quote", "duration": 5, "text": "جمله‌ای که می‌ارزد به یاد بماند.", "author": "نام گوینده"},
     {"type": "quote", "duration": 5, "text": "A sentence worth remembering.", "author": "Speaker name"},
     need=("text",), read=("text", "author"), use="نقل قول جمله شعار quote saying line", about="one quotation with author", dur=(3, 5, 8),
     desc_fa="یک جملهٔ ماندگار با نام گوینده.", desc_en="One memorable line with its speaker.")
_add("stat", "عدد بزرگ", "Big number", "scene", {"kicker": S(60), "value": S(24), "decimals": I(0, 3), "prefix": S(12), "suffix": S(12), "label": S(160), "count_up": B},
     {"type": "stat", "duration": 4, "kicker": "عدد", "value": "12", "suffix": "ساعت", "label": "توضیحِ عدد"},
     {"type": "stat", "duration": 4, "kicker": "Number", "value": "12", "suffix": "h", "label": "What the number means"},
     need=("value",), read=("kicker", "label"), use="عدد آمار تعداد درصد stat number count metric figure", about="one big counting number with label (value is a number string)",
     dur=(3, 4, 6), desc_fa="یک عدد درشت که از صفر شمرده می‌شود؛ بدون منبعِ تأییدشده با برچسب «نمونهٔ نمایشی» می‌آید.",
     desc_en="One big number that counts up; without a verified source it carries the «example» label.")
_add("logo", "نشان سریال (استینگ)", "Series sting", "scene", {"title": S(80), "tagline": S(160), "logo": REF},
     {"type": "logo", "duration": 3, "title": "سفر به ستاره‌ها", "tagline": "هر هفته یک ماجرا"},
     {"type": "logo", "duration": 3, "title": "Journey to the Stars", "tagline": "A new adventure every week"},
     read=("title", "tagline"), use="لوگو شعار سریال پایان logo sting series tagline", about="series logo / name reveal with tagline", dur=(2, 3, 5),
     desc_fa="نام یا نشان سریال با حلقه‌های نوری و یک شعار.", desc_en="The series name or logo with pulsing rings and a tagline.")

# ───────────────────────────────────────────── data components (explainer numbers: «example» unless a verified source is named)
_add("bar_chart", "نمودار میله‌ای", "Bar chart", "data",
     {"title": S(100), "bars": O(6, label=S(40), value=N(0, 1e9)), "unit": S(16), "show_values": B, "horizontal": B, "note": S(160)},
     {"type": "bar_chart", "duration": 6, "title": "مقایسهٔ سه گزینه", "bars": [{"label": "الف", "value": 40}, {"label": "ب", "value": 65}, {"label": "ج", "value": 90}], "unit": "٪"},
     {"type": "bar_chart", "duration": 6, "title": "Three options compared", "bars": [{"label": "A", "value": 40}, {"label": "B", "value": 65}, {"label": "C", "value": 90}], "unit": "%"},
     need=("bars",), read=("title", "note"), items="bars", use="نمودار میله مقایسه رشد آمار bar chart compare growth data", about="bars grow from zero; bars=[{label,value}] up to 6",
     dur=(4, 6, 9), desc_fa="میله‌هایی که از صفر بالا می‌آیند؛ برای مقایسهٔ چند چیز.", desc_en="Bars that grow from zero, to compare a few things.")
_add("line_chart", "نمودار خطی", "Line chart", "data",
     {"title": S(100), "points": O(8, label=S(24), value=N(-1e9, 1e9)), "unit": S(16), "note": S(160)},
     {"type": "line_chart", "duration": 6, "title": "روند در طول زمان", "points": [{"label": "اول", "value": 10}, {"label": "دوم", "value": 25}, {"label": "سوم", "value": 22}, {"label": "چهارم", "value": 48}]},
     {"type": "line_chart", "duration": 6, "title": "A trend over time", "points": [{"label": "1", "value": 10}, {"label": "2", "value": 25}, {"label": "3", "value": 22}, {"label": "4", "value": 48}]},
     need=("points",), read=("title", "note"), items="points", use="نمودار خطی روند زمان line chart trend over time", about="line draws itself; points=[{label,value}] up to 8",
     dur=(4, 6, 9), desc_fa="خطی که خودش کشیده می‌شود؛ برای نشان‌دادن روند.", desc_en="A line that draws itself, to show a trend.")
_add("donut", "نمودار دونات", "Donut chart", "data",
     {"title": S(100), "slices": O(5, label=S(40), value=N(0, 1e9)), "center_label": S(30)},
     {"type": "donut", "duration": 6, "title": "سهم هر بخش", "slices": [{"label": "الف", "value": 50}, {"label": "ب", "value": 30}, {"label": "ج", "value": 20}], "center_label": "کل"},
     {"type": "donut", "duration": 6, "title": "Share of each part", "slices": [{"label": "A", "value": 50}, {"label": "B", "value": 30}, {"label": "C", "value": 20}], "center_label": "Total"},
     need=("slices",), read=("title", "center_label"), items="slices", use="دونات دایره سهم درصد donut pie share parts", about="donut / pie; slices=[{label,value}] up to 5",
     dur=(4, 6, 9), desc_fa="سهم هر بخش از کل.", desc_en="The share of each part in a whole.")
_add("counter", "شمارنده با واحد", "Counters with units", "data",
     {"kicker": S(60), "items": O(3, value=S(24), unit=S(16), label=S(60), decimals=I(0, 3)), "note": S(160)},
     {"type": "counter", "duration": 5, "kicker": "در یک نگاه", "items": [{"value": "8", "unit": "قسمت", "label": "در هر فصل"}, {"value": "20", "unit": "دقیقه", "label": "هر قسمت"}]},
     {"type": "counter", "duration": 5, "kicker": "At a glance", "items": [{"value": "8", "unit": "episodes", "label": "per season"}, {"value": "20", "unit": "min", "label": "each"}]},
     need=("items",), read=("kicker", "note"), items="items", use="شمارنده عدد واحد آمار counter numbers units", about="1-3 counting numbers with unit and label", dur=(3, 5, 8),
     desc_fa="یک تا سه عدد که با واحدشان شمرده می‌شوند.", desc_en="One to three numbers that count up with their units.")
_add("before_after", "قبل و بعد (تقسیم‌شونده)", "Before / after (what if)", "data",
     {"title": S(100), "before": S(140), "after": S(140), "before_label": S(24), "after_label": S(24), "before_image": REF, "after_image": REF},
     {"type": "before_after", "duration": 6, "title": "اگر چنین می‌شد؟", "before": "دنیای امروز", "after": "دنیای دیگر", "before_label": "واقعیت", "after_label": "اگر…"},
     {"type": "before_after", "duration": 6, "title": "What if?", "before": "The world today", "after": "Another world", "before_label": "Reality", "after_label": "What if"},
     need=("before", "after"), read=("title", "before", "after", "before_label", "after_label"), use="قبل بعد اگر چه می‌شد تفاوت before after what if split reveal",
     about="wipe-split before/after with optional images", dur=(4, 6, 8), desc_fa="دو نیمه که با یک جاروی نوری عوض می‌شوند؛ برای قسمت‌های «اگر چنین می‌شد؟».",
     desc_en="Two halves swapped by a light wipe; for «what if» episodes.")
_add("countdown", "شمارش معکوس (پریمیر)", "Countdown (premiere)", "data", {"label": S(100), "from": I(1, 10), "finish_text": S(40)},
     {"type": "countdown", "duration": 5, "label": "پخش قسمت بعد تا", "from": 3, "finish_text": "شروع!"},
     {"type": "countdown", "duration": 5, "label": "Next episode in", "from": 3, "finish_text": "Go!"},
     read=("label", "finish_text"), use="شمارش معکوس پریمیر شروع countdown premiere launch timer", about="countdown from N with a finish word", dur=(3, 5, 8),
     desc_fa="شمارش معکوس تا پخش قسمت.", desc_en="A countdown to the premiere of an episode.")

# ───────────────────────────────────────────── text and display components
_add("kinetic_title", "تیتر کلمه‌به‌کلمه", "Kinetic title", "text", {"kicker": S(60), "text": S(140), "title": S(140)},
     {"type": "kinetic_title", "duration": 4, "kicker": "ویژه", "text": "هر ستاره یک داستان دارد"},
     {"type": "kinetic_title", "duration": 4, "kicker": "Special", "text": "Every star has a story"},
     need=("text", "title"), read=("kicker", "text", "title"), use="تیتر کلمه حرکتی کینتیک شعار kinetic title words typography headline",
     about="headline whose WORDS pop one by one (never letters); syncs to narration", dur=(3, 4, 6),
     desc_fa="تیتری که کلمه‌ها یکی‌یکی همزمان با گفتار می‌آیند.", desc_en="A headline whose words pop in one by one, in step with the narration.")
_add("lower_third", "نوار نام شخصیت", "Character name bar", "text", {"name": S(60), "role": S(60)},
     {"type": "lower_third", "duration": 4, "name": "سارا", "role": "خلبان"},
     {"type": "lower_third", "duration": 4, "name": "Sara", "role": "Pilot"},
     need=("name",), read=("name", "role"), overlay=True, use="نام سمت شخصیت گوینده lower third name character speaker role", about="name + role bar; best as an overlay on another scene",
     dur=(3, 4, 6), desc_fa="نوار نام و نقش یک شخصیت که از کنار می‌لغزد؛ روی صحنهٔ دیگر هم می‌نشیند.",
     desc_en="A name and role bar for a character that slides in; it can also sit over another scene.")
_add("checklist", "چک‌لیست تیک‌دار", "Checklist", "text", {"title": S(100), "items": L(6, 100)},
     {"type": "checklist", "duration": 6, "title": "چه چیزهایی را یاد گرفتیم؟", "items": ["مورد اول", "مورد دوم", "مورد سوم"]},
     {"type": "checklist", "duration": 6, "title": "What did we learn?", "items": ["First thing", "Second thing", "Third thing"]},
     need=("items",), read=("title", "items"), items="items", use="چک لیست تیک موارد خلاصه checklist ticks recap", about="items get a drawn tick one after another", dur=(4, 6, 9),
     desc_fa="موردها یکی‌یکی تیک می‌خورند؛ برای جمع‌بندی.", desc_en="Items get a drawn tick one after another; good for a recap.")
_add("steps", "مراحل / خط زمان", "Steps / timeline", "text", {"title": S(100), "steps": O(5, title=S(60), text=S(120)), "layout": E("horizontal", "vertical")},
     {"type": "steps", "duration": 7, "title": "چهار گام", "steps": [{"title": "پرسش"}, {"title": "بررسی"}, {"title": "آزمایش"}, {"title": "نتیجه"}]},
     {"type": "steps", "duration": 7, "title": "Four steps", "steps": [{"title": "Ask"}, {"title": "Look"}, {"title": "Test"}, {"title": "Conclude"}]},
     need=("steps",), read=("title", "steps"), items="steps", use="مراحل گام روند خط زمان timeline steps process how it works", about="numbered steps connected by a line; steps=[{title,text?}] up to 5",
     dur=(5, 7, 10), desc_fa="مرحله‌های شماره‌دار که با یک خط به هم وصل‌اند.", desc_en="Numbered steps joined by a line.")
_add("captions", "زیرنویس کلمه‌به‌کلمه", "Word-by-word captions", "text", {"title": S(60), "text": S(300), "size": N(30, 120)},
     {"type": "captions", "duration": 5, "text": "این جمله کلمه به کلمه زیرنویس می‌شود"},
     {"type": "captions", "duration": 5, "text": "This line is captioned word by word"},
     need=("text",), read=("text",), overlay=True, use="زیرنویس کپشن گفتار captions subtitles speech karaoke", about="caption track with the spoken word highlighted (uses narration cues)",
     dur=(3, 5, 10), desc_fa="زیرنویسی که کلمهٔ در حال گفتن را پررنگ می‌کند (به زمان‌بندی گفتار نیاز دارد).",
     desc_en="A caption track that highlights the word being spoken (uses the narration timing).")
_add("sticker", "استیکر پاپ", "Pop sticker", "text", {"kind": E(*STICKER_KINDS), "icon": E(*ICON_NAMES), "color": E(*STICKER_COLORS), "text": S(20)},
     {"type": "sticker", "duration": 3, "kind": "burst", "text": "تازه"},
     {"type": "sticker", "duration": 3, "kind": "burst", "text": "New"},
     read=("text",), overlay=True, use="استیکر برچسب جدید نشان sticker badge new burst", about="pop-in sticker (burst/circle/tag) with a short text or an icon; overlay",
     dur=(2, 3, 5), desc_fa="برچسبی که با پاپ می‌آید (ستاره، دایره یا برچسب).", desc_en="A sticker that pops in (burst, circle or tag).")
_add("social_cta", "دعوت به دنبال‌کردن + قسمت بعد", "Subscribe + next episode", "text",
     {"title": S(140), "platform": E(*PLATFORM_NAMES), "handle": S(40), "note": S(80), "button": S(40), "next_episode": S(120)},
     {"type": "social_cta", "duration": 4, "title": "قسمت بعد را از دست ندهید", "platform": "youtube", "handle": "@example", "button": "دنبال کردن", "next_episode": "فرود در سیارهٔ سرخ"},
     {"type": "social_cta", "duration": 4, "title": "Don't miss the next one", "platform": "youtube", "handle": "@example", "button": "Subscribe", "next_episode": "Landing on the red planet"},
     need=("handle", "title"), read=("title", "note", "button", "next_episode"), overlay=True, use="دنبال کردن اشتراک قسمت بعد یوتیوب subscribe follow next episode end card",
     about="handle + button + «next episode» line; only handles the user gave", dur=(3, 4, 6),
     desc_fa="کارت پایانی: نشانی کانال، دکمهٔ دنبال‌کردن و نام قسمت بعد.", desc_en="The end card: channel handle, a follow button and the next episode.")
_add("image_hero", "تصویر تمام‌صفحه با عنوان", "Key art with title", "text", {"kicker": S(60), "caption": S(140), "image": REF},
     {"type": "image_hero", "duration": 4, "kicker": "ویژه", "caption": "عنوان روی تصویر"},
     {"type": "image_hero", "duration": 4, "kicker": "Special", "caption": "Title over the picture"},
     need=("caption",), read=("kicker", "caption"), use="عکس تمام صفحه تصویر کلیدی hero image key art full picture", about="full-bleed picture (the shot's keyframe) with caption",
     dur=(3, 4, 6), desc_fa="تصویر کلیدی نما به‌صورت تمام‌صفحه با یک عنوان.", desc_en="The shot's key picture full-bleed with a caption.")

SCENE_IDS = tuple(COMPONENTS)
OVERLAY_IDS = tuple(k for k, c in COMPONENTS.items() if c["overlay"])
GROUP_LABELS = {"scene": ("صحنه‌های پایه", "Basic scenes"), "data": ("عدد و نمودار", "Numbers and charts"), "text": ("متن و نمایش", "Text and display")}


def get(cid: str):
    return COMPONENTS.get(cid)


def label(cid: str, lang: str = "fa") -> str:
    c = COMPONENTS.get(cid)
    return (c["label_en"] if lang == "en" else c["label_fa"]) if c else cid


def sample(cid: str, lang: str = "fa") -> dict:
    c = COMPONENTS[cid]
    return dict(c["sample_en"] if lang == "en" else c["sample"])


def field_doc(spec: dict) -> str:
    """One field in compact form for the prompt: str<=60 · num 0..100 · enum a|b · [{label:str<=40,value:num}]x6"""
    k = spec["kind"]
    if k == "str":
        return f"str<={spec['max']}"
    if k in ("num", "int"):
        lo, hi = spec["min"], spec["max"]
        return f"{k} {lo:g}..{hi:g}" if hi < 1e8 else f"{k}"
    if k == "bool":
        return "bool"
    if k == "enum":
        ch = spec["choices"]
        return "|".join(ch) if len(ch) <= 8 else f"icon name ({len(ch)} choices)"
    if k == "ref":
        return "image ref (omit unless given)"
    if k == "strs":
        return f"[str<={spec['item_max']}]x{spec['max_items']}"
    if k == "objs":
        inner = ",".join(f"{n}:{field_doc(f)}" for n, f in spec["fields"].items())
        return f"[{{{inner}}}]x{spec['max_items']}"
    return k


def _public_fields(fields: dict) -> dict:
    out = {}
    for n, f in fields.items():
        d = {k: (list(v) if isinstance(v, tuple) else v) for k, v in f.items() if k != "fields"}
        if f["kind"] == "objs":
            d["fields"] = _public_fields(f["fields"])
        out[n] = d
    return out


def public_list() -> list:
    """For the API and the page: every component with its fields, labels (fa + en), samples (fa + en) and duration rule."""
    out = []
    for c in COMPONENTS.values():
        gfa, gen = GROUP_LABELS[c["group"]]
        out.append({"id": c["id"], "label_fa": c["label_fa"], "label_en": c["label_en"], "group": c["group"], "group_fa": gfa, "group_en": gen, "overlay": c["overlay"],
                    "fields": _public_fields(c["fields"]), "sample_fa": c["sample"], "sample_en": c["sample_en"], "need": list(c["need"]),
                    "duration": {"min": c["dur"][0], "typical": c["dur"][1], "max": c["dur"][2]}, "about": c["about"], "desc_fa": c["desc_fa"], "desc_en": c["desc_en"],
                    "data": c["id"] in DATA_IDS})
    return out
