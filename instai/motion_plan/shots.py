"""The motion-graphics SHOTS of an episode: their plans, their render jobs and their clips.

A shot with technique `motion_graphics` has no keyframe to move: its clip is DRAWN by Remotion from a scene plan written from the shot's narration
(role.write_plan: a text model when one answers, else the deterministic plan of fallback.py). The clip is registered as the shot's `shot_clip`, exactly where a Wan
clip would be, and the assembly uses it in preview and final mode (render_shot_clip fits its length to the shot).

  missing(ep, mode)  - the shots whose clip does not exist or is stale (the hash covers the plan, the look, the size, the length and the renderer)
  enqueue(ep, mode)  - one `remotion.render` job per missing shot (pipeline.advance calls this once the narration exists: the clip is as long as the speech)
  render_shot(ctx)   - the body of such a job (called by instai/jobs/handlers/remotion.py)
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
from pathlib import Path

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.jobs import queue
from instai.jobs.models import Job
from instai.styles import library as style_library

from . import fallback, motionlib, plans, qa, role, specs, timeline
from .models import MotionPlan, MotionPlanRev

log = logging.getLogger("instai.motion_plan")
TECHNIQUE = "motion_graphics"
RENDERER_REV = "1"        # bump when the components change what a plan looks like: every old clip becomes stale
MAX_ASSET_SIDE = 1280


def _h(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def motion_shots(ep) -> list:
    from instai.story import services

    return [s for s in services.all_shots(ep) if s.technique == TECHNIQUE]


def page_of(ep):
    return ep.series.page


def look_keys(ep) -> tuple[str, str]:
    lk = style_library.look_of(page_of(ep), ep.series)
    return lk.get("style_key", ""), lk.get("theme_key", "")


def kit_of_episode(ep) -> dict:
    from instai.remotion import kit as kitmod

    style, theme = look_keys(ep)
    return kitmod.style_kit(style or None, theme or None)


def render_size(ep) -> str:
    """The size the assembly renders in (it follows RenderOptions: today always 9:16)."""
    from instai.production import pipeline

    o = pipeline.render_options(ep, pipeline.FINAL)
    if o.width > o.height * 1.2:
        return "landscape"
    if abs(o.width - o.height) < o.height * 0.1:
        return "square"
    return "vertical"


def render_scale(ep, mode: str) -> float:
    """The renderer's scale of the composition (1 = 1080 x 1920): the preview is drawn small, the final at the page's final height. Remotion needs the scaled width and height to be
    whole numbers (and h264 even ones): the scale is a multiple of 1/120 for which that holds in every size (a rounded 0.333 once made 638.361 and the render failed)."""
    from instai.production import pipeline

    o = pipeline.render_options(ep, mode)
    target = max(o.width, o.height) / 1920.0
    sizes = list(motionlib.SIZES.values())
    for cand in (round(target * 120) / 120, round(target * 4) / 4, 0.5):
        if cand >= 0.25 and all(float(w * cand).is_integer() and float(h * cand).is_integer() and int(w * cand) % 2 == 0 and int(h * cand) % 2 == 0 for w, h in sizes):
            return min(cand, 2.0)
    return 0.5


def narration_of(shot):
    return (shot.narration or "").strip()


def target_seconds(shot, ep) -> float:
    """The clip's length: the assembly's own rule (narration drives the length)."""
    from instai.production import pipeline
    from instai.render import assemble as asm

    nar = pipeline.current(shot, "narration")
    spec = asm.ShotSpec(key=str(shot.pk), duration=shot.duration_sec, audio="x" if nar else None, audio_duration=(nar.duration_sec or 0.0) if nar else 0.0)
    return round(max(1.0, asm.shot_duration(spec)), 2)


def series_context(ep, shot=None) -> dict:
    chars = []
    try:
        chars = [c.name for c in page_of(ep).characters.all()][:8]
    except Exception:  # noqa: BLE001
        pass
    return {"title": ep.series.title[:80], "episode": int(ep.number or 0), "episode_title": (ep.title or "")[:140], "channel": (page_of(ep).name or "")[:80], "characters": chars}


def verified_sources(ep) -> list:
    """[{title, extract}] of the episode's VERIFIED sources (the only thing that lets a number on screen drop the «example» label)."""
    out = []
    try:
        for s in ep.sources.all():
            if s.verified:
                out.append({"title": s.title, "extract": s.extract or ""})
    except Exception:  # noqa: BLE001
        pass
    return out


def inputs_hash(shot, ep, seconds: float) -> str:
    """What a generated plan depends on; when it changes an UNEDITED generated plan is written again."""
    style, theme = look_keys(ep)
    ser = series_context(ep, shot)
    return _h("plan", narration_of(shot), round(seconds, 1), style, theme, render_size(ep), page_of(ep).language, ser["title"], ser["episode"], ser["episode_title"])


def latest_plan(shot) -> MotionPlan | None:
    return MotionPlan.objects.filter(shot=shot).order_by("-id").first()


def edited_by_owner(plan: MotionPlan) -> bool:
    return MotionPlanRev.objects.filter(plan=plan, source__in=("user", "chat", "patch", "import")).exists()


def ensure_plan(shot, ep, *, ctx=None, provider=None, force: bool = False) -> MotionPlan:
    """The plan of this shot: made when missing, written again when its inputs changed and the owner never edited it (or when `force`). The owner's own
    edits are never thrown away: a stale edited plan stays, the clip is fitted to the shot by the assembly."""
    seconds = target_seconds(shot, ep)
    ih = inputs_hash(shot, ep, seconds)
    plan = latest_plan(shot)
    if plan is not None and not force and (plan.source_hash == ih or edited_by_owner(plan)):
        return plan
    kit = kit_of_episode(ep)
    style, theme = look_keys(ep)
    lang = page_of(ep).language or "fa"
    ser = series_context(ep, shot)
    srcs = verified_sources(ep)
    allowed = [s["title"] for s in srcs]
    if provider is None:
        from instai.agents import llm

        provider = llm.resolve(page_of(ep), "storyboard")
    if ctx is not None:
        ctx.live(phase="planning", shot=shot.pk)
    spec, info = role.write_plan(narration_of(shot), seconds=seconds, kit=kit, style=style, theme=theme, size=render_size(ep), lang=lang if lang in ("fa", "en") else "fa",
                                 series=ser, platform="", sources=srcs, allowed_sources=allowed, provider=provider)
    if plan is None:
        plan = plans.create(spec, shot=shot, origin=info["origin"], source=info["origin"] if info["origin"] in plans.SOURCES else "ai", label="Version 1: " + info["origin"])
    else:
        plan = plans.commit(plan, spec, label=f"rewritten: {info['origin']}", source=info["origin"])
        MotionPlan.objects.filter(pk=plan.pk).update(origin=info["origin"])
    MotionPlan.objects.filter(pk=plan.pk).update(source_hash=ih)
    plan.refresh_from_db()
    return plan


def prepare_plans(ep) -> int:
    """A first plan for every motion shot that has a narration and none yet: the deterministic one (no model, instant), so the storyboard shows it. The speech does not exist yet, so the
    plan's inputs hash differs from the one production computes: production writes an UNEDITED plan again, with the model, once the length of the speech is known. => how many were made."""
    n = 0
    kit = kit_of_episode(ep)
    style, theme = look_keys(ep)
    lang = page_of(ep).language or "fa"
    for s in motion_shots(ep):
        if not narration_of(s) or latest_plan(s) is not None:
            continue
        seconds = target_seconds(s, ep)
        spec = fallback.make_plan(narration_of(s), seconds, lang=lang if lang in ("fa", "en") else "fa", style=style, theme=theme, size=render_size(ep), series=series_context(ep, s),
                                  sources=verified_sources(ep), kit=kit, allowed_sources=[x["title"] for x in verified_sources(ep)])
        plan = plans.create(spec, shot=s, origin="fallback", source="fallback", label="Version 1: fallback")
        MotionPlan.objects.filter(pk=plan.pk).update(source_hash=inputs_hash(s, ep, seconds))
        n += 1
    return n


def clip_hash(plan: MotionPlan, shot, ep, mode: str) -> str:
    spec = {k: v for k, v in plan.spec.items() if k not in ("total_s",)}
    return _h("motion", spec, kit_of_episode(ep), render_size(ep), render_scale(ep, mode), target_seconds(shot, ep), RENDERER_REV)


def current_clip(shot) -> Asset | None:
    return Asset.objects.filter(shot=shot, role="shot_clip", is_current=True, provenance__engine="remotion").order_by("-version").first()


def missing(ep, mode: str) -> list:
    """The motion shots with no up-to-date clip. A shot whose narration is still missing waits (its clip is as long as the speech)."""
    from instai.production import pipeline

    out = []
    for s in motion_shots(ep):
        if narration_of(s) and pipeline.current(s, "narration") is None:
            continue
        plan = latest_plan(s)
        if plan is None or (plan.source_hash != inputs_hash(s, ep, target_seconds(s, ep)) and not edited_by_owner(plan)):
            out.append(s)
            continue
        c = current_clip(s)
        if c is None or not asset_storage.storage.exists(c.path) or c.input_hash != clip_hash(plan, s, ep, mode):
            out.append(s)
    return out


def enqueue(ep, mode: str) -> list:
    jobs = []
    for s in missing(ep, mode):
        plan = latest_plan(s)
        digest = _h(s.pk, narration_of(s), target_seconds(s, ep), plan.pk if plan else 0, plan.cursor if plan else 0, mode, kit_of_episode(ep)["key"])
        job = queue.enqueue("remotion.render", {"composition": "ScenePlan", "shot_id": s.pk, "episode_id": ep.pk, "mode": mode}, episode=ep, page=page_of(ep),
                            idempotency_key=f"ep{ep.pk}:motion:{s.pk}:{mode}:{digest}", title=f"motion shot {s.scene.index}.{s.index}", max_attempts=2)
        if job.status == Job.SUCCEEDED:     # the same inputs but the clip is missing (files removed?): again
            job = queue.requeue(job, reset_attempts=True)
        jobs.append(job)
    return jobs


# ───────────────────────────────────────────── assets of a plan (pictures)

def _data_uri(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_ASSET_SIDE, MAX_ASSET_SIDE))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def resolve_assets(spec: dict, shot=None) -> dict:
    """{ref: data URI} for every picture a plan names: `keyframe` = the shot's current keyframe, `asset:<id>` = an image asset of the same page. Unknown refs are left out."""
    from instai.production import pipeline

    out: dict = {}
    for ref in specs.asset_refs(spec):
        if ref.startswith("data:"):
            out[ref] = ref
            continue
        a = None
        if ref == "keyframe" and shot is not None:
            a = pipeline.current(shot, "keyframe")
        elif ref.startswith("asset:"):
            a = Asset.objects.filter(pk=int(ref.split(":", 1)[1]), kind="image").first()
        if a is not None and asset_storage.storage.exists(a.path):
            try:
                out[ref] = _data_uri(asset_storage.storage.path_for(a.path))
            except Exception:  # noqa: BLE001 - a broken picture is just not drawn
                continue
    return out


def render_props(plan: MotionPlan, shot, ep) -> dict:
    """The props of the `ScenePlan` composition for a shot: the plan + the pictures it names (inline)."""
    spec = {k: v for k, v in plan.spec.items() if k not in ("total_s",)}
    spec["assets"] = resolve_assets(spec, shot)
    return {"spec": spec}


# ───────────────────────────────────────────── the QA before the render (rule checks; the geometry check needs the renderer and is part of the render job)

def quality_check(plan: MotionPlan, ep=None, *, measure=None, kit: dict | None = None, rounds: int = 3, on_round=None) -> MotionPlan:
    """The rule checks (and, when `measure` is given, the geometry from real frames) with their automatic fixes, saved as new versions of the plan. => the plan."""
    kit = kit or (kit_of_episode(ep) if ep is not None else timeline.kit_of(plan.spec))
    allowed = plans.verified_sources(plan)
    report = qa.run_loop(plan.spec, measure=measure, kit=kit, allowed_sources=allowed, rounds=rounds, on_round=on_round)
    if report["fixed"]:
        plan = plans.commit(plan, report["spec"], label=qa.summary(report, "en")[:150], source="qa", ops=[a["ops"] for r in report["rounds"] for a in r.get("applied", [])][:12])
    slim = {k: v for k, v in report.items() if k != "spec"}
    MotionPlan.objects.filter(pk=plan.pk).update(qa=json.loads(json.dumps(slim, default=str)))
    plan.refresh_from_db()
    return plan
