"""Series, plan, continuity, episodes, script, storyboard, shots, production and approvals."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.assets.models import Asset
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import JobSerializer, job_response
from instai.pages import formats
from instai.pages.models import ContentPage

from . import costs, services, states
from .models import (Episode, EpisodeEvent, EpisodeVersion, Scene, Series, Shot, Source, StoryArc, StoryMemoryEntry)


def bad(msg: str, **details):
    return DomainError("validation_error", msg, http_status=400, details=details or None)


# ------------------------------------------------------------------ serializers (plain dicts: explicit contract for the UI)

def series_dict(s: Series, detail: bool = False) -> dict:
    d = {"id": s.pk, "page": s.page_id, "title": s.title, "premise": s.premise, "branch_point": s.branch_point,
         "alternative_timeline": s.alternative_timeline, "content_rules": s.content_rules, "is_fan_content": s.is_fan_content,
         "franchise": s.franchise, "target_episodes": s.target_episodes, "status": s.status, "created_at": s.created_at,
         "episode_count": s.episodes.count(), "format": s.page.format}
    d["notices"] = [{"key": "fan", "text": formats.FAN_NOTICE_FA}] if (s.is_fan_content and s.page.format == formats.ANIME) else []
    if detail:
        d["arcs"] = [arc_dict(a) for a in s.arcs.all()]
        d["episodes"] = [episode_brief(e) for e in s.episodes.all()]
    return d


def arc_dict(a: StoryArc) -> dict:
    return {"id": a.pk, "series": a.series_id, "index": a.index, "title": a.title, "summary": a.summary, "goal": a.goal, "cliffhanger": a.cliffhanger}


def episode_brief(e: Episode) -> dict:
    return {"id": e.pk, "series": e.series_id, "number": e.number, "title": e.title, "logline": e.logline, "goal": e.goal,
            "cliffhanger": e.cliffhanger, "arc": e.arc_id, "arc_index": e.arc.index if e.arc_id else None, "duration_sec": e.duration_sec,
            "state": e.state, "state_label": states.LABELS_FA.get(e.state, e.state), "has_script": bool(e.script), "updated_at": e.updated_at,
            "error": e.error if e.state == states.FAILED else ""}


def shot_dict(s: Shot) -> dict:
    kf = Asset.objects.filter(shot=s, role="keyframe", is_current=True).order_by("-id").first()
    nar = Asset.objects.filter(shot=s, role="narration", is_current=True).order_by("-id").first()
    clip = Asset.objects.filter(shot=s, role="shot_clip", is_current=True).order_by("-id").first()
    est = costs.shot_estimate(s.technique, s.duration_sec)
    return {"id": s.pk, "scene": s.scene_id, "index": s.index, "description": s.description, "image_prompt": s.image_prompt,
            "negative_prompt": s.negative_prompt, "technique": s.technique, "camera": s.camera, "duration_sec": s.duration_sec,
            "narration": s.narration, "speaker": s.speaker, "sfx": s.sfx, "transition": s.transition, "seed": s.seed,
            "approved": s.approved, "status": s.status, "last_error": s.last_error, "estimate": est,
            "keyframe": {"id": kf.pk, "url": kf.url, "approved": kf.approved, "provenance": kf.provenance} if kf else None,
            "narration_asset": {"id": nar.pk, "url": nar.url, "duration_sec": nar.duration_sec} if nar else None,
            "clip": {"id": clip.pk, "url": clip.url} if clip else None}


def episode_dict(e: Episode) -> dict:
    d = episode_brief(e)
    scenes = []
    for sc in e.scenes.prefetch_related("shots", "characters"):
        scenes.append({"id": sc.pk, "index": sc.index, "title": sc.title, "summary": sc.summary, "location": sc.location, "approved": sc.approved,
                       "characters": [c.name for c in sc.characters.all()], "shots": [shot_dict(s) for s in sc.shots.all()]})
    videos = Asset.objects.filter(episode=e, role__in=("preview", "final"), is_current=True).order_by("-id")
    cover = Asset.objects.filter(episode=e, role="cover", is_current=True).order_by("-id").first()
    d.update({
        "series_title": e.series.title, "page": e.series.page_id, "page_format": e.series.page.format, "language": e.series.page.language,
        "script": e.script, "script_checks": e.script_checks, "scenes": scenes, "estimate": e.estimate or costs.episode_estimate([]), "qc": e.qc,
        "research": e.research, "notes": e.notes, "failed_state": e.failed_state,
        "allowed_next": [{"state": s, "label": states.LABELS_FA.get(s, s)} for s in states.allowed_next(e.state, e.failed_state)],
        "videos": [{"id": v.pk, "role": v.role, "url": v.url, "duration_sec": v.duration_sec, "width": v.width, "height": v.height, "fps": v.fps,
                    "codec": v.codec, "loudness_lufs": v.loudness_lufs, "size_bytes": v.size_bytes, "created_at": v.created_at,
                    "provenance": v.provenance} for v in videos],
        "cover_url": cover.url if cover else None,
        "sources": [{"id": s.pk, "title": s.title, "url": s.url, "publisher": s.publisher, "extract": s.extract, "claim": s.claim, "stance": s.stance,
                     "verified": s.verified, "added_by": s.added_by} for s in e.sources.all()],
        "jobs": JobSerializer(e.jobs.all()[:20], many=True).data,
        "stale": stale_summary(e),
    })
    return d


def stale_summary(e: Episode) -> dict:
    """Which pieces would be regenerated now (so the UI can say 'only 2 of 14 shots will be re-made')."""
    if not Shot.objects.filter(scene__episode=e).exists():
        return {}
    from instai.production import pipeline

    return {"keyframes_preview": len(pipeline.missing_keyframes(e, "preview")), "keyframes_final": len(pipeline.missing_keyframes(e, "final")),
            "narration": len(pipeline.missing_narration(e)), "shots": Shot.objects.filter(scene__episode=e).count()}


# ------------------------------------------------------------------ series

@api_view(["GET", "POST"])
def page_series(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        if not (request.data.get("title") or "").strip():
            raise bad("عنوان مجموعه لازم است.", title=["required"])
        return Response(series_dict(services.create_series(page, request.data), True), status=201)
    return Response([series_dict(s) for s in page.series.all()])


@api_view(["GET", "PATCH", "DELETE"])
def series_detail(request, pk):
    s = get_object_or_404(Series, pk=pk)
    if request.method == "DELETE":
        s.delete()
        return Response(status=204)
    if request.method == "PATCH":
        for f in ("title", "premise", "branch_point", "alternative_timeline", "content_rules", "is_fan_content", "franchise", "target_episodes"):
            if f in request.data:
                setattr(s, f, request.data[f])
        if s.is_fan_content and not s.franchise.strip() and request.data.get("is_fan_content"):
            pass  # franchise is optional; the notice is always shown
        s.save()
    return Response(series_dict(s, True))


@api_view(["POST"])
def series_plan(request, pk):
    s = get_object_or_404(Series, pk=pk)
    payload = {"series_id": s.pk}
    for k in ("episodes_count", "premise", "branch_point", "title"):
        if request.data.get(k):
            payload[k] = request.data[k]
    return job_response(queue.enqueue("story.plan", payload, page=s.page_id, title="طرح مجموعه و قسمت‌ها"))


@api_view(["POST"])
def series_apply_plan(request, pk):
    from instai.agents.jsonschema_lite import repair, validate
    from instai.agents.schemas import SERIES_PLAN

    s = get_object_or_404(Series, pk=pk)
    plan = repair(request.data.get("plan") or {}, SERIES_PLAN)
    errs = validate(plan, SERIES_PLAN)
    if errs:
        raise bad("طرح نامعتبر است.", errors=errs[:10])
    services.apply_plan(s, plan)
    return Response(series_dict(s, True))


@api_view(["GET", "POST"])
def series_memory(request, pk):
    s = get_object_or_404(Series, pk=pk)
    mem = services.ensure_memory(s)
    if request.method == "POST":
        kind = request.data.get("kind", "fact")
        if kind not in dict(StoryMemoryEntry.KINDS) or not (request.data.get("text") or "").strip():
            raise bad("نوع یا متن نامعتبر است.")
        StoryMemoryEntry.objects.create(memory=mem, kind=kind, subject=request.data.get("subject", ""), text=request.data["text"].strip(),
                                        status="open" if kind == "open_thread" else "active", key=services._key(kind, request.data.get("subject", ""),
                                                                                                            request.data["text"]))
    groups: dict = {k: [] for k, _ in StoryMemoryEntry.KINDS}
    for e in mem.entries.select_related("episode"):
        groups[e.kind].append({"id": e.pk, "subject": e.subject, "text": e.text, "status": e.status, "episode": e.episode.number if e.episode_id else None})
    return Response({"entries": groups, "digest": services.memory_digest(s)}, status=201 if request.method == "POST" else 200)


@api_view(["DELETE"])
def memory_entry(request, pk):
    get_object_or_404(StoryMemoryEntry, pk=pk).delete()
    return Response(status=204)


@api_view(["POST"])
def series_arcs(request, pk):
    s = get_object_or_404(Series, pk=pk)
    idx = (s.arcs.order_by("-index").first().index + 1) if s.arcs.exists() else 1
    a = StoryArc.objects.create(series=s, index=idx, title=request.data.get("title") or f"بخش {idx}", summary=request.data.get("summary", ""))
    return Response(arc_dict(a), status=201)


@api_view(["PATCH", "DELETE"])
def arc_detail(request, pk):
    a = get_object_or_404(StoryArc, pk=pk)
    if request.method == "DELETE":
        a.delete()
        return Response(status=204)
    for f in ("title", "summary", "goal", "cliffhanger"):
        if f in request.data:
            setattr(a, f, request.data[f])
    a.save()
    return Response(arc_dict(a))


@api_view(["GET", "POST"])
def series_episodes(request, pk):
    s = get_object_or_404(Series, pk=pk)
    if request.method == "POST":
        n = int(request.data.get("number") or (s.episodes.order_by("-number").first().number + 1 if s.episodes.exists() else 1))
        if s.episodes.filter(number=n).exists():
            raise bad("شماره‌ی قسمت تکراری است.", number=["duplicate"])
        e = Episode.objects.create(series=s, number=n, title=request.data.get("title") or f"قسمت {n}", logline=request.data.get("logline", ""),
                                   duration_sec=int(request.data.get("duration_sec") or s.page.profile("production")["episode_length_sec"]),
                                   state=states.PLANNED)
        EpisodeEvent.objects.create(episode=e, from_state=states.DRAFT, to_state=states.PLANNED, reason="added by hand", actor="user")
        return Response(episode_brief(e), status=201)
    return Response([episode_brief(e) for e in s.episodes.all()])


@api_view(["GET"])
def page_episodes(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    return Response([{**episode_brief(e), "series_title": e.series.title} for e in Episode.objects.filter(series__page=page).select_related("series", "arc")])


@api_view(["GET"])
def page_history(request, pk):
    ev = EpisodeEvent.objects.filter(episode__series__page_id=pk).select_related("episode__series").order_by("-id")[:200]
    return Response([{"id": e.pk, "episode": e.episode_id, "episode_number": e.episode.number, "series_title": e.episode.series.title,
                      "from": e.from_state, "to": e.to_state, "to_label": states.LABELS_FA.get(e.to_state, e.to_state), "reason": e.reason,
                      "actor": e.actor, "at": e.at} for e in ev])


@api_view(["GET", "POST"])
def page_sources(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        if not (request.data.get("title") or "").strip():
            raise bad("عنوان منبع لازم است.")
        s = Source.objects.create(page=page, series_id=request.data.get("series"), episode_id=request.data.get("episode"), title=request.data["title"],
                                  url=request.data.get("url", ""), publisher=request.data.get("publisher", ""), extract=request.data.get("extract", ""),
                                  claim=request.data.get("claim", ""), stance=request.data.get("stance", "established"), added_by="user")
        return Response(_source(s), status=201)
    return Response([_source(s) for s in page.sources.all()])


def _source(s: Source) -> dict:
    return {"id": s.pk, "title": s.title, "url": s.url, "publisher": s.publisher, "extract": s.extract, "claim": s.claim, "stance": s.stance,
            "verified": s.verified, "added_by": s.added_by, "episode": s.episode_id, "series": s.series_id}


@api_view(["PATCH", "DELETE"])
def source_detail(request, pk):
    s = get_object_or_404(Source, pk=pk)
    if request.method == "DELETE":
        s.delete()
        return Response(status=204)
    for f in ("title", "url", "publisher", "extract", "claim", "stance", "notes"):
        if f in request.data:
            setattr(s, f, request.data[f])
    s.save()
    return Response(_source(s))


# ------------------------------------------------------------------ episodes

def _ep(pk) -> Episode:
    return get_object_or_404(Episode.objects.select_related("series__page", "arc"), pk=pk)


@api_view(["GET", "PATCH", "DELETE"])
def episode_detail(request, pk):
    e = _ep(pk)
    if request.method == "DELETE":
        e.delete()
        return Response(status=204)
    if request.method == "PATCH":
        for f in ("title", "logline", "goal", "cliffhanger", "duration_sec", "notes"):
            if f in request.data:
                setattr(e, f, request.data[f])
        if "arc" in request.data:
            e.arc = StoryArc.objects.filter(pk=request.data["arc"], series=e.series).first()
        e.save()
    return Response(episode_dict(e))


@api_view(["POST"])
def episode_transition(request, pk):
    e = _ep(pk)
    to = request.data.get("to")
    services.transition(e, to, reason=request.data.get("reason", "manual"), actor="user")
    return Response(episode_dict(e))


def _to_scripting(e: Episode) -> None:
    """Bring an episode to a state from which a script can be (re)generated."""
    e.refresh_from_db()
    if e.state in (states.SCRIPTING,):
        return
    if e.state in (states.DRAFT,):
        services.transition(e, states.PLANNED, actor="user")
    elif e.state in (states.STORYBOARDING, states.ASSET_GENERATION, states.ANIMATION, states.ASSEMBLY, states.QUALITY_REVIEW,
                     states.READY_FOR_APPROVAL):
        services.transition(e, states.SCRIPT_REVIEW, reason="rework: new script", actor="user")
    elif e.state in (states.APPROVED, states.SCHEDULED, states.PUBLISHED):
        raise DomainError("conflict", "قسمتِ تأییدشده را ابتدا از حالت تأیید خارج کنید.")
    elif e.state == states.FAILED:
        services.transition(e, e.failed_state or states.PLANNED, actor="user")
        e.refresh_from_db()
        if e.state not in (states.PLANNED, states.SCRIPT_REVIEW, states.SCRIPTING):
            services.transition(e, states.SCRIPT_REVIEW, actor="user")
    e.refresh_from_db()


@api_view(["POST"])
def generate_script(request, pk):
    e = _ep(pk)
    _to_scripting(e)
    job = queue.enqueue("story.script", {"episode_id": e.pk}, episode=e, page=e.series.page_id, title=f"فیلم‌نامه‌ی قسمت {e.number}",
                        idempotency_key=f"script:{e.pk}:{e.updated_at.timestamp()}")
    return job_response(job)


@api_view(["PUT"])
def save_script(request, pk):
    e = _ep(pk)
    d = request.data
    blocks = d.get("blocks") or []
    if not isinstance(blocks, list) or not all(isinstance(b, dict) and str(b.get("text", "")).strip() for b in blocks):
        raise bad("هر بلوک فیلم‌نامه باید متن داشته باشد.")
    services.save_script(e, {"title": d.get("title") or e.title, "hook": d.get("hook") or (blocks[0]["text"] if blocks else ""),
                             "language": e.series.page.language, "blocks": blocks, "cta": d.get("cta", "")}, note="edited by hand")
    e.refresh_from_db()
    if e.state == states.DRAFT:
        services.transition(e, states.PLANNED, actor="user")
    if e.state == states.PLANNED and len(e.script.get("blocks", [])) >= 3:  # a script written by hand skips generation
        services.transition(e, states.SCRIPTING, reason="script written by hand", actor="user")
        services.transition(e, states.SCRIPT_REVIEW, reason="script written by hand", actor="user")
    e.refresh_from_db()
    return Response(episode_dict(e))


@api_view(["POST"])
def approve_script(request, pk):
    e = _ep(pk)
    if e.state != states.SCRIPT_REVIEW:
        raise DomainError("invalid_transition", "فقط در حالت «بازبینی فیلم‌نامه» می‌توان فیلم‌نامه را تأیید کرد.")
    services.transition(e, states.STORYBOARDING, reason="script approved", actor="user")
    job = queue.enqueue("story.continuity", {"episode_id": e.pk}, episode=e, page=e.series.page_id, title=f"به‌روزرسانی حافظه‌ی داستان (قسمت {e.number})",
                        idempotency_key=f"continuity:{e.pk}:{e.updated_at.timestamp()}")
    return Response({"episode": episode_dict(e), "job": JobSerializer(job).data}, status=200)


@api_view(["POST"])
def generate_storyboard(request, pk):
    e = _ep(pk)
    if e.state == states.SCRIPT_REVIEW:
        services.transition(e, states.STORYBOARDING, reason="script approved for storyboard", actor="user")
    if e.state != states.STORYBOARDING:
        if e.state in (states.ASSET_GENERATION, states.ANIMATION, states.ASSEMBLY, states.QUALITY_REVIEW, states.READY_FOR_APPROVAL, states.FAILED):
            if e.state == states.FAILED:
                services.transition(e, e.failed_state or states.STORYBOARDING, actor="user")
                e.refresh_from_db()
            if e.state != states.STORYBOARDING:
                services.transition(e, states.STORYBOARDING, reason="rework: new storyboard", actor="user")
        else:
            raise DomainError("not_ready", "ابتدا فیلم‌نامه را بسازید و تأیید کنید.")
    job = queue.enqueue("story.storyboard", {"episode_id": e.pk}, episode=e, page=e.series.page_id, title=f"استوری‌بورد قسمت {e.number}",
                        idempotency_key=f"storyboard:{e.pk}:{e.updated_at.timestamp()}")
    return job_response(job)


@api_view(["PUT"])
def save_storyboard(request, pk):
    from instai.agents.jsonschema_lite import repair, validate
    from instai.agents.schemas import STORYBOARD
    from instai.agents.roles import normalize_storyboard

    e = _ep(pk)
    sb = repair(request.data, STORYBOARD)
    errs = validate(sb, STORYBOARD)
    if errs:
        raise bad("استوری‌بورد نامعتبر است.", errors=errs[:10])
    if e.state in (states.ASSET_GENERATION, states.ANIMATION, states.ASSEMBLY, states.QUALITY_REVIEW, states.READY_FOR_APPROVAL):
        services.transition(e, states.STORYBOARDING, reason="rework: storyboard edited", actor="user")
    allowed = e.series.page.profile("production")["allowed_techniques"]
    services.save_storyboard(e, normalize_storyboard(sb, allowed), note="edited by hand")
    e.refresh_from_db()
    return Response(episode_dict(e))


@api_view(["POST"])
def approve_storyboard(request, pk):
    e = _ep(pk)
    services.transition(e, states.ASSET_GENERATION, reason="storyboard approved", actor="user")
    return Response(episode_dict(e))


@api_view(["POST"])
def episode_research(request, pk):
    e = _ep(pk)
    job = queue.enqueue("story.research", {"episode_id": e.pk, "topic": request.data.get("topic", "")}, episode=e, page=e.series.page_id,
                        title=f"پژوهش و منبع (قسمت {e.number})", idempotency_key=f"research:{e.pk}:{e.updated_at.timestamp()}")
    return job_response(job)


@api_view(["POST"])
def episode_produce(request, pk):
    from instai.production import pipeline

    e = _ep(pk)
    mode = request.data.get("mode", "preview")
    jobs = pipeline.start(e, mode)
    e.refresh_from_db()
    return Response({"episode": episode_dict(e), "jobs": JobSerializer(jobs, many=True).data}, status=202)


@api_view(["POST"])
def episode_approve(request, pk):
    e = _ep(pk)
    if e.state == states.QUALITY_REVIEW:
        services.transition(e, states.READY_FOR_APPROVAL, reason="quality review accepted by owner", actor="user")
    services.transition(e, states.APPROVED, reason="approved by owner", actor="user")
    return Response(episode_dict(e))


@api_view(["POST"])
def episode_revoke(request, pk):
    e = _ep(pk)
    services.transition(e, states.READY_FOR_APPROVAL, reason="approval revoked", actor="user")
    return Response(episode_dict(e))


@api_view(["POST"])
def episode_retry(request, pk):
    from instai.production import pipeline

    e = _ep(pk)
    if e.state != states.FAILED:
        raise DomainError("conflict", "این قسمت ناموفق نیست.")
    back = e.failed_state or states.ASSET_GENERATION
    services.transition(e, back, reason="retry", actor="user")
    e.refresh_from_db()
    jobs = pipeline.advance(e, request.data.get("mode", "preview")) if e.state in (states.ASSET_GENERATION, states.ANIMATION, states.ASSEMBLY) else []
    return Response({"episode": episode_dict(e), "jobs": JobSerializer(jobs, many=True).data})


@api_view(["GET"])
def episode_versions(request, pk):
    vs = EpisodeVersion.objects.filter(episode_id=pk)[:50]
    return Response([{"id": v.pk, "kind": v.kind, "note": v.note, "created_at": v.created_at, "data": v.data} for v in vs])


@api_view(["POST"])
def restore_version(request, pk):
    e = _ep(pk)
    v = get_object_or_404(EpisodeVersion, pk=request.data.get("version"), episode=e)
    if v.kind == "script":
        services.save_script(e, v.data, note=f"before restoring version {v.pk}")
    else:
        services.save_storyboard(e, v.data, note=f"before restoring version {v.pk}")
    e.refresh_from_db()
    return Response(episode_dict(e))


@api_view(["GET"])
def episode_events(request, pk):
    ev = EpisodeEvent.objects.filter(episode_id=pk)
    return Response([{"id": x.pk, "from": x.from_state, "to": x.to_state, "to_label": states.LABELS_FA.get(x.to_state, x.to_state), "reason": x.reason,
                      "actor": x.actor, "at": x.at} for x in ev])


@api_view(["GET"])
def episode_estimate(request, pk):
    e = _ep(pk)
    return Response(services.refresh_estimate(e))


# ------------------------------------------------------------------ shots

@api_view(["PATCH"])
def shot_detail(request, pk):
    s = get_object_or_404(Shot.objects.select_related("scene__episode__series__page"), pk=pk)
    from instai.agents.schemas import TECHNIQUES

    if "technique" in request.data and request.data["technique"] not in TECHNIQUES:
        raise bad("تکنیک نامعتبر است.", technique=["invalid"])
    services.update_shot(s, request.data)
    return Response(shot_dict(s))


@api_view(["POST"])
def shot_approve(request, pk):
    s = get_object_or_404(Shot, pk=pk)
    s.approved = bool(request.data.get("approved", True))
    s.save(update_fields=["approved"])
    Asset.objects.filter(shot=s, role__in=("keyframe", "narration", "shot_clip"), is_current=True).update(approved=s.approved)
    return Response(shot_dict(s))


@api_view(["POST"])
def shot_regenerate(request, pk):
    """Regenerate ONLY this shot: new seed (keyframe) and/or narration; the rest of the episode is untouched."""
    from instai.production import pipeline

    s = get_object_or_404(Shot.objects.select_related("scene__episode__series__page"), pk=pk)
    ep = s.scene.episode
    what = request.data.get("what", "keyframe")
    s.approved = False
    if what in ("keyframe", "all"):
        import random

        s.seed = random.randint(1, 2 ** 31 - 1)
    s.save()
    Asset.objects.filter(shot=s, is_current=True, role__in=(["keyframe", "shot_clip", "render_clip"] if what == "keyframe" else
                                                             ["keyframe", "narration", "shot_clip", "render_clip"])).update(approved=False, is_current=False)
    jobs = pipeline.start(ep, request.data.get("mode", "preview")) if ep.state in (
        states.ASSET_GENERATION, states.ANIMATION, states.ASSEMBLY, states.QUALITY_REVIEW, states.READY_FOR_APPROVAL, states.FAILED) else []
    return Response({"shot": shot_dict(s), "jobs": JobSerializer(jobs, many=True).data}, status=202)


@api_view(["POST"])
def scene_approve(request, pk):
    sc = get_object_or_404(Scene, pk=pk)
    sc.approved = bool(request.data.get("approved", True))
    sc.save(update_fields=["approved"])
    return Response({"id": sc.pk, "approved": sc.approved})


urlpatterns = [
    path("pages/<int:pk>/series", page_series),
    path("pages/<int:pk>/episodes", page_episodes),
    path("pages/<int:pk>/history", page_history),
    path("pages/<int:pk>/sources", page_sources),
    path("sources/<int:pk>", source_detail),
    path("series/<int:pk>", series_detail),
    path("series/<int:pk>/plan", series_plan),
    path("series/<int:pk>/apply-plan", series_apply_plan),
    path("series/<int:pk>/memory", series_memory),
    path("memory-entries/<int:pk>", memory_entry),
    path("series/<int:pk>/arcs", series_arcs),
    path("arcs/<int:pk>", arc_detail),
    path("series/<int:pk>/episodes", series_episodes),
    path("episodes/<int:pk>", episode_detail),
    path("episodes/<int:pk>/transition", episode_transition),
    path("episodes/<int:pk>/generate-script", generate_script),
    path("episodes/<int:pk>/script", save_script),
    path("episodes/<int:pk>/approve-script", approve_script),
    path("episodes/<int:pk>/generate-storyboard", generate_storyboard),
    path("episodes/<int:pk>/storyboard", save_storyboard),
    path("episodes/<int:pk>/approve-storyboard", approve_storyboard),
    path("episodes/<int:pk>/research", episode_research),
    path("episodes/<int:pk>/produce", episode_produce),
    path("episodes/<int:pk>/approve", episode_approve),
    path("episodes/<int:pk>/revoke", episode_revoke),
    path("episodes/<int:pk>/retry", episode_retry),
    path("episodes/<int:pk>/versions", episode_versions),
    path("episodes/<int:pk>/restore-version", restore_version),
    path("episodes/<int:pk>/events", episode_events),
    path("episodes/<int:pk>/estimate", episode_estimate),
    path("shots/<int:pk>", shot_detail),
    path("shots/<int:pk>/approve", shot_approve),
    path("shots/<int:pk>/regenerate", shot_regenerate),
    path("scenes/<int:pk>/approve", scene_approve),
]
