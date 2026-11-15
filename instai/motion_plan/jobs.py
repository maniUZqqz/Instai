"""Job handlers of the motion plan: `remotion.render` for ONE shot (called by instai/jobs/handlers/remotion.py when the payload has a shot_id), `motion.plan` (write the
plan of a shot or of a narration with the text model / the deterministic fallback), `motion.qa` (rule checks + the geometry of real frames, with automatic fixes) and
`motion.critique` (the vision model's review of the frames).

Waiting is not failing: Remotion not ready => the job WAITS (wait code remotion_setup) and the setup starts by itself; Ollama off => `motion.critique` WAITS (ollama_down).
"""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from instai.jobs.registry import handler
from instai.providers.base import ProviderError

from . import critique, plans, qa_browser, shots
from .models import MotionPlan

log = logging.getLogger("instai.motion_plan")


def _plan_resource(payload: dict) -> str:
    from instai.agents import llm

    return llm.resource_for(None, "storyboard")


def render_shot(ctx) -> dict:
    """One motion-graphics shot => its clip: plan (made when missing), rule + geometry checks with fixes, the render, the `shot_clip` asset."""
    from instai.assets import storage as asset_storage
    from instai.jobs.handlers import remotion as rh
    from instai.remotion import toolchain
    from instai.story.models import Shot

    p = ctx.payload
    shot = Shot.objects.select_related("scene__episode__series__page").get(pk=p["shot_id"])
    ep = shot.scene.episode
    mode = p.get("mode", "final")
    t0 = time.time()
    plan = shots.ensure_plan(shot, ep, ctx=ctx)                      # fast; a text model when one answers, else the deterministic plan
    ctx.check()
    st = rh.require_toolchain()                                      # not ready => WAIT (the plan stays) and the setup starts by itself
    kit, size, scale = shots.kit_of_episode(ep), shots.render_size(ep), shots.render_scale(ep, mode)
    work = toolchain.work_dir() / "jobs" / str(ctx.job.pk)
    work.mkdir(parents=True, exist_ok=True)
    final = mode == "final"
    ctx.live(phase="checking", provider="remotion", device="cpu", model=f"ScenePlan · {kit['key']}", shot=shot.pk)
    measure = qa_browser.make_measure(ctx, st, kit=kit, size=size, work=work, shot=shot, media_dir=qa_browser.media_dir_for(plan.pk), per_scene=2 if final else 1)
    plan = shots.quality_check(plan, ep, measure=measure, rounds=3 if final else 1, on_round=lambda rec: ctx.check())
    ctx.progress(0.3, "rendering")
    out = work / f"shot{shot.pk}.mp4"
    spec = {"composition": "ScenePlan", "props": {"kit": kit, "size": size, **shots.render_props(plan, shot, ep)}, "out": str(out), "crf": 18 if final else 28, "scale": scale}
    ctx.live(phase="rendering", provider="remotion", device="cpu", model=f"ScenePlan · {kit['key']}", shot=shot.pk)
    d = rh.run_renderer(ctx, st, spec, work=work, base=0.3)
    if not out.is_file():
        raise ProviderError("Remotion render failed: no output file", retryable=False, code="remotion_render_failed", fa="ساخت کلیپ موشن‌گرافیک کامل نشد؛ جزئیات فنی در گزارش کار است.")
    h = shots.clip_hash(plan, shot, ep, mode)
    rel = f"episodes/{ep.pk}/clips/motion-shot{shot.pk}-{h[:8]}.mp4"
    qa_rep = plan.qa or {}
    asset = asset_storage.register(out, rel, kind="video", role="shot_clip", page=shots.page_of(ep), episode=ep, shot=shot, input_hash=h,
                                   provenance={"engine": "remotion", "technique": shots.TECHNIQUE, "composition": "ScenePlan", "plan_id": plan.pk, "plan_rev": plan.cursor,
                                               "plan_origin": plan.origin, "scenes": [s["type"] for s in plan.spec["scenes"]], "style": kit["key"], "size": size, "scale": scale,
                                               "mode": mode, "job_id": ctx.job.pk, "device": "local", "qa": {"fixed": qa_rep.get("fixed", 0), "remaining": len(qa_rep.get("remaining") or []),
                                                                                                             "geometry": bool(qa_rep.get("geometry"))}})
    try:
        from instai.production.models import ShotRender

        ShotRender.objects.create(shot=shot, technique=shots.TECHNIQUE, status="done", asset=asset, device="local", seconds=round(time.time() - t0, 2),
                                  params={"engine": "remotion", "plan_id": plan.pk, "scenes": len(plan.spec["scenes"]), "mode": mode})
    except Exception:  # noqa: BLE001 - the history row is a convenience
        log.exception("ShotRender row of motion shot %s", shot.pk)
    shutil.rmtree(work, ignore_errors=True)
    ctx.progress(1.0, "done")
    return {"asset_id": asset.pk, "url": asset.url, "kind": "mp4", "composition": "ScenePlan", "shot_id": shot.pk, "plan_id": plan.pk, "style": kit["key"], "size": size,
            "width": d.get("width"), "height": d.get("height"), "fps": d.get("fps"), "frames": d.get("frames"), "seconds": round(time.time() - t0, 1), "bytes": asset.size_bytes,
            "qa_fixed": qa_rep.get("fixed", 0), "qa_remaining": len(qa_rep.get("remaining") or [])}


@handler("motion.plan", resource=_plan_resource, timeout=3600)
def plan_job(ctx) -> dict:
    """Write (or rewrite) the plan of a shot: payload {shot_id, force?} - or a stand-alone plan from a narration: {narration, seconds, style, theme, size, lang}."""
    from instai.story.models import Shot

    p = ctx.payload
    if p.get("shot_id"):
        shot = Shot.objects.select_related("scene__episode__series__page").get(pk=p["shot_id"])
        plan = shots.ensure_plan(shot, shot.scene.episode, ctx=ctx, force=bool(p.get("force")))
        return {"plan_id": plan.pk, "origin": plan.origin, "scenes": len(plan.spec["scenes"]), "seconds": plan.spec.get("total_s")}
    from instai.remotion import kit as kitmod

    from . import role, specs

    kit = kitmod.style_kit(p.get("style") or None, p.get("theme") or None)
    spec, info = role.write_plan(str(p.get("narration") or ""), seconds=float(p.get("seconds") or 8), kit=kit, style=kit["key"], theme=p.get("theme") or "",
                                 size=p.get("size") or "vertical", lang=p.get("lang") or "fa", series=p.get("series") or {})
    plan = plans.create(spec, origin=info["origin"], source=info["origin"] if info["origin"] in plans.SOURCES else "ai", label="Version 1: " + info["origin"])
    return {"plan_id": plan.pk, "origin": info["origin"], "scenes": len(spec["scenes"]), "seconds": spec.get("total_s"), "specs": specs.SCHEMA_VERSION}


@handler("motion.qa", resource="cpu", timeout=2 * 3600)
def qa_job(ctx) -> dict:
    """The rule checks and the geometry of real frames (when Remotion is ready) of a plan, with the automatic fixes: payload {plan_id}."""
    from instai.jobs.handlers import remotion as rh
    from instai.remotion import kit as kitmod
    from instai.remotion import toolchain

    plan = MotionPlan.objects.select_related("shot__scene__episode__series__page").get(pk=ctx.payload["plan_id"])
    spec = plan.spec
    kit = kitmod.style_kit(spec.get("style") or None, spec.get("theme") or None)
    measure = None
    st = toolchain.status()
    if st["ready"]:
        work = toolchain.work_dir() / "jobs" / str(ctx.job.pk)
        work.mkdir(parents=True, exist_ok=True)
        measure = qa_browser.make_measure(ctx, st, kit=kit, size=spec.get("size", "vertical"), work=work, shot=plan.shot, media_dir=qa_browser.media_dir_for(plan.pk))
    else:
        rh.kick_setup()                          # the geometry needs Remotion: it starts by itself; the rule checks do not wait for it
    ep = plan.shot.scene.episode if plan.shot_id else None
    plan = shots.quality_check(plan, ep, measure=measure, kit=kit, on_round=lambda rec: ctx.check())
    rep = plan.qa or {}
    return {"plan_id": plan.pk, "fixed": rep.get("fixed", 0), "remaining": len(rep.get("remaining") or []), "geometry": bool(rep.get("geometry")), "ok": bool(rep.get("ok"))}


@handler("motion.critique", resource="gpu", timeout=4 * 3600)
def critique_job(ctx) -> dict:
    """The vision model's review of key frames, at most 3 rounds of «look => patch => look again»: payload {plan_id}. Ollama off => the job WAITS (ollama_down)."""
    from instai.jobs.handlers import remotion as rh
    from instai.remotion import kit as kitmod

    plan = MotionPlan.objects.select_related("shot__scene__episode__series__page").get(pk=ctx.payload["plan_id"])
    from instai.remotion import toolchain

    spec = plan.spec
    kit = kitmod.style_kit(spec.get("style") or None, spec.get("theme") or None)
    st = rh.require_toolchain()                                      # frames need Remotion: wait for it (it starts by itself)
    work = toolchain.work_dir() / "jobs" / str(ctx.job.pk)
    work.mkdir(parents=True, exist_ok=True)
    measure = qa_browser.make_measure(ctx, st, kit=kit, size=spec.get("size", "vertical"), work=work, shot=plan.shot, media_dir=qa_browser.media_dir_for(plan.pk, "critique"),
                                      prefix="c", frames_fn=lambda s: critique.pick_frames(s, kit=kit))
    try:
        state = critique.run(plan, measure=measure, kit=kit, allowed_sources=plans.verified_sources(plan))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return {"plan_id": plan.pk, "state": state.get("state"), "rounds": len(state.get("rounds") or [])}
