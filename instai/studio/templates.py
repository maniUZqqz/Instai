"""Format templates: which development steps a series goes through before episodes are written.

A template is data, not code. The three launch formats ship as built-in templates; the owner can duplicate any template or write a
new one in the UI (pick steps, titles, the brainstorm lens of each board). `base_format` supplies the policy flags (fan notice,
sourced content, synthetic presenter) and the agent guidance of the closest launch format.

Step kinds (each has a UI panel and, where it needs a model, an agent role):
  source       choose the source material (real series via online search, or typed by hand)
  research     canon research (characters, arcs, events, timeline, world rules) or topic research with sources
  brainstorm   an ideas board: AI proposes, humans add; edit / merge / rate / reject / approve / "more like this"
  profile      a character design brief turned into a character bible
  map          consequence ("butterfly-effect") map of a changed event
  timeline     alternative timeline rows (canon vs changed world)
  factcheck    claims reviewed against stored sources (established / contested / speculative)
  bible        the series bible (premise, world rules, characters, tone, themes, arcs, length)
  composition  episode-by-episode outline (series composition) with arcs
  gate         final approval of the development phase (the "greenlight")
"""
from __future__ import annotations

import copy
import re
from typing import Any

from django.db import DatabaseError

from instai.pages import formats

STEP_KINDS = ["source", "research", "brainstorm", "profile", "map", "timeline", "factcheck", "bible", "composition", "gate"]
# What each brainstorm board is asking for (the role prompt differs per lens).
LENSES = {
    "divergence": {"fa": "نقطهٔ انشعاب (چه چیزی عوض شود؟)", "en": "Divergence point (what changes?)"},
    "series_concept": {"fa": "ایدهٔ مجموعه", "en": "Series concept"},
    "scenario": {"fa": "سناریوهای قسمت‌ها", "en": "Episode scenarios"},
    "gag_format": {"fa": "شوخی‌های تکرارشونده و قالب‌ها", "en": "Running gags & formats"},
    "topic": {"fa": "موضوع‌های توضیح", "en": "Topics to explain"},
    "analogy": {"fa": "قیاس و استعارهٔ تصویری", "en": "Analogies & visual metaphors"},
    "character_concept": {"fa": "ایدهٔ شخصیت", "en": "Character concept"},
}
RESEARCH_MODES = ["canon", "topic"]
PROFILE_MODES = ["character"]


def _step(key, kind, fa, en, help_fa, help_en, **params) -> dict:
    return {"key": key, "kind": kind, "title_fa": fa, "title_en": en, "help_fa": help_fa, "help_en": help_en, "params": params}


BUILTIN_TEMPLATES: dict[str, dict] = {
    "anime_whatif": {
        "key": "anime_whatif", "base_format": "anime_whatif", "builtin": True, "needs_source": True,
        "name_fa": "چه می‌شد اگر… (انیمه)", "name_en": "What-If (anime)",
        "description_fa": "سریالِ منبع را انتخاب کنید، دانش «کانن» را پژوهش کنید، نقطهٔ انشعاب را با هم ایده‌پردازی کنید و نقشهٔ پیامدها و خط زمانی جایگزین را بسازید.",
        "description_en": "Pick a source series, research its canon, brainstorm the divergence point together, then build the consequence map and the alternative timeline.",
        "default_series": {"episodes": 5, "episode_length_sec": 45},
        "steps": [
            _step("source", "source", "سریال منبع", "Source series", "سریال یا انیمهٔ مرجع را جست‌وجو کنید یا دستی بنویسید.", "Search for the reference series or type it by hand."),
            _step("canon", "research", "پژوهش کانن", "Canon research", "شخصیت‌ها، کمان‌ها، رویدادهای کلیدی، خط زمانی و قوانین جهان؛ همه با منبع.",
                  "Characters, arcs, key events, timeline and world rules, each with sources.", mode="canon"),
            _step("divergence", "brainstorm", "ایده‌پردازی نقطهٔ انشعاب", "Divergence-point brainstorm", "چه رویدادی را عوض کنیم؟ هوش مصنوعی و شما پیشنهاد می‌دهید؛ ایده‌ها را ویرایش، ادغام و تأیید کنید.",
                  "Which event do we change? AI and you propose; edit, merge and approve ideas.", lens="divergence", board="divergence", count=6),
            _step("map", "map", "نقشهٔ پیامدها (اثر پروانه‌ای)", "Consequence map (butterfly effect)", "از نقطهٔ انشعابِ تأییدشده، پیامدهای مستقیم و زنجیره‌ای را بسط دهید.",
                  "Expand the approved divergence into direct and ripple consequences."),
            _step("timeline", "timeline", "خط زمانی جایگزین", "Alternative timeline", "هر رویداد در جهان اصلی و در جهان تغییرکرده.", "Each event in the canon world and in the changed world."),
            _step("bible", "bible", "کتاب سریال", "Series bible", "فرضیه، قوانین جهان، شخصیت‌ها، لحن، مضمون‌ها، کمان‌ها و طول قسمت‌ها.",
                  "Premise, world rules, characters, tone, themes, arcs and episode length.", gate=True),
            _step("composition", "composition", "ساختار سریال (قسمت‌به‌قسمت)", "Series composition (episode by episode)", "طرح هر قسمت با کلیف‌هنگر.", "An outline of every episode with cliffhangers.", gate=True),
            _step("approval", "gate", "تأیید نهایی مرحلهٔ توسعه", "Development approval", "پس از تأیید، نوشتن فیلم‌نامه‌ی قسمت‌ها شروع می‌شود.", "After approval the episode scripts can start.", gate=True),
        ],
    },
    "recurring_character": {
        "key": "recurring_character", "base_format": "recurring_character", "builtin": True, "needs_source": False,
        "name_fa": "شخصیت تکرارشونده", "name_en": "Recurring character",
        "description_fa": "از یادداشت طراحی شخصیت شروع کنید، کتاب شخصیت بسازید و سناریوها و قالب‌های شوخی را ایده‌پردازی کنید.",
        "description_en": "Start from a character design brief, build the character bible, then brainstorm scenarios and gag formats.",
        "default_series": {"episodes": 6, "episode_length_sec": 30},
        "steps": [
            _step("brief", "profile", "یادداشت طراحی شخصیت", "Character design brief", "شخصیت را توصیف کنید؛ هوش مصنوعی آن را به «کتاب شخصیت» تبدیل می‌کند.",
                  "Describe the character; AI turns it into a character bible.", mode="character"),
            _step("scenarios", "brainstorm", "ایده‌پردازی سناریو", "Scenario brainstorm", "موقعیت‌هایی که شخصیت در آن‌ها قرار می‌گیرد.", "Situations the character gets into.",
                  lens="scenario", board="scenarios", count=8),
            _step("formats", "brainstorm", "شوخی‌های تکرارشونده و قالب‌ها", "Gags & series formats", "شوخی‌های ثابت، جمله‌های تکیه‌کلام و بخش‌های تکراریِ هر قسمت.",
                  "Running gags, catchphrases and recurring segments.", lens="gag_format", board="formats", count=6),
            _step("bible", "bible", "کتاب سریال", "Series bible", "فرضیه، شخصیت‌ها، لحن و قالب قسمت‌ها.", "Premise, characters, tone and episode format.", gate=True),
            _step("composition", "composition", "ساختار سریال (قسمت‌به‌قسمت)", "Series composition (episode by episode)", "طرح هر قسمت.", "An outline of every episode.", gate=True),
            _step("approval", "gate", "تأیید نهایی مرحلهٔ توسعه", "Development approval", "پس از تأیید، نوشتن فیلم‌نامه‌ی قسمت‌ها شروع می‌شود.", "After approval the episode scripts can start.", gate=True),
        ],
    },
    "concept_explainer": {
        "key": "concept_explainer", "base_format": "concept_explainer", "builtin": True, "needs_source": False,
        "name_fa": "توضیح مفاهیم", "name_en": "Concept explainer",
        "description_fa": "موضوع‌ها را ایده‌پردازی کنید، با منبع پژوهش کنید، قیاس‌ها را بسازید و ادعاها را راستی‌آزمایی کنید.",
        "description_en": "Brainstorm topics, research them with sources, build analogies and fact-check the claims.",
        "default_series": {"episodes": 5, "episode_length_sec": 60},
        "steps": [
            _step("topics", "brainstorm", "ایده‌پردازی موضوع", "Topic brainstorm", "چه مفهوم‌هایی را توضیح بدهیم؟", "Which concepts do we explain?", lens="topic", board="topics", count=8),
            _step("research", "research", "پژوهش با منبع", "Research with sources", "منبع‌ها را بیاورید یا اضافه کنید؛ ادعاها فقط از روی منبع نوشته می‌شوند.",
                  "Fetch or add sources; claims are written only from sources.", mode="topic"),
            _step("analogies", "brainstorm", "ایده‌پردازی ساده‌سازی و قیاس", "Simplification & analogy brainstorm", "قیاس و استعارهٔ تصویری برای هر مفهوم.", "An analogy and a visual metaphor for each concept.",
                  lens="analogy", board="analogies", count=6),
            _step("factcheck", "factcheck", "راستی‌آزمایی", "Fact check", "هر ادعا: مسلم، مناقشه‌برانگیز یا حدس؛ ادعای بی‌منبع «مسلم» نمی‌شود.",
                  "Each claim: established, contested or speculative; an unsourced claim can never be 'established'."),
            _step("bible", "bible", "کتاب سریال", "Series bible", "فرضیه، مخاطب، لحن، قواعد بی‌طرفی و ساختار قسمت‌ها.", "Premise, audience, tone, neutrality rules and episode structure.", gate=True),
            _step("composition", "composition", "ساختار سریال (قسمت‌به‌قسمت)", "Series composition (episode by episode)", "طرح هر قسمت.", "An outline of every episode.", gate=True),
            _step("approval", "gate", "تأیید نهایی مرحلهٔ توسعه", "Development approval", "پس از تأیید، نوشتن فیلم‌نامه‌ی قسمت‌ها شروع می‌شود.", "After approval the episode scripts can start.", gate=True),
        ],
    },
    "custom": {
        "key": "custom", "base_format": "custom", "builtin": True, "needs_source": False,
        "name_fa": "قالب دلخواه", "name_en": "Custom",
        "description_fa": "ایده‌پردازی، کتاب سریال و ساختار قسمت‌ها؛ برای هر ایده‌ای.", "description_en": "Brainstorm, series bible and composition; for any idea.",
        "default_series": {"episodes": 5, "episode_length_sec": 45},
        "steps": [
            _step("concepts", "brainstorm", "ایده‌پردازی مجموعه", "Series brainstorm", "ایدهٔ مجموعه را با هم پیدا کنید.", "Find the series idea together.", lens="series_concept", board="concepts", count=6),
            _step("bible", "bible", "کتاب سریال", "Series bible", "فرضیه، شخصیت‌ها، لحن و کمان‌ها.", "Premise, characters, tone and arcs.", gate=True),
            _step("composition", "composition", "ساختار سریال (قسمت‌به‌قسمت)", "Series composition (episode by episode)", "طرح هر قسمت.", "An outline of every episode.", gate=True),
            _step("approval", "gate", "تأیید نهایی مرحلهٔ توسعه", "Development approval", "پس از تأیید، نوشتن فیلم‌نامه‌ی قسمت‌ها شروع می‌شود.", "After approval the episode scripts can start.", gate=True),
        ],
    },
}


# ------------------------------------------------------------------ normalising user templates

_KEY = re.compile(r"[^a-z0-9_]+")


def slug(text: str) -> str:
    return _KEY.sub("_", (text or "").lower().strip()).strip("_")[:40] or "template"


def normalize_step(raw: Any, used: set[str]) -> dict | None:
    if not isinstance(raw, dict) or raw.get("kind") not in STEP_KINDS:
        return None
    kind = raw["kind"]
    key = slug(str(raw.get("key") or raw.get("title_en") or kind))
    base, n = key, 2
    while key in used:
        key = f"{base}_{n}"
        n += 1
    used.add(key)
    params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    clean: dict[str, Any] = {}
    if kind == "brainstorm":
        clean["lens"] = params.get("lens") if params.get("lens") in LENSES else "series_concept"
        clean["board"] = slug(str(params.get("board") or key))
        try:
            clean["count"] = max(2, min(12, int(params.get("count") or 6)))
        except (TypeError, ValueError):
            clean["count"] = 6
    elif kind == "research":
        clean["mode"] = params.get("mode") if params.get("mode") in RESEARCH_MODES else "topic"
    elif kind == "profile":
        clean["mode"] = "character"
    if kind in ("bible", "composition", "gate") or raw.get("gate"):
        clean["gate"] = True
    title_fa = str(raw.get("title_fa") or raw.get("title_en") or key).strip()[:120]
    title_en = str(raw.get("title_en") or raw.get("title_fa") or key).strip()[:120]
    out = {"key": key, "kind": kind, "title_fa": title_fa, "title_en": title_en, "help_fa": str(raw.get("help_fa") or "").strip()[:400],
           "help_en": str(raw.get("help_en") or "").strip()[:400], "params": {k: v for k, v in clean.items() if k != "gate"}}
    if clean.get("gate"):
        out["params"]["gate"] = True
    return out


def normalize_template(data: dict | None, *, key: str = "") -> dict:
    d = data or {}
    base = d.get("base_format") if d.get("base_format") in formats.FORMATS else formats.CUSTOM
    used: set[str] = set()
    steps = [s for s in (normalize_step(x, used) for x in (d.get("steps") or [])[:30]) if s]
    # a series must be able to finish: bible + composition + gate are always present, in that order, at the end
    for kind, fa, en in (("bible", "کتاب سریال", "Series bible"), ("composition", "ساختار سریال (قسمت‌به‌قسمت)", "Series composition"),
                         ("gate", "تأیید نهایی مرحلهٔ توسعه", "Development approval")):
        if not any(s["kind"] == kind for s in steps):
            steps.append(normalize_step({"kind": kind, "title_fa": fa, "title_en": en, "key": kind}, used))  # type: ignore[arg-type]
    tail = [s for s in steps if s["kind"] in ("bible", "composition", "gate")]
    steps = [s for s in steps if s["kind"] not in ("bible", "composition", "gate")] + sorted(tail, key=lambda s: ["bible", "composition", "gate"].index(s["kind"]))
    ds = d.get("default_series") if isinstance(d.get("default_series"), dict) else {}
    try:
        eps = max(1, min(60, int(ds.get("episodes") or 5)))
        dur = max(10, min(180, int(ds.get("episode_length_sec") or 45)))
    except (TypeError, ValueError):
        eps, dur = 5, 45
    return {"key": key or str(d.get("key") or ""), "base_format": base, "builtin": False, "needs_source": bool(d.get("needs_source")) or any(s["kind"] == "source" for s in steps),
            "name_fa": str(d.get("name_fa") or d.get("name_en") or "").strip()[:120], "name_en": str(d.get("name_en") or d.get("name_fa") or "").strip()[:120],
            "description_fa": str(d.get("description_fa") or "").strip()[:600], "description_en": str(d.get("description_en") or "").strip()[:600],
            "default_series": {"episodes": eps, "episode_length_sec": dur}, "steps": steps}


# ------------------------------------------------------------------ lookup (built-ins + database)

def _user_templates() -> dict[str, dict]:
    from .models import FormatTemplate

    try:
        return {t.key: {**normalize_template(t.data, key=t.key), "builtin": False} for t in FormatTemplate.objects.all()}
    except DatabaseError:
        return {}


def all_templates() -> list[dict]:
    return [copy.deepcopy(t) for t in BUILTIN_TEMPLATES.values()] + list(_user_templates().values())


def get_template(key: str | None) -> dict:
    key = key or ""
    if key in BUILTIN_TEMPLATES:
        return copy.deepcopy(BUILTIN_TEMPLATES[key])
    user = _user_templates()
    if key in user:
        return user[key]
    return copy.deepcopy(BUILTIN_TEMPLATES["custom"])


def template_for_page(page) -> dict:
    return get_template(page.template_key or page.format)


def template_for_series(series) -> dict:
    return get_template(series.template_key or series.page.template_key or series.page.format)
