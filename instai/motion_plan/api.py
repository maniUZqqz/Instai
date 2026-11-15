"""Motion plan API (the scene-plan engine behind the `motion_graphics` technique and the Remotion page).

  GET  /api/motion/components                      the component library (labels fa+en, fields, samples), the quick-start templates, the platforms, the sizes
  POST /api/motion/plan/validate   {spec, kit?}    a stand-alone check: the cleaned plan, the silent corrections, the timeline, the rule findings (no browser)
  POST /api/motion/plan/fallback   {narration, seconds, style, theme, size, lang, series?}   the deterministic plan of a narration (no model)
  GET  /api/shots/<id>/motion                      the plan of a motion-graphics shot (null when none yet), its kit, its length, the clip that exists
  POST /api/shots/<id>/motion      {action: write|qa|critique, force?}   a job (the plan is written by the text model or the fallback / the checks / the visual critique)
  GET  /api/motion/plans/<id>                      one plan with its versions, the QA report and the critique
  PUT  /api/motion/plans/<id>      {spec}          the owner's edit (one new version)
  POST /api/motion/plans/<id>/patch   {ops} or {request}   a patch (a request in plain words is turned into ops by the rules, then by the model)
  POST /api/motion/plans/<id>/undo | redo | restore {n}
  POST /api/motion/plans/<id>/qa | critique        a job each
"""
from __future__ import annotations

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.remotion import kit as kitmod

from . import components, fallback, motionlib, plans, qa, role, shots, specs, timeline
from . import patch as patch_mod
from .models import MotionPlan


def _bad(field: str, fa: str, en: str) -> DomainError:
    return DomainError("validation_error", fa, http_status=400, details={field: ["invalid"]}, message_en=en)


def _plan(pk) -> MotionPlan:
    p = MotionPlan.objects.select_related("shot__scene__episode__series__page").filter(pk=pk).first()
    if p is None:
        raise DomainError("not_found", "این طرح پیدا نشد.", http_status=404, message_en="Plan not found")
    return p


def _shot(pk):
    from instai.story.models import Shot

    s = Shot.objects.select_related("scene__episode__series__page").filter(pk=pk).first()
    if s is None:
        raise DomainError("not_found", "این شات پیدا نشد.", http_status=404, message_en="Shot not found")
    return s


def _plan_error(e: Exception) -> DomainError:
    return DomainError("validation_error", str(e), http_status=400, message_en=getattr(e, "en", str(e)))


@api_view(["GET"])
def components_view(request):
    return Response({"components": components.public_list(), "templates": specs.TEMPLATES, "sizes": list(specs.SIZES), "default_size": specs.DEFAULT_SIZE,
                     "platforms": [{"key": k, "fa": v["fa"], "en": v["en"], "size": v["size"], "safe": v["safe"]} for k, v in motionlib.PLATFORMS.items() if k],
                     "limits": {"max_scenes": specs.MAX_SCENES, "scene_s": [specs.MIN_SCENE_S, specs.MAX_SCENE_S], "total_s": specs.MAX_TOTAL_S}, "icons": list(components.ICON_NAMES)})


@api_view(["POST"])
def validate_view(request):
    d = request.data if isinstance(request.data, dict) else {}
    notes: list = []
    kit = kitmod.style_kit((d.get("spec") or {}).get("style") or None, (d.get("spec") or {}).get("theme") or None) if isinstance(d.get("spec"), dict) else None
    try:
        spec = specs.normalize_spec(d.get("spec"), notes=notes, kit=kit)
    except specs.SpecError as e:
        raise _bad("spec", str(e), e.en)
    t = timeline.seconds(spec, kit)
    findings = qa.static_findings(spec, kit)
    bad = [f for f in findings if f["severity"] in ("error", "warn")]
    fa = "قاعده‌ها: مشکلی پیدا نشد." if not bad else f"قاعده‌ها: {qa.fa(len(bad))} مورد پیدا شد؛ بازبینی خودکار آن‌ها را اصلاح می‌کند."
    en = "Rules: nothing found." if not bad else f"Rules: {len(bad)} issue(s) found; the automatic check fixes them."
    return Response({"spec": spec, "notes": notes, "timeline": {"starts": t["starts"], "ends": t["ends"], "total": t["total"], "fps": t["fps"]}, "findings": findings,
                     "summary_fa": fa, "summary_en": en})


@api_view(["POST"])
def fallback_view(request):
    d = request.data if isinstance(request.data, dict) else {}
    narration = str(d.get("narration") or "")[:2000]
    try:
        seconds = float(d.get("seconds") or 8)
    except (TypeError, ValueError):
        raise _bad("seconds", "مدت باید عدد باشد.", "seconds must be a number")
    kit = kitmod.style_kit(d.get("style") or None, d.get("theme") or None)
    size = d.get("size") if d.get("size") in specs.SIZES else specs.DEFAULT_SIZE
    try:
        spec = fallback.make_plan(narration, max(1.0, min(specs.MAX_TOTAL_S, seconds)), lang=d.get("lang") if d.get("lang") in ("fa", "en") else "fa", style=kit["key"],
                                  theme=str(d.get("theme") or ""), size=size, series=specs.normalize_series(d.get("series")), kit=kit)
    except specs.SpecError as e:
        raise _bad("narration", str(e), e.en)
    return Response({"spec": spec, "origin": "fallback"})


def shot_state(shot) -> dict:
    ep = shot.scene.episode
    plan = shots.latest_plan(shot)
    clip = shots.current_clip(shot)
    from instai.production import pipeline

    narrated = bool(shots.narration_of(shot)) and pipeline.current(shot, "narration") is not None
    return {"shot_id": shot.pk, "technique": shot.technique, "plan": plans.plan_dict(plan) if plan else None, "kit": shots.kit_of_episode(ep), "size": shots.render_size(ep),
            "seconds": shots.target_seconds(shot, ep), "narration_ready": narrated or not shots.narration_of(shot), "lang": ep.series.page.language,
            "edited": bool(plan and shots.edited_by_owner(plan)), "stale": bool(plan and plan.source_hash != shots.inputs_hash(shot, ep, shots.target_seconds(shot, ep))),
            "clip": ({"asset_id": clip.pk, "url": clip.url, "duration": clip.duration_sec, "current": bool(plan and clip.input_hash == shots.clip_hash(plan, shot, ep, "final"))} if clip else None)}


@api_view(["GET", "POST"])
def shot_motion_view(request, pk: int):
    shot = _shot(pk)
    if request.method == "GET":
        return Response(shot_state(shot))
    d = request.data if isinstance(request.data, dict) else {}
    action = d.get("action") or "write"
    if shot.technique != shots.TECHNIQUE:
        raise DomainError("conflict", "این شات با تکنیک «گرافیک متحرک» ساخته نمی‌شود.", http_status=409, message_en="This shot does not use the motion graphics technique")
    ep = shot.scene.episode
    if action == "write":
        job = queue.enqueue("motion.plan", {"shot_id": shot.pk, "force": bool(d.get("force", True))}, episode=ep, page=ep.series.page, title=f"motion plan {shot.scene.index}.{shot.index}", max_attempts=2)
        return job_response(job)
    plan = shots.latest_plan(shot)
    if plan is None:
        raise DomainError("not_ready", "برای این شات هنوز طرحی نوشته نشده است.", http_status=409, message_en="This shot has no plan yet")
    if action == "qa":
        return job_response(queue.enqueue("motion.qa", {"plan_id": plan.pk}, episode=ep, page=ep.series.page, title="motion check", max_attempts=1))
    if action == "critique":
        return job_response(queue.enqueue("motion.critique", {"plan_id": plan.pk}, episode=ep, page=ep.series.page, title="motion critique", max_attempts=1))
    raise _bad("action", "کار نامعتبر است.", "unknown action")


@api_view(["GET", "PUT"])
def plan_view(request, pk: int):
    plan = _plan(pk)
    if request.method == "PUT":
        d = request.data if isinstance(request.data, dict) else {}
        try:
            plan = plans.commit(plan, d.get("spec"), label=str(d.get("label") or "edit")[:120], source="user", coalesce=bool(d.get("coalesce")))
        except plans.PlanError as e:
            raise _plan_error(e)
    return Response(plans.plan_dict(plan))


@api_view(["POST"])
def plan_patch_view(request, pk: int):
    plan = _plan(pk)
    d = request.data if isinstance(request.data, dict) else {}
    lang = d.get("lang") if d.get("lang") in ("fa", "en") else "fa"
    say, by = "", "ops"
    ops = d.get("ops")
    source = "patch"
    if ops is None:
        request_text = str(d.get("request") or "").strip()
        if not request_text:
            raise _bad("request", "یک درخواست یا فهرست تغییرها بدهید.", "give a request or a list of changes")
        provider = None
        try:
            from instai.agents import llm

            if plan.shot_id:
                provider = llm.resolve(plan.shot.scene.episode.series.page, "storyboard")
        except Exception:  # noqa: BLE001
            provider = None
        r = role.write_patch(plan.spec, request_text[:500], lang=lang, provider=provider)
        ops, say, by, source = r["ops"], r["say"], r["by"], "chat"
        if not ops:
            return Response({"plan": plans.plan_dict(plan), "applied": False, "say": say, "by": by})
    try:
        plan, summary = plans.apply_ops(plan, ops, source=source, label=(say or "")[:120])
    except plans.PlanError as e:
        raise _plan_error(e)
    return Response({"plan": plans.plan_dict(plan), "applied": True, "say": say, "by": by, "summary": summary})


@api_view(["POST"])
def plan_undo_view(request, pk: int):
    try:
        return Response(plans.plan_dict(plans.step(_plan(pk), -1)))
    except plans.PlanError as e:
        raise _plan_error(e)


@api_view(["POST"])
def plan_redo_view(request, pk: int):
    try:
        return Response(plans.plan_dict(plans.step(_plan(pk), 1)))
    except plans.PlanError as e:
        raise _plan_error(e)


@api_view(["POST"])
def plan_restore_view(request, pk: int):
    d = request.data if isinstance(request.data, dict) else {}
    try:
        return Response(plans.plan_dict(plans.restore(_plan(pk), int(d.get("n") or 0))))
    except (plans.PlanError, ValueError, TypeError) as e:
        raise _plan_error(e) if isinstance(e, plans.PlanError) else _bad("n", "شمارهٔ نسخه معتبر نیست.", "invalid version number")


@api_view(["POST"])
def plan_qa_view(request, pk: int):
    plan = _plan(pk)
    ep = plan.shot.scene.episode if plan.shot_id else None
    return job_response(queue.enqueue("motion.qa", {"plan_id": plan.pk}, episode=ep, page=ep.series.page if ep else None, title="motion check", max_attempts=1))


@api_view(["POST"])
def plan_critique_view(request, pk: int):
    plan = _plan(pk)
    ep = plan.shot.scene.episode if plan.shot_id else None
    return job_response(queue.enqueue("motion.critique", {"plan_id": plan.pk}, episode=ep, page=ep.series.page if ep else None, title="motion critique", max_attempts=1))


urlpatterns = [
    path("motion/components", components_view),
    path("motion/plan/validate", validate_view),
    path("motion/plan/fallback", fallback_view),
    path("shots/<int:pk>/motion", shot_motion_view),
    path("motion/plans/<int:pk>", plan_view),
    path("motion/plans/<int:pk>/patch", plan_patch_view),
    path("motion/plans/<int:pk>/undo", plan_undo_view),
    path("motion/plans/<int:pk>/redo", plan_redo_view),
    path("motion/plans/<int:pk>/restore", plan_restore_view),
    path("motion/plans/<int:pk>/qa", plan_qa_view),
    path("motion/plans/<int:pk>/critique", plan_critique_view),
]
