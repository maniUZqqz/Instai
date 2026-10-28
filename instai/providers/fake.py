"""Deterministic fake text provider: tests, demos and the GPU-less dev PC. Output is schema-valid and clearly a demo.

It reads the structured `task` / `meta` the agents pass (real providers ignore them), so no prompt parsing is needed.
`fail_first` makes the first N calls return broken text, which exercises the validate/repair/retry loop.
"""
from __future__ import annotations

import hashlib
import json
import time

from .base import LLMResult, TextProvider

DEMO_TAG_FA = "[نمونه‌ی آزمایشی]"
DEMO_TAG_EN = "[demo]"


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def _pick(seq, *keys):
    return seq[_h(*keys) % len(seq)]


class FakeProvider(TextProvider):
    name = "fake"
    resource = "cpu"

    def __init__(self, fail_first: int = 0, garbage: str = "این یک پاسخ نامعتبر است {", latency: float = 0.0):
        self.fail_first = fail_first
        self.garbage = garbage
        self.latency = latency
        self.calls: list[dict] = []

    @property
    def model(self) -> str:
        return "fake-1"

    def health(self) -> dict:
        return {"ok": True, "detail": "fake provider (demo content)", "models": ["fake-1"]}

    def generate(self, messages, *, schema=None, temperature=0.4, max_tokens=4096, task=None, meta=None,
                 model=None, timeout=600) -> LLMResult:
        self.calls.append({"task": task, "meta": meta, "messages": messages})
        if self.latency:
            time.sleep(self.latency)
        if self.fail_first > 0:
            self.fail_first -= 1
            return LLMResult(text=self.garbage, provider="fake", model="fake-1", seconds=0.0)
        fn = _TASKS.get(task or "")
        if fn is None:
            text = json.dumps({"text": "fake"}, ensure_ascii=False)
        else:
            text = json.dumps(fn(meta or {}), ensure_ascii=False)
        return LLMResult(text=text, provider="fake", model="fake-1", seconds=0.0, prompt_tokens=100,
                         completion_tokens=len(text) // 4)


# ------------------------------------------------------------------ helpers

def _fa(meta: dict) -> bool:
    return (meta.get("language") or "fa").startswith("fa")


def _fmt(meta: dict) -> str:
    return meta.get("format") or "anime_whatif"


def _hero(meta: dict) -> str:
    chars = meta.get("characters") or []
    return chars[0] if chars else ("قهرمان" if _fa(meta) else "the hero")


def _topic(meta: dict) -> str:
    return meta.get("topic") or meta.get("idea") or meta.get("page_name") or ("موضوع" if _fa(meta) else "the topic")


# ------------------------------------------------------------------ strategy

def strategy(meta: dict) -> dict:
    fa, fmt, name = _fa(meta), _fmt(meta), meta.get("page_name") or "InstAI"
    idea = meta.get("idea") or ""
    tag = DEMO_TAG_FA if fa else DEMO_TAG_EN
    if fa:
        base = {
            "anime_whatif": ("روایت جایگزین دنیای انیمه: «اگر یک تصمیم عوض می‌شد؟»", ["شاخه‌ی داستانی", "جدول زمانی جایگزین", "کلیف‌هنگر"]),
            "recurring_character": ("یک شخصیت کارتونیِ دوست‌داشتنی در موقعیت‌های روزمره", ["کمدی روزمره", "شوخی تکرارشونده", "داستان کوتاه"]),
            "concept_explainer": ("توضیح ساده‌ی مفاهیم سخت، بی‌طرف و مستند", ["مفهوم", "قیاس", "منبع و راستی‌آزمایی"]),
        }.get(fmt, ("صفحه‌ی محتوایی با تولید خودکار", ["معرفی", "آموزش", "سرگرمی"]))
        out = {
            "positioning": f"{tag} {name}: {base[0]}. ایده‌ی کاربر: {idea or 'ثبت نشده'}",
            "audience_insight": "مخاطب فارسی‌زبان ۱۸ تا ۳۵ ساله که ویدئوی کوتاه عمودی را سریع و بی‌صدا هم دنبال می‌کند؛ زیرنویس مهم است.",
            "tone_guidelines": "ساده، گرم و شفاف؛ جمله‌های کوتاه؛ بدون اغراق و بدون ادعای بی‌منبع.",
            "content_pillars": [{"title": t, "description": f"ستون محتوایی «{t}» برای {name}"} for t in base[1]],
            "series_ideas": [
                {"title": f"{name} - فصل اول", "premise": f"فصل اول بر پایه‌ی ایده‌ی «{idea or name}»", "branch_point": "نقطه‌ی انشعاب اولیه", "episodes": 5},
                {"title": f"{name} - ویژه", "premise": "یک مجموعه‌ی کوتاه‌تر برای محک‌زدن مخاطب", "episodes": 3},
            ],
            "posting_plan": {"per_week": 3, "best_times": ["۱۹:۰۰", "۲۱:۰۰"], "episode_length_sec": 45},
            "hashtags": ["#انیمه", "#داستان", "#ویدئوکوتاه"] if fmt == "anime_whatif" else ["#آموزش", "#ساده", "#ویدئوکوتاه"],
            "risks": ["حق نشر: از شخصیت‌ها و نام‌های اصلیِ فرانچایز استفاده نشود مگر با علامت‌گذاری «محتوای طرفدارانه»."]
            if fmt == "anime_whatif" else ["ادعاها باید منبع داشته باشند و مناقشه‌ها برچسب بخورند."],
        }
        if fmt in ("anime_whatif", "recurring_character"):
            out["characters"] = [
                {"name": "آرتا", "role": "قهرمان", "personality": "شجاع و کنجکاو", "appearance": "موی کوتاه مشکی، شنل آبی", "is_original": True},
                {"name": "نیلا", "role": "همراه", "personality": "باهوش و کم‌حرف", "appearance": "موی بلند نقره‌ای", "is_original": True},
            ]
        return out
    out = {
        "positioning": f"{tag} {name}: a content page built around '{idea or name}'.",
        "audience_insight": "Short vertical-video viewers aged 18-35 who often watch muted, so subtitles matter.",
        "tone_guidelines": "Plain, warm and clear. Short sentences. No hype and no unsourced claims.",
        "content_pillars": [{"title": t, "description": f"Pillar '{t}' for {name}"} for t in ("Core idea", "Story", "Sources")],
        "series_ideas": [{"title": f"{name} - Season 1", "premise": f"Season one based on '{idea or name}'", "branch_point": "Initial branch", "episodes": 5}],
        "posting_plan": {"per_week": 3, "best_times": ["19:00", "21:00"], "episode_length_sec": 45},
        "hashtags": ["#anime", "#story", "#shorts"],
        "risks": ["Copyright: avoid franchise names and characters unless the series is marked as fan content."],
    }
    if fmt in ("anime_whatif", "recurring_character"):
        out["characters"] = [{"name": "Arta", "role": "hero", "personality": "brave", "appearance": "short black hair, blue cape", "is_original": True}]
    return out


# ------------------------------------------------------------------ series plan

def series_plan(meta: dict) -> dict:
    fa, fmt = _fa(meta), _fmt(meta)
    n = int(meta.get("episodes_count") or 5)
    dur = int(meta.get("episode_length_sec") or 45)
    title = meta.get("title") or meta.get("page_name") or "Series"
    premise = meta.get("premise") or meta.get("idea") or title
    hero = _hero(meta)
    arcs_n = max(1, min(3, (n + 1) // 2))
    arcs = []
    for i in range(1, arcs_n + 1):
        arcs.append({
            "title": (f"بخش {i}" if fa else f"Arc {i}"),
            "summary": (f"بخش {i} از داستان «{title}»؛ {hero} با چالش تازه‌ای روبه‌رو می‌شود." if fa
                        else f"Arc {i} of '{title}': {hero} faces a new challenge."),
            "goal": "پیشبردِ هدفِ اصلی" if fa else "Advance the main goal",
            "cliffhanger": "یک راز تازه فاش می‌شود" if fa else "A new secret is revealed",
        })
    eps = []
    for k in range(1, n + 1):
        arc = min(arcs_n, (k - 1) * arcs_n // n + 1)
        if fa:
            lines = {
                "anime_whatif": f"اگر در لحظه‌ی انشعاب، {hero} راه دیگری را انتخاب می‌کرد، در قسمت {k} چه می‌شد؟",
                "recurring_character": f"{hero} در قسمت {k} با موقعیتی خنده‌دار روبه‌رو می‌شود.",
                "concept_explainer": f"قسمت {k}: بخشی از «{premise}» به زبان ساده.",
            }
            eps.append({"number": k, "arc": arc, "title": f"قسمت {k}", "logline": lines.get(fmt, f"قسمت {k} از {title}"),
                        "goal": "پیشبرد داستان" if fmt != "concept_explainer" else "فهم یک ایده‌ی کلیدی",
                        "cliffhanger": "اما چیزی ناگهان تغییر می‌کند..." if k < n else "پایان فصل", "duration_sec": dur})
        else:
            eps.append({"number": k, "arc": arc, "title": f"Episode {k}", "logline": f"Episode {k} of {title} featuring {hero}.",
                        "goal": "Advance the story", "cliffhanger": "But then something changes..." if k < n else "Season finale",
                        "duration_sec": dur})
    plan = {"title": title, "premise": premise, "arcs": arcs, "episodes": eps,
            "content_rules": (["شخصیت‌های اصلی ثابت می‌مانند.", "هر قسمت با قلاب شروع و با کلیف‌هنگر تمام می‌شود."] if fa
                              else ["Main characters stay consistent.", "Every episode opens with a hook and ends on a cliffhanger."])}
    if fmt == "anime_whatif":
        plan["branch_point"] = meta.get("branch_point") or ("تصمیم کلیدیِ پایانِ فصل اول" if fa else "The key decision at the end of season one")
        plan["alternative_timeline"] = ("جهانی که در آن آن تصمیم عوض شد؛ پیامدهایش قسمت‌به‌قسمت باز می‌شود." if fa
                                        else "A world where that decision changed; consequences unfold episode by episode.")
    return plan


# ------------------------------------------------------------------ script

_FA_BLOCKS = {
    "anime_whatif": [
        "فرض کن در آن شب سرنوشت‌ساز، {hero} تصمیم دیگری می‌گرفت.",
        "شهر در سکوت فرو رفته بود و فقط صدای باد از میان برج‌ها می‌گذشت.",
        "{hero} نفس عمیقی کشید؛ این بار قرار نبود عقب بنشیند.",
        "هم‌پیمانانش هنوز نمی‌دانستند که مسیر داستان همین حالا عوض شده است.",
        "در دلِ تاریکی، نشانه‌ای کوچک روشن شد و همه‌چیز معنای تازه‌ای پیدا کرد.",
        "هر انتخاب، پیامدی دارد و این پیامد خیلی زودتر از انتظار رسید.",
        "دشمن قدمی به جلو گذاشت و {hero} فهمید که بازی تازه شروع شده است.",
        "و آن‌گاه، دری باز شد که هیچ‌کس انتظارش را نداشت.",
    ],
    "recurring_character": [
        "{hero} صبح زود از خواب بیدار شد و فکر کرد امروز روز خوبی است.",
        "اما قهوه‌ساز، ناگهان تصمیم گرفت امروز کار نکند!",
        "{hero} با همان لبخند همیشگی سراغ راه‌حل رفت.",
        "هرچه تلاش کرد، اوضاع خنده‌دارتر و درهم‌ریخته‌تر شد.",
        "همسایه‌ها هم سر رسیدند و هر کدام پیشنهاد عجیبی دادند.",
        "آخرش معلوم شد مشکل از یک دکمه‌ی کوچک بوده است.",
        "{hero} خندید و گفت: «فردا دوباره!»",
    ],
    "concept_explainer": [
        "بیایید «{topic}» را بدون اصطلاحات پیچیده بفهمیم.",
        "ساده‌ترین تصویر این است: یک مثال روزمره که همه آن را دیده‌ایم.",
        "این ایده از اینجا شروع شد که آدم‌ها می‌خواستند چیزی را توضیح بدهند.",
        "آنچه مورد توافق است این است که این مفهوم سه بخش اصلی دارد.",
        "در مورد بخش چهارم، دیدگاه‌ها متفاوت است و آن را به‌عنوان نظر مناقشه‌برانگیز در نظر می‌گیریم.",
        "نتیجه: وقتی بخش‌ها را کنار هم بگذاریم، تصویر شفاف‌تر می‌شود.",
    ],
}
_EN_BLOCKS = {
    "anime_whatif": ["Imagine that on that fateful night, {hero} chose differently.", "The city was silent; only the wind crossed the towers.",
                     "{hero} took a deep breath. This time there would be no stepping back.", "The allies did not yet know the story had already changed.",
                     "In the dark a small sign lit up and everything meant something new.", "Every choice has a price, and it arrived sooner than expected.",
                     "And then a door opened that nobody expected."],
    "recurring_character": ["{hero} woke up early, sure that today would be a good day.", "But the coffee machine decided not to work today!",
                            "{hero} went looking for a fix with the usual smile.", "The harder they tried, the funnier the mess became.",
                            "The neighbours showed up, each with a stranger idea.", "In the end the problem was one tiny button.",
                            "{hero} laughed and said: see you tomorrow!"],
    "concept_explainer": ["Let us understand '{topic}' without the jargon.", "The simplest picture is an everyday example we have all seen.",
                          "The idea began when people wanted to explain something.", "What is widely agreed is that the concept has three main parts.",
                          "About the fourth part, views differ, so we treat it as contested.", "Put the parts together and the picture becomes clearer."],
}


def script(meta: dict) -> dict:
    fa, fmt = _fa(meta), _fmt(meta)
    ep = meta.get("episode") or {}
    dur = int(meta.get("duration_sec") or 45)
    wps = 2.4 if fa else 2.6
    target_words = max(30, int(dur * wps * 0.9))
    hero, topic = _hero(meta), _topic(meta)
    pool = (_FA_BLOCKS if fa else _EN_BLOCKS).get(fmt) or (_FA_BLOCKS if fa else _EN_BLOCKS)["anime_whatif"]
    k = int(ep.get("number") or 1)
    sentences = []
    words = 0
    i = 0
    while words < target_words and i < 40:
        s = pool[(i + k - 1) % len(pool)].format(hero=hero, topic=topic)
        sentences.append(s)
        words += len(s.split())
        i += 1
    sentences = sentences[: max(3, len(sentences))]
    if len(sentences) < 3:
        sentences += pool[:3]
    speakers = [("راوی" if fa else "Narrator")]
    chars = meta.get("characters") or []
    if fmt != "concept_explainer" and chars:
        speakers.append(chars[0])
    blocks = []
    for j, s in enumerate(sentences):
        sp = speakers[1] if (len(speakers) > 1 and j % 4 == 3) else speakers[0]
        blocks.append({"speaker": sp, "text": s, "emotion": ("هیجان" if j % 3 == 0 else "آرام") if fa else ("excited" if j % 3 == 0 else "calm")})
    title = ep.get("title") or (f"قسمت {k}" if fa else f"Episode {k}")
    return {"title": title, "hook": sentences[0], "language": "fa" if fa else "en", "blocks": blocks,
            "cta": ep.get("cliffhanger") or ("قسمت بعد را از دست ندهید." if fa else "Do not miss the next episode.")}


# ------------------------------------------------------------------ storyboard

_FORMAT_TECH = {
    "anime_whatif": ["still_kenburns", "parallax_25d", "still_kenburns", "wan_i2v"],
    "recurring_character": ["puppet_2d", "puppet_2d", "still_kenburns"],
    "concept_explainer": ["motion_graphics", "still_kenburns", "motion_graphics", "parallax_25d"],
}
_MOVES = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "pan_down"]


def storyboard(meta: dict) -> dict:
    fa, fmt = _fa(meta), _fmt(meta)
    scr = meta.get("script") or {}
    blocks = scr.get("blocks") or []
    allowed = meta.get("allowed_techniques") or []
    techs = [t for t in _FORMAT_TECH.get(fmt, ["still_kenburns"]) if not allowed or t in allowed] or (allowed[:1] or ["still_kenburns"])
    wps = 2.4 if fa else 2.6
    style = meta.get("visual_style") or ("سبک انیمه، رنگ‌های گرم" if fa else "anime style, warm colours")
    chars = meta.get("characters") or []
    per_scene = 2
    scenes = []
    for si in range(0, len(blocks), per_scene):
        grp = blocks[si: si + per_scene]
        shots = []
        for bi, b in enumerate(grp):
            idx = si + bi
            words = max(1, len(b["text"].split()))
            dur = round(max(3.0, min(12.0, words / wps + 0.8)), 1)
            tech = techs[idx % len(techs)]
            shots.append({
                "description": (f"نمای {idx + 1}: {b['text'][:60]}" if fa else f"Shot {idx + 1}: {b['text'][:60]}"),
                "image_prompt": f"{style}; {b['text'][:80]}; vertical 9:16, clean composition",
                "technique": tech,
                "camera": {"move": _MOVES[idx % len(_MOVES)], "intensity": 0.5},
                "duration_sec": dur,
                "narration": b["text"],
                "speaker": b["speaker"],
                "sfx": "",
                "transition": "crossfade" if bi == len(grp) - 1 else "cut",
            })
        scenes.append({"title": (f"صحنه {si // per_scene + 1}" if fa else f"Scene {si // per_scene + 1}"),
                       "summary": grp[0]["text"][:90], "location": ("شهر" if fa else "city") if fmt != "concept_explainer" else ("استودیو" if fa else "studio"),
                       "characters": chars[:2], "shots": shots})
    return {"scenes": scenes}


# ------------------------------------------------------------------ research / continuity

def research_queries(meta: dict) -> dict:
    topic = _topic(meta)
    return {"queries": [topic, f"{topic} history" if not _fa(meta) else f"تاریخچه {topic}"],
            "key_points": ["تعریف", "تاریخچه", "دیدگاه‌های مختلف"] if _fa(meta) else ["definition", "history", "different views"]}


def research_claims(meta: dict) -> dict:
    srcs = meta.get("sources") or []
    fa = _fa(meta)
    claims = []
    for i, s in enumerate(srcs[:3]):
        claims.append({"claim": (f"طبق «{s.get('title')}»، این مفهوم تعریف مشخصی دارد." if fa else f"According to '{s.get('title')}', the concept has a clear definition."),
                       "stance": "established", "source_ids": [s["id"]], "explanation": ""})
    claims.append({"claim": ("تفسیر دقیق بخش آخر مورد مناقشه است." if fa else "The exact reading of the last part is contested."),
                   "stance": "contested", "source_ids": [s["id"] for s in srcs[-1:]] if srcs else [], "explanation": ""})
    claims.append({"claim": ("برخی معتقدند پیامدها گسترده‌تر است؛ این فقط حدس است." if fa else "Some believe the consequences are wider; this is speculation."),
                   "stance": "speculative", "source_ids": [], "explanation": ""})
    return {"claims": claims, "analogies": ["مثل یک نقشه که همه‌چیز را ساده می‌کند" if fa else "Like a map that simplifies everything"],
            "visual_metaphors": ["نقشه و مسیر" if fa else "map and route"], "caveats": ["این خلاصه جایگزین منابع اصلی نیست." if fa else "This summary does not replace primary sources."]}


def continuity(meta: dict) -> dict:
    fa = _fa(meta)
    ep = meta.get("episode") or {}
    k = ep.get("number") or 1
    hero = _hero(meta)
    return {
        "episode_summary": (f"در قسمت {k}، {hero} با یک انتخاب مهم روبه‌رو شد و مسیر داستان کمی تغییر کرد." if fa
                            else f"In episode {k}, {hero} faced an important choice and the story shifted slightly."),
        "facts": [f"{hero} در قسمت {k} تصمیم تازه‌ای گرفت."] if fa else [f"{hero} made a new decision in episode {k}."],
        "character_states": [{"character": hero, "state": "مصمم" if fa else "determined"}],
        "relationships": [],
        "timeline": [{"when": f"قسمت {k}" if fa else f"Episode {k}", "event": "تصمیم تازه" if fa else "A new decision"}],
        "open_threads": [{"text": f"پیامد تصمیمِ قسمت {k} هنوز روشن نیست." if fa else f"The consequence of episode {k}'s decision is unclear.", "status": "open"}],
        "future_goals": ["پاسخ به پرسشِ باز" if fa else "Answer the open question"],
    }


_TASKS = {
    "strategy": strategy, "series_plan": series_plan, "script": script, "storyboard": storyboard,
    "research_queries": research_queries, "research_claims": research_claims, "continuity": continuity,
}
