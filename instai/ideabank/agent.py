"""The idea generator: one validated model call that writes NEW bank ideas (Persian + English) for a category, in the spirit of the ones the owner liked.

Same rules as the other agent roles: one `call_json`, plain dicts out, nothing touches the database here (`bank.add_generated` saves them).
Registers a deterministic output for the fake text provider so tests, demo mode and a PC without a text model still work.
"""
from __future__ import annotations

import json

from instai.agents.runner import AgentResult, call_json
from instai.agents.schemas import _arr, _s
from instai.providers import fake

from .seed_base import CATEGORIES

KINDS = ["story", "explainer", "character"]
IDEA = {
    "type": "object", "required": ["title_fa", "title_en", "logline_fa", "logline_en", "hook_fa", "hook_en"],
    "properties": {
        "title_fa": _s(1, maxLength=160), "title_en": _s(1, maxLength=160), "logline_fa": _s(1, maxLength=600), "logline_en": _s(1, maxLength=600),
        "hook_fa": _s(1, maxLength=300), "hook_en": _s(1, maxLength=300), "kind": {"type": "string"}, "tags": _arr({"type": "string"}, maxItems=8),
    },
}
IDEAS = {"type": "object", "required": ["ideas"], "properties": {"ideas": _arr(IDEA, minItems=1, maxItems=12)}}

CATEGORY_GUIDE = {
    "psychology": "Explain ONE well-documented psychological effect or bias per idea (kind=explainer). Never invent studies, numbers or quotes.",
    "personal_development": "Practical, honest self-development ideas (kind=explainer or story). No miracle promises, no medical claims.",
    "economy": "Explain ONE economic concept per idea with an everyday example (kind=explainer). Use made-up example numbers only, never real statistics.",
    "success": "Stories or explainers about effort, failure, focus and luck (kind=story or explainer). Made-up characters only; no real people.",
    "business": "Small-business and startup lessons told as short stories or explainers. Made-up businesses only; no real brands or figures.",
    "mystery": "Original mystery / sci-fi / thriller premises for a short mini-series (kind=story). A strange rule, a personal stake and an unanswered question. Made-up people only.",
}


def idea_generator(meta: dict, provider=None) -> AgentResult:
    cat = meta.get("category") if meta.get("category") in CATEGORIES else "mystery"
    n = max(1, min(8, int(meta.get("count") or 5)))
    system = (
        "You are the idea editor of a studio that makes short vertical videos (Persian and English audiences).\n"
        f"Category: {CATEGORIES[cat]['en']}. {CATEGORY_GUIDE[cat]}\n"
        f"Write exactly {n} NEW ideas. Every idea has a short title, a one-sentence logline, and a hook (the opening line or question that makes a viewer stay), "
        "each in BOTH Persian (fa) and English (en); the two languages say the same thing in natural wording, not word-for-word translation. "
        "Persian text must be fluent and idiomatic. Ideas must differ from each other and from every title in 'existing_titles'; if 'liked' ideas are given, "
        "write more in their spirit (not copies). Never use real people, brands or franchises. Add 2-5 lower-case English tags.")
    user = "Context:\n" + json.dumps({k: meta.get(k) for k in ("existing_titles", "liked", "instruction") if meta.get(k)}, ensure_ascii=False)

    def semantic(d: dict) -> list[str]:
        titles = [i["title_en"].strip().lower() for i in d["ideas"]]
        taken = {str(t).strip().lower() for t in (meta.get("existing_titles") or [])}
        errs = []
        if len(set(titles)) < len(titles):
            errs.append("ideas must have different titles")
        if any(t in taken for t in titles):
            errs.append("an idea repeats an existing title")
        return errs

    def transform(d: dict) -> dict:
        d["ideas"] = d.get("ideas", [])[:n]
        return d

    return call_json("bank_ideas", IDEAS, system=system, user=user, meta={**meta, "category": cat, "count": n}, provider=provider, max_tokens=3500,
                     semantic=semantic, transform=transform)


def _fake_ideas(meta: dict) -> dict:
    cat = meta.get("category") if meta.get("category") in CATEGORIES else "mystery"
    n = int(meta.get("count") or 5)
    start = len(meta.get("existing_titles") or []) + 1
    out = []
    for i in range(n):
        k = start + i
        out.append({
            "title_fa": f"{fake.DEMO_TAG_FA} ایده {CATEGORIES[cat]['fa']} {k}", "title_en": f"{fake.DEMO_TAG_EN} {CATEGORIES[cat]['en']} idea {k}",
            "logline_fa": f"یک ایدهٔ نمایشی شمارهٔ {k} در دستهٔ «{CATEGORIES[cat]['fa']}».", "logline_en": f"A demo idea #{k} in the '{CATEGORIES[cat]['en']}' category.",
            "hook_fa": f"چه می‌شد اگر شمارهٔ {k} واقعی بود؟", "hook_en": f"What if number {k} were real?",
            "kind": "story" if cat == "mystery" else "explainer", "tags": ["demo", cat],
        })
    return {"ideas": out}


fake._TASKS["bank_ideas"] = _fake_ideas
