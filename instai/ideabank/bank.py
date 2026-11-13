"""The idea bank: built-in ideas (code) + the owner's ideas (database), search and filters, favourites, and "start a project from this idea".

An idea is a seed for a series: a title, a logline (what it is, one sentence) and a hook (the line that opens the video), in Persian and English,
with a category, tags, the best-fitting format and a few styles that suit it. Starting a project creates a series (and, if asked, a page) with the
look chosen ONCE for the whole project.
"""
from __future__ import annotations

import functools
import random
import re
from typing import Any

from django.db import DatabaseError, transaction

from instai.core.errors import DomainError
from instai.pages import formats
from instai.styles import library as styles

from .models import IdeaMark, IdeaUse, UserIdea
from .seed_base import CATEGORIES
from .seeds import BUILTIN_IDEAS

FIELDS = {
    "category": "mystery", "format": formats.CUSTOM, "tags": [], "title_fa": "", "title_en": "", "logline_fa": "", "logline_en": "", "hook_fa": "", "hook_en": "",
    "premise_fa": "", "premise_en": "", "suggested_styles": [], "episodes": 5,
}
_KEY = re.compile(r"[^a-z0-9_]+")


def _s(v: Any, limit: int = 2000) -> str:
    return "" if v is None else str(v).strip()[:limit]


def normalize(data: dict | None) -> dict:
    """A complete, safe idea dict: unknown keys dropped, enums clamped, style keys that do not exist removed."""
    d = data or {}
    out: dict[str, Any] = {}
    for k, default in FIELDS.items():
        v = d.get(k, default)
        if k == "category":
            v = v if v in CATEGORIES else default
        elif k == "format":
            v = v if v in formats.FORMATS else default
        elif k == "tags":
            raw = re.split(r"[,\n،]", v) if isinstance(v, str) else (v or [])
            v = [_s(x, 40) for x in raw if _s(x, 40)][:12]
        elif k == "suggested_styles":
            raw = re.split(r"[,\n،]", v) if isinstance(v, str) else (v or [])
            v = [x for x in dict.fromkeys(_s(x, 64) for x in raw) if x and styles.get_style(x)][:5]
        elif k == "episodes":
            try:
                v = max(1, min(30, int(v)))
            except (TypeError, ValueError):
                v = default
        elif k.startswith("premise"):
            v = _s(v, 4000)
        else:
            v = _s(v, 600)
        out[k] = v
    return out


def _validate(data: dict) -> dict:
    n = normalize(data)
    if not (n["title_fa"] or n["title_en"]):
        raise DomainError("validation_error", "عنوان ایده لازم است.", http_status=400, details={"title_fa": ["required"]}, message_en="The idea needs a title.")
    if not (n["logline_fa"] or n["logline_en"]):
        raise DomainError("validation_error", "خلاصهٔ یک‌جمله‌ای (لاگ‌لاین) لازم است.", http_status=400, details={"logline_fa": ["required"]},
                          message_en="The idea needs a one-sentence logline.")
    return n


# ------------------------------------------------------------------ rows

def _user_rows() -> dict[str, UserIdea]:
    try:
        return {r.key: r for r in UserIdea.objects.all()}
    except DatabaseError:
        return {}


def _marks() -> dict[str, IdeaMark]:
    try:
        return {m.key: m for m in IdeaMark.objects.all()}
    except DatabaseError:
        return {}


def _uses() -> dict[str, int]:
    from django.db.models import Count

    try:
        return {r["key"]: r["n"] for r in IdeaUse.objects.values("key").annotate(n=Count("id"))}
    except DatabaseError:
        return {}


def _entry(key: str, data: dict, *, builtin: bool, origin: str, based_on: str, marks: dict, uses: dict) -> dict:
    m = marks.get(key)
    return {"key": key, "builtin": builtin, "origin": origin, "based_on": based_on, **data, "favorite": bool(m and m.favorite), "hidden": bool(m and m.hidden),
            "uses": uses.get(key, 0)}


@functools.lru_cache(maxsize=1)
def _builtin_normalized() -> dict[str, dict]:
    return {k: normalize(v) for k, v in BUILTIN_IDEAS.items()}


def all_ideas() -> list[dict]:
    marks, uses = _marks(), _uses()
    out = [_entry(k, dict(v), builtin=True, origin="builtin", based_on="", marks=marks, uses=uses) for k, v in _builtin_normalized().items()]
    out += [_entry(k, normalize(r.data), builtin=False, origin=r.origin, based_on=r.based_on, marks=marks, uses=uses) for k, r in _user_rows().items()]
    return out


def get_idea(key: str) -> dict | None:
    return next((i for i in all_ideas() if i["key"] == key), None)


# ------------------------------------------------------------------ search / filter

def matches(idea: dict, q: str) -> bool:
    words = [w for w in styles._fold(q).split() if w]
    if not words:
        return True
    hay = styles._fold(" ".join([idea["title_fa"], idea["title_en"], idea["logline_fa"], idea["logline_en"], idea["hook_fa"], idea["hook_en"],
                                 idea["premise_fa"], idea["premise_en"], " ".join(idea["tags"]), idea["key"].replace("_", " ")]))
    return all(w in hay for w in words)


def list_ideas(*, q: str = "", category: str = "", tag: str = "", fmt: str = "", favorite: bool = False, source: str = "", include_hidden: bool = False) -> list[dict]:
    out = []
    for i in all_ideas():
        if i["hidden"] and not include_hidden:
            continue
        if category and i["category"] != category:
            continue
        if fmt and i["format"] != fmt:
            continue
        if tag and tag.lower() not in [t.lower() for t in i["tags"]]:
            continue
        if favorite and not i["favorite"]:
            continue
        if source == "builtin" and not i["builtin"]:
            continue
        if source == "mine" and i["builtin"]:
            continue
        if q and not matches(i, q):
            continue
        out.append(i)
    order = {k: v["order"] for k, v in CATEGORIES.items()}
    out.sort(key=lambda i: (not i["favorite"], order.get(i["category"], 99), i["builtin"], i["key"]))
    return out


def facets(rows: list[dict] | None = None) -> dict:
    """Counts for the filter chips: categories (in the owner's order), formats and the most used tags."""
    rows = all_ideas() if rows is None else rows
    rows = [r for r in rows if not r["hidden"]]
    cats = [{"key": k, "fa": v["fa"], "en": v["en"], "count": sum(1 for r in rows if r["category"] == k)} for k, v in sorted(CATEGORIES.items(), key=lambda kv: kv[1]["order"])]
    fmts = [{"key": k, "fa": f["label_fa"], "en": f["label_en"], "count": sum(1 for r in rows if r["format"] == k)} for k, f in formats.FORMATS.items()]
    tags: dict[str, int] = {}
    for r in rows:
        for t in r["tags"]:
            tags[t] = tags.get(t, 0) + 1
    top = sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))[:40]
    return {"categories": cats, "formats": [f for f in fmts if f["count"]], "tags": [{"tag": t, "count": n} for t, n in top], "total": len(rows)}


def random_idea(category: str = "") -> dict | None:
    rows = list_ideas(category=category)
    return random.choice(rows) if rows else None


# ------------------------------------------------------------------ write

def _unique_key(wanted: str) -> str:
    taken = set(BUILTIN_IDEAS) | set(_user_rows())
    base = _KEY.sub("_", (wanted or "idea").lower()).strip("_")[:40] or "idea"
    key, n = f"u_{base}", 2
    while key in taken:
        key = f"u_{base}_{n}"
        n += 1
    return key[:64]


def create_idea(data: dict, *, origin: str = "user", based_on: str = "") -> dict:
    norm = _validate(data)
    key = _unique_key(norm["title_en"] or norm["logline_en"] or "idea")
    UserIdea.objects.create(key=key, data=norm, origin=origin, based_on=based_on)
    return get_idea(key)  # type: ignore[return-value]


def update_idea(key: str, data: dict) -> dict:
    if key in BUILTIN_IDEAS:
        raise DomainError("conflict", "ایده‌های آماده فقط‌خواندنی‌اند؛ از آن کپی بگیرید.", message_en="Built-in ideas are read-only; make a copy first.")
    row = UserIdea.objects.filter(key=key).first()
    if not row:
        raise DomainError("not_found", http_status=404)
    merged = {**normalize(row.data), **{k: v for k, v in (data or {}).items() if k in FIELDS}}
    row.data = _validate(merged)
    row.save()
    return get_idea(key)  # type: ignore[return-value]


def delete_idea(key: str) -> None:
    if key in BUILTIN_IDEAS:
        raise DomainError("conflict", "ایده‌های آماده حذف نمی‌شوند؛ می‌توانید پنهانشان کنید.", message_en="Built-in ideas cannot be deleted; hide them instead.")
    n, _ = UserIdea.objects.filter(key=key).delete()
    if not n:
        raise DomainError("not_found", http_status=404)
    IdeaMark.objects.filter(key=key).delete()


def duplicate_idea(key: str, overrides: dict | None = None) -> dict:
    src = get_idea(key)
    if not src:
        raise DomainError("not_found", http_status=404)
    data = {k: src[k] for k in FIELDS}
    data.update({k: v for k, v in (overrides or {}).items() if k in FIELDS})
    if not (overrides or {}).get("title_fa") and data["title_fa"]:
        data["title_fa"] += " (کپی)"
    if not (overrides or {}).get("title_en") and data["title_en"]:
        data["title_en"] += " (copy)"
    return create_idea(data, origin="duplicate", based_on=key)


def set_mark(key: str, *, favorite: bool | None = None, hidden: bool | None = None) -> dict:
    if not get_idea(key):
        raise DomainError("not_found", http_status=404)
    m, _ = IdeaMark.objects.get_or_create(key=key)
    if favorite is not None:
        m.favorite = bool(favorite)
    if hidden is not None:
        m.hidden = bool(hidden)
    m.save()
    return get_idea(key)  # type: ignore[return-value]


def add_generated(items: list[dict], category: str) -> list[dict]:
    """Save ideas written by the model as the owner's ideas (origin 'generated'); an idea whose title already exists is skipped."""
    have = {(i["title_en"].lower(), i["title_fa"]) for i in all_ideas()}
    made = []
    for it in items:
        data = normalize({**it, "category": category, "format": it.get("format") or _format_of(it.get("kind"), category)})
        if not (data["title_fa"] or data["title_en"]) or (data["title_en"].lower(), data["title_fa"]) in have:
            continue
        if not (data["logline_fa"] or data["logline_en"]):
            continue
        made.append(create_idea(data, origin="generated"))
        have.add((data["title_en"].lower(), data["title_fa"]))
    return made


def _format_of(kind: str | None, category: str) -> str:
    if kind in ("story", "mystery"):
        return formats.CUSTOM
    if kind == "character":
        return formats.CHARACTER
    if kind == "explainer":
        return formats.EXPLAINER
    return formats.CUSTOM if category == "mystery" else formats.EXPLAINER


# ------------------------------------------------------------------ start a project

def start_project(key: str, data: dict) -> dict:
    """Create the series (and the page when none is given) for an idea, with the look chosen once for the whole project.

    data: page_id | page_name, language (fa|en), style_key, theme_key (optional), episodes, title. Returns {page_id, series_id, series_url}."""
    from instai.pages.models import ContentPage
    from instai.story import services

    idea = get_idea(key)
    if not idea:
        raise DomainError("not_found", http_status=404)
    lang = data.get("language") if data.get("language") in ("fa", "en") else "fa"

    def pick(base: str) -> str:
        a, b = idea[f"{base}_fa"], idea[f"{base}_en"]
        return (a or b) if lang == "fa" else (b or a)

    title = _s(data.get("title"), 200) or pick("title")
    premise = pick("premise") or pick("logline")
    hook = pick("hook")
    if hook and hook not in premise:
        premise = f"{premise}\n\n{'جملهٔ آغاز' if lang == 'fa' else 'Opening hook'}: {hook}"
    style_key = _s(data.get("style_key"), 64)
    if not style_key and not data.get("page_id") and idea["suggested_styles"]:
        style_key = idea["suggested_styles"][0]      # a new page gets the idea's best-fitting look; an existing page keeps its own unless one is chosen
    look: dict = {}
    patch: dict = {}
    if style_key:
        patch = styles.visual_patch(style_key, _s(data.get("theme_key"), 64) if data.get("theme_key") else None)
        look = {"style_key": patch["style_key"], "realism": patch["realism"], "theme_key": patch["theme_key"]}
    try:
        episodes = max(1, min(30, int(data.get("episodes") or idea["episodes"])))
    except (TypeError, ValueError):
        episodes = idea["episodes"]
    with transaction.atomic():
        if data.get("page_id"):
            page = ContentPage.objects.filter(pk=data["page_id"]).first()
            if not page:
                raise DomainError("validation_error", "صفحهٔ انتخاب‌شده پیدا نشد.", http_status=400, details={"page_id": ["invalid"]}, message_en="The chosen page was not found.")
            created = False
        else:
            name = _s(data.get("page_name"), 160) or title
            page = services.create_page({"name": name, "format": idea["format"], "languages": [lang], "idea": pick("logline")})
            created = True
            if patch:
                page.set_profile("visual", {**patch, "aspect_ratio": _aspect_of(style_key)})
        series = services.create_series(page, {"title": title, "premise": premise, "target_episodes": episodes, "languages": [lang], "look": look})
        if idea["format"] == formats.EXPLAINER:
            series.content_rules = ["Neutral and sourced", "Label contested claims", "No propaganda"]
            series.save(update_fields=["content_rules"])
        IdeaUse.objects.create(key=key, series=series, page_id=page.pk)
    return {"page_id": page.pk, "series_id": series.pk, "series_url": f"/series/{series.pk}", "page_created": created, "look": look}


def _aspect_of(style_key: str) -> str:
    st = styles.get_style(style_key) or {}
    a = (st.get("gen") or {}).get("aspect") or "9:16"
    return a if a in ("9:16", "1:1", "16:9", "4:5") else "9:16"
