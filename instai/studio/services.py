"""Development-room services: steps, brainstorm boards, research documents, the series bible and the development approval.

Same rule as story/services.py: agents return validated dicts, only this module writes them to the database.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from instai.core.errors import DomainError
from instai.pages.models import Character
from instai.story.models import Series, Source

from . import gates, templates
from .models import DevStep, Idea, ResearchDoc, SeriesBible

# English texts for the Persian reasons returned by _can_complete
EN = {
    "این مرحله هنوز خروجی ندارد.": "This step has no output yet.",
    "حداقل یک ایده را تأیید کنید.": "Approve at least one idea first.",
    "ابتدا کتاب سریال را تأیید کنید.": "Approve the series bible first.",
    "ادعاهای «مسلم» بدون منبع وجود دارد.": "Some claims are marked 'established' but have no source.",
    "کتاب سریال هنوز تأیید نشده است.": "The series bible is not approved yet.",
    "ساختار قسمت‌ها هنوز ساخته نشده است.": "The episode outline has not been made yet.",
}
STEP_STATUSES = ["todo", "active", "review", "done", "skipped"]
IDEA_STATUSES = ["proposed", "liked", "approved", "rejected"]


def bad(msg: str, en: str | None = None, **details) -> DomainError:
    return DomainError("validation_error", msg, http_status=400, details=details or None, message_en=en)


# ------------------------------------------------------------------ steps

def template_of(series: Series) -> dict:
    return templates.template_for_series(series)


@transaction.atomic
def ensure_steps(series: Series) -> list[DevStep]:
    """Create the series' development steps from its template (idempotent: existing steps keep their data and status)."""
    tpl = template_of(series)
    existing = {s.key: s for s in series.dev_steps.all()}
    out: list[DevStep] = []
    for i, st in enumerate(tpl["steps"]):
        row = existing.get(st["key"])
        if row is None:
            row = DevStep.objects.create(series=series, key=st["key"], kind=st["kind"], index=i)
        elif row.index != i or row.kind != st["kind"]:
            row.index, row.kind = i, st["kind"]
            row.save(update_fields=["index", "kind", "updated_at"])
        out.append(row)
    if series.dev_status == "none":
        series.dev_status = "developing"
        series.save(update_fields=["dev_status"])
    return out


def step_def(series: Series, key: str) -> dict:
    for st in template_of(series)["steps"]:
        if st["key"] == key:
            return st
    raise DomainError("not_found", http_status=404)


def get_step(series: Series, key: str) -> DevStep:
    ensure_steps(series)
    step_def(series, key)
    return series.dev_steps.get(key=key)


def has_content(series: Series, step: DevStep, sdef: dict | None = None) -> bool:
    k, sdef = step.kind, sdef or step_def(series, step.key)
    if k == "source":
        return bool((series.source or {}).get("title"))
    if k == "research":
        mode = sdef.get("params", {}).get("mode", "topic")
        d = series.research_docs.filter(kind=mode).first()
        return bool(d and d.content)
    if k == "brainstorm":
        return series.ideas.filter(board=sdef["params"].get("board", step.key)).exclude(status="rejected").exists()
    if k == "profile":
        return bool((step.data or {}).get("characters"))
    if k == "map":
        return len((step.data or {}).get("nodes") or []) >= 2
    if k == "timeline":
        return len((step.data or {}).get("rows") or []) >= 2
    if k == "factcheck":
        d = series.research_docs.filter(kind="topic").first()
        return bool(d and (d.content or {}).get("claims"))
    if k == "bible":
        b = SeriesBible.objects.filter(series=series).first()
        return bool(b and (b.data or {}).get("premise"))
    if k == "composition":
        return series.episodes.exists() and series.arcs.exists()
    return True


def _can_complete(series: Series, step: DevStep, sdef: dict) -> tuple[bool, str]:
    k = step.kind
    if not has_content(series, step, sdef) and k != "gate":
        return False, "این مرحله هنوز خروجی ندارد."
    if k == "brainstorm" and not series.ideas.filter(board=sdef["params"].get("board", step.key), status="approved").exists():
        return False, "حداقل یک ایده را تأیید کنید."
    if k == "bible" and SeriesBible.objects.filter(series=series, status="approved").count() == 0:
        return False, "ابتدا کتاب سریال را تأیید کنید."
    if k == "factcheck":
        d = series.research_docs.filter(kind="topic").first()
        weak = [c for c in (d.content or {}).get("claims", []) if c.get("stance") == "established" and not c.get("source_ids")] if d else []
        if weak:
            return False, "ادعاهای «مسلم» بدون منبع وجود دارد."
    if k == "gate":
        if not SeriesBible.objects.filter(series=series, status="approved").exists():
            return False, "کتاب سریال هنوز تأیید نشده است."
        if not series.episodes.exists():
            return False, "ساختار قسمت‌ها هنوز ساخته نشده است."
    return True, ""


@transaction.atomic
def set_step_status(series: Series, key: str, status: str, *, auto: bool = False) -> DevStep:
    if status not in STEP_STATUSES:
        raise bad("وضعیت مرحله نامعتبر است.", "Invalid step status.", status=["invalid"])
    step = get_step(series, key)
    sdef = step_def(series, key)
    if status == "done":
        ok, why = _can_complete(series, step, sdef)
        if not ok:
            raise DomainError("not_ready", why, message_en=EN.get(why))
        step.approved_at = timezone.now()
        step.auto_approved = auto
    elif status in ("todo", "active", "review"):
        step.approved_at, step.auto_approved = None, False
    step.status = status
    step.save()
    return step


def step_touched(series: Series, key: str) -> DevStep:
    """The step just received AI or human output. A human gate waits in `review`; a step the page's automation level does not guard passes by itself."""
    step = get_step(series, key)
    if step.status in ("done", "skipped"):
        return step
    if gates.dev_step_needs_human(series.page, step.kind):
        step.status = "review"
        step.save(update_fields=["status", "updated_at"])
        return step
    if step.kind == "bible" and SeriesBible.objects.filter(series=series).exists():
        approve_bible(series, auto=True)
        return get_step(series, key)
    ok, _ = _can_complete(series, step, step_def(series, key))
    if ok and step.kind in ("research", "map", "timeline", "profile", "source", "factcheck", "composition"):
        return set_step_status(series, key, "done", auto=True)
    step.status = "review"
    step.save(update_fields=["status", "updated_at"])
    return step


def save_step_data(series: Series, key: str, data: dict) -> DevStep:
    step = get_step(series, key)
    clean = normalize_step_data(step.kind, data, step.data or {})
    step.data = clean
    if step.status == "todo":
        step.status = "active"
    elif step.status == "done":
        step.status, step.approved_at, step.auto_approved = "review", None, False  # edited after approval: needs a new look
    step.save()
    return step


def _s(v: Any, n: int = 4000) -> str:
    return "" if v is None else str(v).strip()[:n]


def normalize_step_data(kind: str, data: dict, current: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    if kind == "map":
        nodes, ids = [], set()
        for n in (data.get("nodes") or [])[:60]:
            if not isinstance(n, dict) or not _s(n.get("title")):
                continue
            nid = _s(n.get("id")) or f"n{len(nodes) + 1}"
            while nid in ids:
                nid += "x"
            ids.add(nid)
            nodes.append({"id": nid, "title": _s(n.get("title"), 200), "description": _s(n.get("description")), "parent": _s(n.get("parent"), 40),
                          "kind": n.get("kind") if n.get("kind") in ("divergence", "direct", "ripple", "character", "world", "theme") else "ripple",
                          "episode_hint": int(n["episode_hint"]) if str(n.get("episode_hint", "")).isdigit() else 0})
        for n in nodes:  # a parent must exist (otherwise the node becomes a root)
            if n["parent"] not in ids or n["parent"] == n["id"]:
                n["parent"] = ""
        return {"nodes": nodes, "instruction": _s(data.get("instruction", current.get("instruction", "")), 600)}
    if kind == "timeline":
        rows = [{"when": _s(r.get("when"), 120), "canon": _s(r.get("canon")), "alternate": _s(r.get("alternate")), "note": _s(r.get("note"))}
                for r in (data.get("rows") or [])[:60] if isinstance(r, dict) and (_s(r.get("when")) or _s(r.get("alternate")))]
        return {"rows": rows, "summary": _s(data.get("summary", current.get("summary", "")), 800)}
    if kind == "profile":
        chars = []
        for c in (data.get("characters") or [])[:12]:
            if isinstance(c, dict) and _s(c.get("name")):
                chars.append({"name": _s(c["name"], 120), "role": _s(c.get("role"), 120), "appearance": _s(c.get("appearance")), "personality": _s(c.get("personality")),
                              "motivations": _s(c.get("motivations")), "abilities": _s(c.get("abilities")),
                              "catchphrases": [_s(x, 160) for x in (c.get("catchphrases") or []) if _s(x)][:8],
                              "visual_hooks": [_s(x, 160) for x in (c.get("visual_hooks") or []) if _s(x)][:8], "voice_notes": _s(c.get("voice_notes"), 400),
                              "is_original": bool(c.get("is_original", True))})
        return {"brief": _s(data.get("brief", current.get("brief", ""))), "characters": chars}
    return {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}


# ------------------------------------------------------------------ source material

def set_source(series: Series, src: dict) -> Series:
    """Remember the chosen source series (from a search candidate or typed by hand). A real franchise makes the series fan content."""
    title = _s(src.get("title"), 200)
    if not title:
        raise bad("نام سریال منبع لازم است.", "The source series name is required.", title=["required"])
    keep = ("provider", "id", "url", "year", "format", "episodes", "status", "genres", "description", "title_romaji", "title_native", "cover_url", "fandom_wiki")
    data = {k: src[k] for k in keep if k in src and src[k] not in (None, "")}
    data.update(title=title, manual=bool(src.get("manual") or not src.get("provider")), notes=_s(src.get("notes"), 1500))
    series.source = data
    series.franchise = title
    series.is_fan_content = True
    series.save(update_fields=["source", "franchise", "is_fan_content", "updated_at"])
    step_touched(series, _first_key(series, "source"))
    return series


def _first_key(series: Series, kind: str) -> str:
    for st in template_of(series)["steps"]:
        if st["kind"] == kind:
            return st["key"]
    raise DomainError("not_found", http_status=404)


# ------------------------------------------------------------------ ideas

def idea_dict(i: Idea) -> dict:
    return {"id": i.pk, "series": i.series_id, "board": i.board, "title": i.title, "logline": i.logline, "why": i.why, "details": i.details or {}, "tags": i.tags or [],
            "author": i.author, "status": i.status, "rating": i.rating, "parent": i.parent_id, "notes": i.notes, "language": i.language, "position": i.position,
            "created_at": i.created_at, "updated_at": i.updated_at}


def _clean_details(d: Any) -> dict:
    return {str(k)[:60]: _s(v, 1200) for k, v in (d or {}).items() if _s(v)} if isinstance(d, dict) else {}


def add_idea(series: Series, board: str, data: dict, *, author: str = "human", parent: Idea | None = None, language: str = "") -> Idea:
    title = _s(data.get("title"), 200)
    if not title:
        raise bad("عنوان ایده لازم است.", "The idea needs a title.", title=["required"])
    pos = (series.ideas.filter(board=board).order_by("-position").values_list("position", flat=True).first() or 0) + 1
    idea = Idea.objects.create(series=series, board=board, title=title, logline=_s(data.get("logline")), why=_s(data.get("why") or data.get("why_it_works")),
                               details=_clean_details(data.get("details")), tags=[_s(t, 40) for t in (data.get("tags") or []) if _s(t)][:8], author=author,
                               parent=parent, language=language, position=pos, notes=_s(data.get("notes")))
    step_key = step_for_board(series, board)
    if step_key:
        step = get_step(series, step_key)
        if step.status == "todo":
            step.status = "active"
            step.save(update_fields=["status", "updated_at"])
    return idea


def step_for_board(series: Series, board: str) -> str:
    for st in template_of(series)["steps"]:
        if st["kind"] == "brainstorm" and st["params"].get("board", st["key"]) == board:
            return st["key"]
    return ""


@transaction.atomic
def save_ai_ideas(series: Series, board: str, ideas: list[dict], *, language: str, parent: Idea | None = None) -> list[Idea]:
    rows = [add_idea(series, board, i, author="ai", parent=parent, language=language) for i in ideas]
    key = step_for_board(series, board)
    if key:
        step = get_step(series, key)
        if step.status in ("todo", "active"):
            step.status = "review"
            step.save(update_fields=["status", "updated_at"])
    return rows


def update_idea(idea: Idea, data: dict) -> Idea:
    for f, n in (("title", 200), ("logline", 4000), ("why", 4000), ("notes", 4000)):
        if f in data:
            setattr(idea, f, _s(data[f], n))
    if "why_it_works" in data:
        idea.why = _s(data["why_it_works"])
    if "details" in data:
        idea.details = _clean_details(data["details"])
    if "tags" in data:
        idea.tags = [_s(t, 40) for t in (data["tags"] or []) if _s(t)][:8]
    if not idea.title:
        raise bad("عنوان ایده لازم است.", "The idea needs a title.", title=["required"])
    if idea.author == "ai":
        idea.author = "refined"  # edited by a human: no longer pure AI output
    idea.save()
    return idea


def set_idea_status(idea: Idea, status: str) -> Idea:
    if status not in IDEA_STATUSES:
        raise bad("وضعیت ایده نامعتبر است.", "Invalid idea status.", status=["invalid"])
    idea.status = status
    idea.save(update_fields=["status", "updated_at"])
    return idea


def rate_idea(idea: Idea, rating: int) -> Idea:
    idea.rating = max(0, min(5, int(rating)))
    idea.save(update_fields=["rating", "updated_at"])
    return idea


@transaction.atomic
def merge_ideas(series: Series, ids: list[int], merged: dict, *, language: str = "") -> Idea:
    srcs = list(Idea.objects.filter(series=series, pk__in=ids))
    if len(srcs) < 2:
        raise bad("برای ادغام حداقل دو ایده لازم است.", "Merging needs at least two ideas.", ids=["too_few"])
    if len({s.board for s in srcs}) != 1:
        raise bad("ایده‌های یک تخته را می‌توان ادغام کرد.", "Only ideas from the same board can be merged.", ids=["mixed_boards"])
    card = add_idea(series, srcs[0].board, merged, author="merged", parent=srcs[0], language=language)
    card.rating = max(s.rating for s in srcs)
    card.save(update_fields=["rating"])
    for s in srcs:
        s.status = "rejected" if s.status != "approved" else s.status  # merged sources leave the active board unless already approved
        s.notes = (s.notes + f"\nmerged -> #{card.pk}").strip()
        s.save(update_fields=["status", "notes", "updated_at"])
    return card


def local_merge(ideas: list[Idea]) -> dict:
    """The human merge (no model): titles joined, loglines and reasons concatenated, details of the first card win."""
    details: dict[str, str] = {}
    for i in ideas:
        for k, v in (i.details or {}).items():
            details[k] = f"{details[k]} / {v}" if k in details and v not in details[k] else details.get(k, v)
    return {"title": " + ".join(i.title for i in ideas)[:190], "logline": " ".join(i.logline for i in ideas if i.logline)[:1500],
            "why": " ".join(i.why for i in ideas if i.why)[:1500], "details": details}


def approved_ideas(series: Series, board: str | None = None) -> list[Idea]:
    qs = series.ideas.filter(status="approved")
    return list(qs.filter(board=board) if board else qs)


def board_summary(series: Series, board: str) -> list[dict]:
    return [idea_dict(i) for i in series.ideas.filter(board=board)]


# ------------------------------------------------------------------ research documents

def _doc_dict(d: ResearchDoc) -> dict:
    return {"id": d.pk, "series": d.series_id, "kind": d.kind, "title": d.title, "content": d.content, "status": d.status, "language": d.language,
            "meta": d.meta, "updated_at": d.updated_at}


def doc_dict(d: ResearchDoc) -> dict:
    return _doc_dict(d)


@transaction.atomic
def store_research_doc(series: Series, kind: str, fetched: list[dict], content: dict, *, language: str, title: str = "", meta: dict | None = None) -> ResearchDoc:
    """Save fetched sources (verified=True: the system retrieved them) and the research content that cites them (indices -> Source ids)."""
    page = series.page
    series.sources.filter(added_by="system", episode__isnull=True, notes=kind).delete()
    id_map: dict[int, int] = {}
    for s in fetched:
        if s.get("pk"):  # a source the owner added by hand: keep it as it is
            id_map[s["id"]] = s["pk"]
            continue
        row = Source.objects.create(page=page, series=series, title=s["title"][:300], url=s.get("url", "")[:600], publisher=s.get("publisher", "")[:200],
                                    extract=s.get("extract", ""), verified=bool(s.get("verified")), added_by="system", notes=kind, stance="established",
                                    retrieved_at=timezone.now() if s.get("verified") else None)
        id_map[s["id"]] = row.pk
    content = _remap_source_ids(content, id_map)
    doc, _ = ResearchDoc.objects.update_or_create(series=series, kind=kind, defaults={"content": content, "title": title, "status": "draft",
                                                                                    "language": language, "meta": meta or {}})
    return doc


def _remap_source_ids(content: Any, id_map: dict[int, int]) -> Any:
    if isinstance(content, dict):
        return {k: ([id_map[i] for i in v if i in id_map] if k == "source_ids" and isinstance(v, list) else _remap_source_ids(v, id_map)) for k, v in content.items()}
    if isinstance(content, list):
        return [_remap_source_ids(x, id_map) for x in content]
    return content


def normalize_topic_content(content: dict) -> dict:
    """Claims keep the explainer rule: a claim with no source can never be 'established'."""
    out = dict(content or {})
    claims = []
    for c in out.get("claims") or []:
        if not isinstance(c, dict) or not _s(c.get("claim")):
            continue
        stance = c.get("stance") if c.get("stance") in ("established", "contested", "speculative") else "speculative"
        ids = [int(i) for i in (c.get("source_ids") or []) if str(i).isdigit()]
        claims.append({"claim": _s(c["claim"]), "stance": stance if (ids or stance != "established") else "speculative", "source_ids": ids,
                       "explanation": _s(c.get("explanation")), "unsupported": not ids})
    out["claims"] = claims
    out["unsupported_count"] = sum(1 for c in claims if c["unsupported"])
    return out


def update_research_doc(doc: ResearchDoc, data: dict) -> ResearchDoc:
    if "content" in data and isinstance(data["content"], dict):
        doc.content = normalize_topic_content(data["content"]) if doc.kind == "topic" else data["content"]
    if data.get("status") in ("draft", "reviewed"):
        doc.status = data["status"]
    doc.save()
    return doc


# ------------------------------------------------------------------ series bible

BIBLE_TEXT = ("title", "logline", "premise", "tone", "branch_point", "alternative_timeline", "visual_notes")
BIBLE_LISTS = ("world_rules", "themes", "content_rules")


def normalize_bible(data: dict) -> dict:
    d = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {k: _s(d.get(k)) for k in BIBLE_TEXT}
    for k in BIBLE_LISTS:
        out[k] = [_s(x, 800) for x in (d.get(k) or []) if _s(x)][:30]
    out["characters"] = [{"name": _s(c.get("name"), 120), "role": _s(c.get("role"), 120), "appearance": _s(c.get("appearance")), "personality": _s(c.get("personality")),
                          "motivations": _s(c.get("motivations")), "abilities": _s(c.get("abilities")), "is_original": bool(c.get("is_original", True))}
                         for c in (d.get("characters") or [])[:20] if isinstance(c, dict) and _s(c.get("name"))]
    out["arcs"] = [{"title": _s(a.get("title"), 200), "summary": _s(a.get("summary")), "goal": _s(a.get("goal")), "cliffhanger": _s(a.get("cliffhanger"))}
                   for a in (d.get("arcs") or [])[:20] if isinstance(a, dict) and _s(a.get("title"))]
    try:
        out["episode_count"] = max(1, min(60, int(d.get("episode_count") or 5)))
        out["episode_length_sec"] = max(10, min(180, int(d.get("episode_length_sec") or 45)))
    except (TypeError, ValueError):
        out["episode_count"], out["episode_length_sec"] = 5, 45
    return out


def bible_dict(series: Series) -> dict:
    b = SeriesBible.objects.filter(series=series).first()
    return {"data": normalize_bible(b.data if b else {}), "status": b.status if b else "draft", "version": b.version if b else 0,
            "approved_at": b.approved_at if b else None, "exists": bool(b)}


def save_bible(series: Series, data: dict, *, by_ai: bool = False) -> SeriesBible:
    clean = normalize_bible({**(SeriesBible.objects.filter(series=series).values_list("data", flat=True).first() or {}), **(data or {})}
                            if not by_ai else data)
    b, created = SeriesBible.objects.get_or_create(series=series)
    changed = clean != normalize_bible(b.data or {})
    b.data = clean
    if not created and changed:
        b.version += 1
    if changed and b.status == "approved":
        b.status, b.approved_at = "draft", None  # edited after approval: it must be approved again
    b.save()
    step_touched(series, _first_key(series, "bible"))
    return b


@transaction.atomic
def approve_bible(series: Series, *, auto: bool = False) -> dict:
    b = SeriesBible.objects.filter(series=series).first()
    if not b or not normalize_bible(b.data).get("premise"):
        raise DomainError("not_ready", "کتاب سریال هنوز نوشته نشده است.", message_en="The series bible has not been written yet.")
    b.status, b.approved_at = "approved", timezone.now()
    b.save()
    synced = sync_bible_to_series(series, b)
    key = _first_key(series, "bible")
    step = get_step(series, key)
    step.status, step.approved_at, step.auto_approved = "done", timezone.now(), auto
    step.save()
    return {"bible": bible_dict(series), "synced": synced}


def revoke_bible(series: Series) -> dict:
    b = SeriesBible.objects.filter(series=series).first()
    if b:
        b.status, b.approved_at = "draft", None
        b.save()
    step = get_step(series, _first_key(series, "bible"))
    step.status, step.approved_at = "review", None
    step.save()
    return bible_dict(series)


def sync_bible_to_series(series: Series, b: SeriesBible) -> dict:
    """Bible -> series header + page characters. Existing characters are never overwritten (the owner may have edited them)."""
    d = normalize_bible(b.data)
    if d["premise"]:
        series.premise = d["premise"]
    if d["title"] and not series.title.strip():
        series.title = d["title"]
    if d["branch_point"]:
        series.branch_point = d["branch_point"]
    if d["alternative_timeline"]:
        series.alternative_timeline = d["alternative_timeline"]
    if d["content_rules"]:
        series.content_rules = d["content_rules"]
    series.target_episodes = d["episode_count"]
    series.save()
    have = {c.name.strip().lower() for c in series.page.characters.all()}
    added = 0
    for c in d["characters"]:
        if c["name"].strip().lower() in have:
            continue
        Character.objects.create(page=series.page, name=c["name"], role=c["role"], appearance=c["appearance"], personality=c["personality"], motivations=c["motivations"],
                                 abilities=c["abilities"], is_original=c["is_original"] and not series.is_fan_content,
                                 franchise=series.franchise if (series.is_fan_content and not c["is_original"]) else "")
        added += 1
    return {"characters_added": added}


def sync_profile_characters(series: Series, step: DevStep) -> int:
    """Character bible (profile step) -> page characters (new names only)."""
    have = {c.name.strip().lower() for c in series.page.characters.all()}
    n = 0
    for c in (step.data or {}).get("characters", []):
        if c["name"].strip().lower() in have:
            continue
        hooks = "؛ ".join(c.get("visual_hooks") or [])
        Character.objects.create(page=series.page, name=c["name"], role=c["role"], appearance=(c["appearance"] + (f"\nVisual hooks: {hooks}" if hooks else "")).strip(),
                                 personality=c["personality"], motivations=c["motivations"], abilities=c["abilities"], is_original=c.get("is_original", True),
                                 profile=("Catchphrases: " + " | ".join(c.get("catchphrases") or [])) if c.get("catchphrases") else "",
                                 voice={"notes": c.get("voice_notes", "")} if c.get("voice_notes") else {})
        n += 1
    return n


# ------------------------------------------------------------------ development approval

@transaction.atomic
def approve_development(series: Series, *, auto: bool = False) -> Series:
    ensure_steps(series)
    ok, why = _can_complete(series, get_step(series, _first_key(series, "gate")), {"params": {}})
    if not ok:
        raise DomainError("not_ready", why, message_en=EN.get(why))
    for step in series.dev_steps.exclude(status__in=("done", "skipped")):
        if step.kind != "gate" and step.status in ("todo", "active", "review"):
            step.status = "skipped" if not has_content(series, step) else "done"
            step.auto_approved = True
            step.approved_at = timezone.now()
            step.save()
    gate = get_step(series, _first_key(series, "gate"))
    gate.status, gate.approved_at, gate.auto_approved = "done", timezone.now(), auto
    gate.save()
    series.dev_status, series.dev_approved_at = "approved", timezone.now()
    if series.status == "draft":
        series.status = "planned"
    series.save(update_fields=["dev_status", "dev_approved_at", "status", "updated_at"])
    return series


def reopen_development(series: Series) -> Series:
    series.dev_status, series.dev_approved_at = "developing", None
    series.save(update_fields=["dev_status", "dev_approved_at", "updated_at"])
    gate = get_step(series, _first_key(series, "gate"))
    gate.status, gate.approved_at = "review", None
    gate.save()
    return series
