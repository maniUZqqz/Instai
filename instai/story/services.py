"""Application services: the ONLY place where agent output is written to the database.

Agents return validated dicts; they never write rows or run commands. Everything here is small, transactional and testable.
"""
from __future__ import annotations

import difflib
import hashlib
import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from instai.core.errors import DomainError
from instai.pages import formats, profiles
from instai.pages.models import Character, ContentPage

from . import costs, states
from .models import (Episode, EpisodeEvent, EpisodeVersion, Scene, Series, Shot, Source, StoryArc, StoryMemory,
                     StoryMemoryEntry)

# ------------------------------------------------------------------ pages

@transaction.atomic
def create_page(data: dict) -> ContentPage:
    fmt = data.get("format") or formats.ANIME
    fdef = formats.get_format(fmt)
    page = ContentPage.objects.create(
        name=data["name"].strip(), handle=(data.get("handle") or "").strip(), format=fmt if fmt in formats.FORMATS else formats.CUSTOM,
        languages=data.get("languages") or ["fa"], idea=data.get("idea") or "",
        automation_level=data.get("automation_level") or "manual")
    prof = data.get("profiles") or {}
    prod = {"episodes_per_series": fdef["default_series"]["episodes"], "episode_length_sec": fdef["default_series"]["episode_length_sec"],
            "allowed_techniques": fdef["default_techniques"]}
    base = {
        "identity": {"display_name": page.name, "handle": page.handle, "languages": page.languages},
        "production": prod,
    }
    for kind in profiles.KINDS:
        merged = {**base.get(kind, {}), **(prof.get(kind) or {})}
        if kind == "production":
            merged["preset"] = merged.get("preset") or "balanced"
        page.set_profile(kind, merged)
    for ch in data.get("characters") or []:
        add_character(page, ch)
    if data.get("strategy"):
        apply_strategy(page, data["strategy"], add_characters=not data.get("characters"))
    if data.get("series"):
        s = data["series"]
        series = create_series(page, {"title": s.get("title") or page.name, "premise": s.get("premise") or page.idea,
                                      "branch_point": s.get("branch_point", ""), "target_episodes": s.get("episodes")
                                      or prod["episodes_per_series"], "is_fan_content": bool(s.get("is_fan_content")),
                                      "franchise": s.get("franchise", "")})
        if fmt == formats.EXPLAINER:
            series.content_rules = ["Neutral and sourced", "Label contested claims", "No propaganda"]
            series.save(update_fields=["content_rules"])
    return page


def add_character(page: ContentPage, data: dict) -> Character:
    return Character.objects.create(
        page=page, name=str(data.get("name", "")).strip()[:120] or "?", role=data.get("role", ""), profile=data.get("profile", ""),
        personality=data.get("personality", ""), appearance=data.get("appearance", ""), abilities=data.get("abilities", ""),
        motivations=data.get("motivations", ""), voice=data.get("voice") or {}, is_original=bool(data.get("is_original", True)),
        franchise=data.get("franchise", ""))


def apply_strategy(page: ContentPage, strategy: dict, *, add_characters: bool = True) -> None:
    page.set_profile("strategy", {
        "positioning": strategy.get("positioning", ""), "audience_insight": strategy.get("audience_insight", ""),
        "tone_guidelines": strategy.get("tone_guidelines", ""),
        "pillars": [p.get("title", "") if isinstance(p, dict) else str(p) for p in strategy.get("content_pillars", [])],
        "hashtags": strategy.get("hashtags", []), "risks": strategy.get("risks", [])})
    plan = strategy.get("posting_plan") or {}
    if plan.get("per_week"):
        page.set_profile("publishing", {"per_week": plan["per_week"], "hashtags": strategy.get("hashtags", [])})
    if plan.get("episode_length_sec"):
        page.set_profile("production", {"episode_length_sec": plan["episode_length_sec"]})
    if add_characters:
        have = {c.name for c in page.characters.all()}
        for ch in strategy.get("characters", []):
            if ch.get("name") and ch["name"] not in have:
                add_character(page, ch)


# ------------------------------------------------------------------ series and plan

def create_series(page: ContentPage, data: dict) -> Series:
    series = Series.objects.create(
        page=page, title=data.get("title") or page.name, premise=data.get("premise", ""), branch_point=data.get("branch_point", ""),
        alternative_timeline=data.get("alternative_timeline", ""), content_rules=data.get("content_rules") or [],
        is_fan_content=bool(data.get("is_fan_content")), franchise=data.get("franchise", ""),
        target_episodes=int(data.get("target_episodes") or page.profile("production")["episodes_per_series"]))
    ensure_memory(series)
    return series


def ensure_memory(series: Series) -> StoryMemory:
    mem, _ = StoryMemory.objects.get_or_create(series=series)
    return mem


@transaction.atomic
def apply_plan(series: Series, plan: dict, *, overwrite_header: bool = True) -> Series:
    """Write a (possibly user-edited) series plan: header fields, arcs, episodes. Episodes that already have work are kept."""
    if overwrite_header:
        for f in ("title", "premise", "branch_point", "alternative_timeline"):
            if plan.get(f):
                setattr(series, f, plan[f])
        if plan.get("content_rules"):
            series.content_rules = plan["content_rules"]
    series.target_episodes = len(plan["episodes"])
    series.status = "planned"
    series.save()
    series.arcs.all().delete()
    arcs = {}
    for i, a in enumerate(plan["arcs"], 1):
        arcs[i] = StoryArc.objects.create(series=series, index=i, title=a["title"], summary=a.get("summary", ""), goal=a.get("goal", ""),
                                          cliffhanger=a.get("cliffhanger", ""))
    numbers = set()
    for e in plan["episodes"]:
        numbers.add(e["number"])
        ep = Episode.objects.filter(series=series, number=e["number"]).first()
        fields = dict(title=e["title"], logline=e.get("logline", ""), goal=e.get("goal", ""), cliffhanger=e.get("cliffhanger", ""),
                      arc=arcs.get(e.get("arc") or 1), duration_sec=int(e.get("duration_sec") or 45))
        if ep is None:
            ep = Episode.objects.create(series=series, number=e["number"], state=states.PLANNED, **fields)
            EpisodeEvent.objects.create(episode=ep, from_state=states.DRAFT, to_state=states.PLANNED, reason="series plan", actor="system")
        elif ep.state in (states.DRAFT, states.PLANNED):
            for k, v in fields.items():
                setattr(ep, k, v)
            if ep.state == states.DRAFT:
                EpisodeEvent.objects.create(episode=ep, from_state=states.DRAFT, to_state=states.PLANNED, reason="series plan", actor="system")
                ep.state = states.PLANNED
            ep.save()
        else:  # already has work: keep content, only re-link the arc
            ep.arc = fields["arc"]
            ep.save(update_fields=["arc"])
    for ep in series.episodes.exclude(number__in=numbers):
        if ep.state in (states.DRAFT, states.PLANNED) and not ep.script:
            ep.delete()
    return series


# ------------------------------------------------------------------ state machine

def _guard(ep: Episode, to: str) -> None:
    if to == states.SCRIPTING and not ep.title.strip():
        raise DomainError("not_ready", "قسمت عنوان ندارد.")
    if (to == states.SCRIPT_REVIEW and ep.state == states.SCRIPTING) or (to == states.STORYBOARDING and ep.state == states.SCRIPT_REVIEW):
        if len((ep.script or {}).get("blocks", [])) < 3:
            raise DomainError("not_ready", "فیلم‌نامه‌ی کامل وجود ندارد.")
    if to == states.ASSET_GENERATION and ep.state == states.STORYBOARDING and not Shot.objects.filter(scene__episode=ep).exists():
        raise DomainError("not_ready", "هنوز هیچ شاتی در استوری‌بورد نیست.")
    if to in (states.READY_FOR_APPROVAL, states.APPROVED):
        from instai.assets.models import Asset

        if not Asset.objects.filter(episode=ep, role__in=("preview", "final"), is_current=True).exists():
            raise DomainError("not_ready", "هنوز ویدئویی برای این قسمت ساخته نشده است.")


def transition(ep: Episode, to: str, *, reason: str = "", actor: str = "user", error: str = "") -> Episode:
    """Validated state change. Atomic compare-and-set so two workers cannot both move the same episode."""
    ep.refresh_from_db(fields=["state", "failed_state"])
    frm = ep.state
    if frm == to:
        return ep
    if not states.can_transition(frm, to, ep.failed_state):
        raise DomainError("invalid_transition", f"تغییر از «{states.LABELS_FA.get(frm, frm)}» به «{states.LABELS_FA.get(to, to)}» مجاز نیست.",
                          details={"from": frm, "to": to, "allowed": states.allowed_next(frm, ep.failed_state)})
    _guard(ep, to)
    failed_state = frm if to == states.FAILED else ""
    n = Episode.objects.filter(pk=ep.pk, state=frm).update(state=to, failed_state=failed_state, error=error if to == states.FAILED else "",
                                                           updated_at=timezone.now())
    if n != 1:
        raise DomainError("conflict", "وضعیت قسمت هم‌زمان تغییر کرد؛ دوباره امتحان کنید.")
    EpisodeEvent.objects.create(episode=ep, from_state=frm, to_state=to, reason=reason[:300], actor=actor)
    ep.refresh_from_db()
    return ep


def fail_episode(ep: Episode, message: str) -> None:
    ep.refresh_from_db(fields=["state"])
    if ep.state not in (states.FAILED, states.CANCELLED, states.PUBLISHED):
        transition(ep, states.FAILED, reason=message[:300], actor="system", error=message[:2000])


# ------------------------------------------------------------------ script

def snapshot(ep: Episode, kind: str, note: str = "") -> None:
    data = ep.script if kind == "script" else storyboard_dict(ep)
    if data:
        EpisodeVersion.objects.create(episode=ep, kind=kind, data=data, note=note[:300])


def save_script(ep: Episode, script: dict, *, note: str = "", checks: dict | None = None) -> Episode:
    from instai.agents.roles import reading_stats

    if ep.script:
        snapshot(ep, "script", note or "before replace")
    blocks = []
    for i, b in enumerate(script.get("blocks", []), 1):
        blocks.append({"id": i, "speaker": str(b.get("speaker", "")), "text": str(b.get("text", "")).strip(), "emotion": b.get("emotion", "")})
    script = {**script, "blocks": [b for b in blocks if b["text"]]}
    ep.script = script
    lang = script.get("language") or ep.series.page.language
    ep.script_checks = checks or reading_stats(script, lang, ep.duration_sec)
    if script.get("title") and not ep.title:
        ep.title = script["title"]
    ep.save()
    return ep


# ------------------------------------------------------------------ storyboard

def storyboard_dict(ep: Episode) -> dict:
    scenes = []
    for sc in ep.scenes.prefetch_related("shots", "characters"):
        scenes.append({"index": sc.index, "title": sc.title, "summary": sc.summary, "location": sc.location,
                       "characters": [c.name for c in sc.characters.all()],
                       "shots": [{"index": s.index, "description": s.description, "image_prompt": s.image_prompt, "technique": s.technique,
                                  "camera": s.camera, "duration_sec": s.duration_sec, "narration": s.narration, "speaker": s.speaker,
                                  "sfx": s.sfx, "transition": s.transition} for s in sc.shots.all()]})
    return {"scenes": scenes} if scenes else {}


@transaction.atomic
def save_storyboard(ep: Episode, sb: dict, *, note: str = "") -> Episode:
    """Replace the episode's scenes/shots with `sb` (the old storyboard is kept as a version)."""
    snapshot(ep, "storyboard", note or "before replace")
    names = {c.name: c for c in ep.series.page.characters.all()}
    ep.scenes.all().delete()
    neg = ep.series.page.profile("visual").get("negative_prompt", "")
    for si, sc in enumerate(sb["scenes"], 1):
        scene = Scene.objects.create(episode=ep, index=si, title=sc.get("title", ""), summary=sc.get("summary", ""),
                                     location=sc.get("location", ""))
        scene.characters.set([names[n] for n in sc.get("characters", []) if n in names])
        for hi, sh in enumerate(sc["shots"], 1):
            est = costs.shot_estimate(sh["technique"], float(sh["duration_sec"]), "final")
            Shot.objects.create(scene=scene, index=hi, description=sh.get("description", ""), image_prompt=sh.get("image_prompt", ""),
                                negative_prompt=neg, technique=sh["technique"], camera=sh.get("camera") or {},
                                duration_sec=float(sh["duration_sec"]), narration=sh.get("narration", ""), speaker=sh.get("speaker", ""),
                                sfx=sh.get("sfx", ""), transition=sh.get("transition") or "cut", est_gpu_seconds=est["gpu_seconds"],
                                status="ready")
    refresh_estimate(ep)
    return ep


def all_shots(ep: Episode) -> list[Shot]:
    return list(Shot.objects.filter(scene__episode=ep).select_related("scene").order_by("scene__index", "index"))


def refresh_estimate(ep: Episode) -> dict:
    ep.estimate = costs.episode_estimate(all_shots(ep))
    ep.save(update_fields=["estimate", "updated_at"])
    return ep.estimate


def update_shot(shot: Shot, data: dict) -> Shot:
    """Edit one shot. Only this shot becomes stale (its asset hash changes); approval is cleared."""
    allowed = {"description", "image_prompt", "negative_prompt", "technique", "camera", "duration_sec", "narration", "speaker", "sfx",
               "transition", "seed"}
    changed = False
    for k, v in data.items():
        if k in allowed and getattr(shot, k) != v:
            setattr(shot, k, v)
            changed = True
    if changed:
        shot.approved = False
        shot.status = "ready"
        shot.est_gpu_seconds = costs.shot_estimate(shot.technique, shot.duration_sec)["gpu_seconds"]
        shot.save()
        refresh_estimate(shot.scene.episode)
    return shot


# ------------------------------------------------------------------ story memory

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (text or "").lower())).strip()


def _key(kind: str, subject: str, text: str) -> str:
    return hashlib.sha1(f"{kind}|{_norm(subject)}|{_norm(text)}".encode()).hexdigest()[:40]


@transaction.atomic
def apply_continuity(ep: Episode, data: dict) -> int:
    """Add what the episode established to the series' StoryMemory. Re-running replaces this episode's entries."""
    mem = ensure_memory(ep.series)
    mem.entries.filter(episode=ep).delete()
    rows: list[StoryMemoryEntry] = []

    def add(kind: str, text: str, subject: str = "", status: str = "active", key: str | None = None):
        if text and text.strip():
            rows.append(StoryMemoryEntry(memory=mem, kind=kind, subject=subject[:200], text=text.strip(), status=status, episode=ep,
                                         key=key or _key(kind, subject, text)))

    add("episode_summary", data.get("episode_summary", ""), f"#{ep.number}")
    for f in data.get("facts", []):
        add("fact", f)
    for c in data.get("character_states", []):
        add("character_state", c["state"], c["character"])
    for r in data.get("relationships", []):
        add("relationship", r["status"], f"{r['a']} - {r['b']}")
    for t in data.get("timeline", []):
        add("timeline", t["event"], t.get("when", ""))
    open_now = {e.key: e.text for e in mem.entries.filter(kind="open_thread", status="open").exclude(episode=ep)}
    for th in data.get("open_threads", []):
        if th.get("status") == "resolved":
            match = difflib.get_close_matches(th["text"], list(open_now.values()), n=1, cutoff=0.6)
            if match:
                k = next(k for k, v in open_now.items() if v == match[0])
                add("open_thread", match[0], status="resolved", key=k)
        else:
            add("open_thread", th["text"], status="open")
    for g in data.get("future_goals", []):
        add("future_goal", g)
    StoryMemoryEntry.objects.bulk_create(rows)
    return len(rows)


def memory_digest(series: Series, *, before_episode: int | None = None) -> dict:
    """Compact, current view of the memory for prompts: latest state per subject, still-open threads, last summaries."""
    mem = ensure_memory(series)
    qs = mem.entries.select_related("episode").order_by("id")
    if before_episode is not None:
        qs = qs.filter(models_q_before(before_episode))
    entries = list(qs)
    latest: dict[tuple[str, str], StoryMemoryEntry] = {}
    for e in entries:
        if e.kind in ("character_state", "relationship"):
            latest[(e.kind, e.subject)] = e
    resolved = {e.key for e in entries if e.kind == "open_thread" and e.status == "resolved"}
    summaries = [e for e in entries if e.kind == "episode_summary"][-5:]
    return {
        "facts": [e.text for e in entries if e.kind == "fact"][-25:],
        "character_states": {e.subject: e.text for (k, _), e in latest.items() if k == "character_state"},
        "relationships": {e.subject: e.text for (k, _), e in latest.items() if k == "relationship"},
        "timeline": [{"when": e.subject, "event": e.text} for e in entries if e.kind == "timeline"][-15:],
        "open_threads": [e.text for e in entries if e.kind == "open_thread" and e.status == "open" and e.key not in resolved],
        "previous_summaries": [f"{e.subject}: {e.text}" for e in summaries],
        "future_goals": [e.text for e in entries if e.kind == "future_goal"][-6:],
    }


def models_q_before(n: int):
    from django.db.models import Q

    return Q(episode__isnull=True) | Q(episode__number__lt=n)


# ------------------------------------------------------------------ research

@transaction.atomic
def store_research(ep: Episode, topic: str, queries: list[str], fetched: list[dict], claims: dict) -> dict:
    """Save fetched sources (verified=True: the system retrieved them) and the claims that cite them."""
    page = ep.series.page
    id_map: dict[int, int] = {}
    ep.sources.filter(added_by="system").delete()
    for s in fetched:
        if s.get("pk"):  # a source the owner added by hand: keep it as it is
            id_map[s["id"]] = s["pk"]
            continue
        row = Source.objects.create(page=page, series=ep.series, episode=ep, title=s["title"], url=s.get("url", ""), publisher=s.get("publisher", ""),
                                    extract=s.get("extract", ""), verified=bool(s.get("verified")), added_by="system",
                                    retrieved_at=timezone.now() if s.get("verified") else None, stance="established")
        id_map[s["id"]] = row.id
    out_claims = []
    for c in claims.get("claims", []):
        ids = [id_map[i] for i in c.get("source_ids", []) if i in id_map]
        own = [s.id for s in ep.sources.filter(added_by="user")]
        ids += own if c["stance"] == "established" and not ids and own else []
        out_claims.append({"claim": c["claim"], "stance": c["stance"] if ids or c["stance"] != "established" else "speculative",
                           "source_ids": ids, "explanation": c.get("explanation", ""), "unsupported": not ids})
    ep.research = {"topic": topic, "queries": queries, "claims": out_claims, "analogies": claims.get("analogies", []),
                   "visual_metaphors": claims.get("visual_metaphors", []), "caveats": claims.get("caveats", []),
                   "unsupported_count": sum(1 for c in out_claims if c["unsupported"]), "at": timezone.now().isoformat()}
    ep.save(update_fields=["research", "updated_at"])
    return ep.research


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def unsupported_numbers(ep: Episode) -> list[str]:
    """Explainers: numbers/years in the script that no research claim or source extract contains (flagged, not blocked)."""
    if not ep.script or not ep.research:
        return []
    corpus = " ".join([c["claim"] for c in ep.research.get("claims", [])] + [s.extract for s in ep.sources.all()]).translate(_DIGITS)
    text = " ".join(b.get("text", "") for b in ep.script.get("blocks", [])).translate(_DIGITS)
    nums = set(re.findall(r"\d[\d.,]*%?", text))
    return sorted(n for n in nums if len(n.strip(".,")) >= 2 and n not in corpus)
