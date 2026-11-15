"""Cover ideas: the facts of an episode / series -> clickable titles + a suggested layout + a background prompt.

Two paths, always in this order:

1. **The AI** through the page's text model (``instai.agents.llm``: local Ollama first, an OpenAI-compatible API as the fallback, by the page's own choice per task group).
   The answer is JSON and is checked strictly: an unknown layout, an invented price / percentage / number, a title that is too long or too short, a broken English prompt
   is thrown away (the claim guard of the NM thumbnail maker is kept).
2. **The ready-made formulas** (``engine.hooks.rule_ideas``) when the AI is not available (the text model is off, no credit, a network error) or gave too few valid ideas.
   The message then says why; every time the AI is back the first path is tried again.

No path makes up a statistic, a price or an unverified claim. Both languages (Persian and English) are supported: the language of the context decides the copy.

SOURCE: adapted from NMarketing:backend/apps/thumbs/ideation.py @ v3.02 (c23f861) for series/episode covers (instai.agents.llm instead of the NM AI router;
episode facts instead of store facts).
"""
from __future__ import annotations

import json
import logging
import re

from instai.providers import fake
from instai.providers.base import ProviderError

from .engine import hooks, palette, typo
from .engine.render import CONTENT_LIMITS
from .engine.styles import STYLES

log = logging.getLogger("instai.covers")

TASK = "cover_ideas"
MAX_IDEAS = 8
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

SCHEMA = {
    "type": "object", "required": ["ideas"],
    "properties": {"ideas": {"type": "array", "minItems": 1, "maxItems": 12, "items": {
        "type": "object", "required": ["title", "style"],
        "properties": {"title": {"type": "string", "minLength": 2, "maxLength": 120}, "subtitle": {"type": "string"}, "kicker": {"type": "string"},
                       "badge": {"type": "string"}, "tagline": {"type": "string"}, "style": {"type": "string"}, "concept": {"type": "string"},
                       "bg_prompt_en": {"type": "string"}, "mood": {"type": "string"}}}}},
}


class AIUnavailable(RuntimeError):
    """The AI did not answer. ``fa`` / ``en`` carry the reason for the user."""

    def __init__(self, fa: str, en: str):
        super().__init__(en)
        self.fa, self.en = fa, en


# ───────────────────────────── asking the AI

def _prompt(ctx: hooks.Ctx, fmt_title: str, styles: list[str], count: int) -> tuple[str, str]:
    lang_name = "Persian" if ctx.fa else "English"
    style_lines = "\n".join(f"- {k}: {STYLES[k].title_en} - {STYLES[k].short_en}" for k in styles)
    facts = {k: v for k, v in {"series": ctx.series, "episode_number": ctx.episode_number, "episode_title": ctx.episode_title, "logline": ctx.logline, "hook": ctx.hook,
                               "cliffhanger": ctx.cliffhanger, "premise": ctx.premise, "characters": list(ctx.characters), "channel": ctx.channel}.items() if v}
    system = (f"You are a senior cover designer and copywriter for an animation / film content studio. You write short, curiosity-driven {lang_name} cover titles for an "
              "episode or series, plus the best layout for each. NEVER invent prices, percentages, statistics, guarantees, results or claims that are not in the facts; "
              "the only number allowed is the episode number. No emoji. Mark the single most important word of a title with asterisks like *word*. Use a different layout "
              "for each idea when possible. 'bg_prompt_en' is an ENGLISH image-generation prompt for the background only (no text, no people, no logos) that fits the layout "
              "and the story. 'concept' is one sentence describing the visual in " + lang_name + ".")
    user = (f"Platform: {fmt_title}\nFacts (use ONLY these):\n{json.dumps(facts, ensure_ascii=False)}\n\nAvailable layouts (key - meaning):\n{style_lines}\n\n"
            f"Give exactly {count} ideas, each title 2 to 7 words in {lang_name}.")
    return system, user


def _reason(exc: Exception) -> tuple[str, str]:
    raw = str(exc)
    if "402" in raw or "insufficient" in raw.lower() or "credit" in raw.lower():
        return "اعتبارِ سرویسِ ابری تمام شده است (۴۰۲).", "The cloud service is out of credit (402)."
    if isinstance(exc, ProviderError) and exc.fa:
        return hooks.fit_text(exc.fa.split("\n")[0], 170), hooks.fit_text(raw, 170)
    if isinstance(exc, ProviderError):
        return "مدلِ متن در دسترس نیست (Ollama خاموش است یا مدل نصب نشده).", hooks.fit_text(raw, 170)
    return "هوش مصنوعی پاسخِ قابل‌استفاده نداد.", hooks.fit_text(raw, 170)


def _default_ask(page, ctx: hooks.Ctx, fmt_title: str, styles: list[str], count: int) -> tuple[dict, dict]:
    """-> (the JSON, {label}). Any failure -> AIUnavailable. Under test the fake provider answers (no network)."""
    from instai.agents import llm
    from instai.agents.runner import AgentError, call_json

    system, user = _prompt(ctx, fmt_title, styles, count)
    try:
        provider = llm.resolve(page, TASK)
        res = call_json(TASK, SCHEMA, system=system, user=user, meta={"language": ctx.lang, "ctx": ctx.__dict__ | {"characters": list(ctx.characters)}, "count": count},
                        provider=provider, max_attempts=2, temperature=0.7, max_tokens=2500)
    except (ProviderError, AgentError) as exc:
        fa, en = _reason(exc)
        raise AIUnavailable(fa, en) from exc
    label = f"{res.provider}:{res.model}" if res.model else res.provider
    return res.data, {"label": label}


# ───────────────────────────── checking the AI's answer

def _text(text, ctx: hooks.Ctx) -> str:
    t = typo.clean(text)
    t = _EMOJI.sub("", t).strip()
    return typo.to_fa_digits(t) if ctx.fa else t


def _risky(text: str, source: str) -> bool:
    low, src = text.lower(), source.lower()
    return any(w in low and w not in src for w in hooks.RISKY)


def _bad_number(text: str, allowed: set[str]) -> bool:
    """A number in the text that the facts do not contain (an invented statistic)."""
    for m in re.findall(r"[0-9۰-۹]+", text):
        if m.translate(_DIGITS) not in allowed:
            return True
    return False


def clean_ai_ideas(parsed, *, ctx: hooks.Ctx, fmt: str, source_text: str) -> list[dict]:
    """The raw JSON -> checked ideas (an idea with a bad title is dropped; any other bad field becomes empty)."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ideas"), list):
        return []
    pref = hooks.preferred_styles(fmt)
    allowed = {x.translate(_DIGITS) for x in re.findall(r"[0-9۰-۹]+", source_text)}
    out: list[dict] = []
    seen: set[str] = set()
    for i, raw in enumerate(parsed["ideas"][:MAX_IDEAS * 2]):
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("title"), ctx)
        words = typo.plain(title).split()
        if not (2 <= len(words) <= 10) or len(typo.plain(title)) > 70 or _risky(title, source_text) or _bad_number(title, allowed):
            continue
        key = typo.plain(title)
        if key in seen:
            continue
        seen.add(key)
        style = raw.get("style") if raw.get("style") in STYLES else pref[i % len(pref)]

        def field(name: str, limit: int) -> str:
            v = _text(raw.get(name), ctx)
            if len(v) > limit:
                v = hooks.clip(v, 999, ctx.lang, limit)[0]
            return "" if (_risky(v, source_text) or _bad_number(v, allowed)) else v

        prompt_en = typo.clean(raw.get("bg_prompt_en"))[:260]
        if not prompt_en or not hooks.ASCII_PROMPT.match(prompt_en):
            prompt_en = hooks.bg_prompt(style)
        elif "no text" not in prompt_en.lower():
            prompt_en += hooks.BG_SUFFIX
        d = {k: "" for k in CONTENT_LIMITS}
        d.update(title=title, subtitle=field("subtitle", 60), kicker=field("kicker", 24) or ctx.series[:24], badge=field("badge", CONTENT_LIMITS["badge"]),
                 tagline=field("tagline", 60), channel=ctx.channel, number=hooks.digits(ctx.episode_number, ctx.lang) if (ctx.episode_number and style in ("episode_card", "number_list")) else "")
        concept = field("concept", 220)
        d.update(style=style, formula="ai", formula_label_fa="پیشنهادِ هوش مصنوعی", formula_label_en="AI suggestion", source="ai", bg_prompt_en=prompt_en,
                 mood=raw.get("mood") if raw.get("mood") in palette.MOODS else "", concept_fa=concept if ctx.fa else hooks.CONCEPTS[style][0].format(t=hooks.short_topic(ctx.topic, 4, "fa")),
                 concept_en=concept if not ctx.fa else hooks.CONCEPTS[style][1].format(t=hooks.short_topic(ctx.topic, 4, "en")))
        out.append(d)
    return out


# ───────────────────────────── the result

def decorate(idea: dict, idx: int, fmt: str) -> dict:
    """Add the layout title and a ready spec patch so the page applies the idea with one click."""
    sd = STYLES[idea["style"]]
    content = {k: idea.get(k, "") for k in CONTENT_LIMITS}
    out = dict(idea)
    out.update({"id": f"i{idx + 1}", "style_title_fa": sd.title_fa, "style_title_en": sd.title_en, "format": fmt, "needs_second": sd.needs_second,
                "spec_patch": {"format": fmt, "style": idea["style"], "content": content, "colors": {"mood": idea.get("mood") or ""}}})
    return out


def ideate(ctx_dict: dict, *, fmt: str = "youtube", count: int = 6, use_ai: bool = True, variation: int = 0, page=None, ask=None) -> dict:
    """-> {via, ai:{tried, ok, label, reason_fa, reason_en}, message_fa, message_en, ideas[], format, topic}. ``ask`` can be injected (tests)."""
    from .engine import formats as F

    ctx = hooks.make_ctx(ctx_dict)
    if not typo.plain(ctx.topic):
        raise ValueError("empty topic")
    fmt_obj = F.get(fmt)
    count = max(2, min(MAX_IDEAS, int(count or 6)))
    source_text = " ".join([ctx.series, str(ctx.episode_number or ""), ctx.episode_title, ctx.logline, ctx.hook, ctx.cliffhanger, ctx.premise, ctx.branch_point,
                            " ".join(ctx.characters), ctx.channel, " ".join(l for _, l in ctx.dialogue)])
    rules = hooks.rule_ideas(ctx, fmt=fmt, count=count, variation=variation)
    ai = {"tried": False, "ok": False, "label": "", "reason_fa": "", "reason_en": ""}
    ideas: list[dict] = []
    if use_ai:
        ai["tried"] = True
        styles = [k for k in list(hooks.preferred_styles(fmt)) + [k for k in STYLES if k not in hooks.preferred_styles(fmt)] if k in STYLES][:12]
        try:
            parsed, info = (ask or _default_ask)(page, ctx, fmt_obj.title_en, styles, count)
            ideas = clean_ai_ideas(parsed, ctx=ctx, fmt=fmt, source_text=source_text)
            ai.update(ok=bool(ideas), label=str((info or {}).get("label") or ""))
            if not ideas:
                ai.update(reason_fa="هوش مصنوعی جوابِ قابل‌استفاده نداد.", reason_en="The AI gave no usable answer.")
        except AIUnavailable as exc:
            ai.update(reason_fa=hooks.fit_text(exc.fa, 300), reason_en=hooks.fit_text(exc.en, 300))
        except Exception as exc:  # noqa: BLE001 - nothing may stop the ready-made ideas
            log.exception("covers.ideation: the AI path crashed")
            ai.update(reason_fa="خطای پیش‌بینی‌نشده در هوش مصنوعی.", reason_en=hooks.fit_text(f"Unexpected AI error: {exc}", 300))
    via = "rules"
    if ideas:
        via = "ai"
        if len(ideas) < min(3, count):
            have = {typo.plain(i["title"]) for i in ideas}
            ideas += [r for r in rules if typo.plain(r["title"]) not in have][: count - len(ideas)]
            via = "mixed"
        ideas = ideas[:count]
    else:
        ideas = rules
    if not ideas:
        raise ValueError("no idea")
    ideas = [decorate(i, n, fmt) for n, i in enumerate(ideas)]
    label = f" ({ai['label']})" if ai["label"] else ""
    if via == "ai":
        fa, en = f"ایده‌ها را هوش مصنوعی نوشت{label}؛ همه را پیش از استفاده ویرایش کنید.", f"The ideas were written by the AI{label}; edit them before use."
    elif via == "mixed":
        fa, en = "چند ایده از هوش مصنوعی آمد و بقیه از فرمول‌های آماده تکمیل شد.", "A few ideas came from the AI and the rest were completed from the ready-made formulas."
    elif use_ai:
        fa = ("هوش مصنوعی در دسترس نبود، برای همین از فرمول‌های آماده استفاده شد" + (f" ({ai['reason_fa']})" if ai["reason_fa"] else "")
              + ". وقتی هوش مصنوعی برگردد همین دکمه پیشنهادهای هوشمند می‌دهد.")
        en = ("The AI was not available, so the ready-made formulas were used" + (f" ({ai['reason_en']})" if ai["reason_en"] else "")
              + ". When the AI is back the same button gives smart suggestions.")
    else:
        fa, en = "ایده‌ها از فرمول‌های آماده ساخته شد (هوش مصنوعی خاموش بود).", "The ideas were made from the ready-made formulas (the AI was off)."
    return {"topic": ctx.topic, "format": fmt, "lang": ctx.lang, "via": via, "ai": ai, "message_fa": fa, "message_en": en, "ideas": ideas}


# ───────────────────────────── the fake text provider (tests, demo mode, a PC without a model)

def _fake_ideas(meta: dict) -> dict:
    c = meta.get("ctx") or {}
    lang = meta.get("language") or "fa"
    n = int(meta.get("count") or 3)
    base = str(c.get("episode_title") or c.get("series") or ("جهان" if lang == "fa" else "the world"))
    styles = ["episode_card", "cliffhanger", "character_face", "neon"]
    tag = fake.DEMO_TAG_FA if lang == "fa" else fake.DEMO_TAG_EN
    words_fa, words_en = ("اول", "دوم", "سوم", "چهارم"), ("one", "two", "three", "four")
    return {"ideas": [{"title": (f"راز {base} {words_fa[k % 4]}" if lang == "fa" else f"The secret of {base} {words_en[k % 4]}")[:60], "subtitle": "", "kicker": "", "badge": "", "tagline": "",
                       "style": styles[k % len(styles)], "concept": f"{tag} concept", "bg_prompt_en": "soft abstract gradient background", "mood": ""} for k in range(n)]}


fake._TASKS[TASK] = _fake_ideas
