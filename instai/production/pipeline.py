"""Episode production pipeline: what is missing -> which job runs next. Idempotent and resumable.

State is derived from assets, not remembered: every asset stores the hash of the inputs that made it, so
  * editing one shot makes only that shot's keyframe/narration/clip stale (partial regeneration);
  * a failed video job never touches script or storyboard;
  * approved assets are always reused.
`advance()` is safe to call any number of times (also concurrently): it enqueues what is missing, or moves the state forward.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.models import Job
from instai.pages import formats
from instai.providers.base import ProviderError
from instai.render import assemble as asm
from instai.render import ffmpeg
from instai.render.placeholders import make_placeholder
from instai.story import costs, services, states
from instai.story.models import Episode, Shot

log = logging.getLogger("instai.pipeline")
PREVIEW, FINAL = "preview", "final"
KF_SIZE = {PREVIEW: (448, 800), FINAL: (832, 1472)}
STEP_KINDS = ("prod.keyframes", "prod.tts", "prod.clips", "prod.assemble")


def _h(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


# ------------------------------------------------------------------ settings / hashes

def page_of(ep: Episode):
    return ep.series.page


def render_options(ep: Episode, mode: str) -> asm.RenderOptions:
    page = page_of(ep)
    prod, vis, aud = page.profile("production"), page.profile("visual"), page.profile("audio")
    return asm.RenderOptions.for_mode(mode, final_height=prod["final_height"], preview_height=prod["preview_height"], fps=prod["fps"],
                                      subtitle_style=vis["subtitle"], target_lufs=float(aud["target_lufs"]))


def style_prompt(ep: Episode) -> str:
    vis = page_of(ep).profile("visual")
    base = next((s["prompt"] for s in formats.STYLES if s["key"] == vis["style_key"]), "")
    return ", ".join(x for x in (base, vis.get("style_notes", "")) if x)


def image_engine() -> str:
    return str(settings_store.effective("image_engine") or "auto")


def keyframe_hash(shot: Shot, ep: Episode, mode: str) -> str:
    w, h = KF_SIZE[mode]
    return _h("kf", shot.image_prompt, shot.negative_prompt, shot.seed, w, h, style_prompt(ep), image_engine(),
              settings_store.effective("image_workflow"), mode if image_engine() != "placeholder" else "")


def narration_hash(shot: Shot, ep: Episode) -> str:
    voice = voice_for(shot, ep)
    return _h("tts", shot.narration, voice, ep.series.page.language)


def voice_for(shot: Shot, ep: Episode) -> dict:
    """Voice of a shot: the speaking character's voice, else the page's narration voice."""
    page = page_of(ep)
    aud = page.profile("audio")
    char = page.characters.filter(name=shot.speaker).first() if shot.speaker else None
    cv = (char.voice if char else None) or {}
    return {"engine": cv.get("engine") or aud["narration_engine"] or "auto", "voice": cv.get("voice_id") or aud["narration_voice"],
            "reference": cv.get("reference") or ""}


def current(shot: Shot, role: str) -> Asset | None:
    return Asset.objects.filter(shot=shot, role=role, is_current=True).order_by("-version").first()


def asset_ok(a: Asset | None, want_hash: str | None = None) -> bool:
    if a is None or not asset_storage.storage.exists(a.path):
        return False
    return a.approved or want_hash is None or a.input_hash == want_hash


def missing_keyframes(ep: Episode, mode: str) -> list[Shot]:
    return [s for s in services.all_shots(ep) if not asset_ok(current(s, "keyframe"), keyframe_hash(s, ep, mode))]


def missing_narration(ep: Episode) -> list[Shot]:
    return [s for s in services.all_shots(ep) if s.narration.strip() and not asset_ok(current(s, "narration"), narration_hash(s, ep))]


def wan_shots(ep: Episode) -> list[Shot]:
    return [s for s in services.all_shots(ep) if s.technique == "wan_i2v"]


def clip_hash(shot: Shot, kf: Asset) -> str:
    return _h("wan", kf.sha256, shot.image_prompt, shot.description, shot.duration_sec, shot.seed)


def missing_clips(ep: Episode) -> list[Shot]:
    out = []
    for s in wan_shots(ep):
        kf = current(s, "keyframe")
        if kf and not asset_ok(current(s, "shot_clip"), clip_hash(s, kf)):
            out.append(s)
    return out


# ------------------------------------------------------------------ orchestration

def _enqueue_step(ep: Episode, kind: str, mode: str, digest: str, title: str, estimated: float | None = None) -> Job:
    key = f"ep{ep.pk}:{kind}:{mode}:{digest}"
    job = queue.enqueue(kind, {"episode_id": ep.pk, "mode": mode}, episode=ep, page=page_of(ep), idempotency_key=key, title=title,
                        estimated_sec=estimated)
    if job.status == Job.SUCCEEDED:  # same inputs, but something is still missing (files removed?): run it again
        job = queue.requeue(job, reset_attempts=True)
    return job


def start(ep: Episode, mode: str, actor: str = "user") -> list[Job]:
    """User pressed "produce": move the episode into asset_generation (from any editing state) and advance."""
    if mode not in (PREVIEW, FINAL):
        raise DomainError("validation_error", "حالت باید preview یا final باشد.", http_status=400)
    ep.refresh_from_db()
    if ep.state in (states.APPROVED, states.SCHEDULED, states.PUBLISHED):
        raise DomainError("conflict", "قسمتِ تأییدشده را ابتدا به «آماده‌ی تأیید» برگردانید تا دوباره ساخته شود.")
    if ep.state in (states.DRAFT, states.PLANNED, states.SCRIPTING, states.SCRIPT_REVIEW):
        raise DomainError("not_ready", "ابتدا فیلم‌نامه و استوری‌بورد باید آماده شود.")
    if ep.state == states.FAILED:
        services.transition(ep, ep.failed_state or states.ASSET_GENERATION, reason="retry", actor=actor)
        ep.refresh_from_db()
    if ep.state != states.ASSET_GENERATION:
        services.transition(ep, states.ASSET_GENERATION, reason=f"produce ({mode})", actor=actor)
    Shot.objects.filter(scene__episode=ep).update(last_error="")
    return advance(ep, mode)


def advance(ep: Episode, mode: str) -> list[Job]:
    """Enqueue what is missing or move the state forward. Returns the jobs enqueued/awaited."""
    ep.refresh_from_db()
    jobs: list[Job] = []
    if ep.state == states.ASSET_GENERATION:
        kf, tts = missing_keyframes(ep, mode), missing_narration(ep)
        if kf:
            sec = sum(costs.shot_estimate(s.technique, s.duration_sec, mode)["gpu_seconds"] for s in kf)
            jobs.append(_enqueue_step(ep, "prod.keyframes", mode, _h([(s.pk, keyframe_hash(s, ep, mode)) for s in kf]),
                                      f"تصاویر کلیدی ({len(kf)} شات)", sec))
        if tts:
            jobs.append(_enqueue_step(ep, "prod.tts", mode, _h([(s.pk, narration_hash(s, ep)) for s in tts]), f"گفتار ({len(tts)} شات)"))
        if jobs:
            return jobs
        pending = Job.objects.filter(episode=ep, kind__in=("prod.keyframes", "prod.tts"), status__in=(Job.QUEUED, Job.RUNNING))
        if pending.exists():
            return list(pending)
        try:
            if mode == FINAL and wan_shots(ep) and missing_clips(ep):
                services.transition(ep, states.ANIMATION, reason="video shots", actor="system")
                return [_enqueue_step(ep, "prod.clips", mode, _h([s.pk for s in missing_clips(ep)]), "ویدئوی شات‌ها (Wan)",
                                      len(missing_clips(ep)) * costs.table()[0]["video_5s"])]
            services.transition(ep, states.ASSEMBLY, reason="assets ready", actor="system")
        except DomainError:
            return []  # another worker moved it first
        return advance(ep, mode)
    if ep.state == states.ANIMATION:
        pending = Job.objects.filter(episode=ep, kind="prod.clips", status__in=(Job.QUEUED, Job.RUNNING))
        if pending.exists():
            return list(pending)
        try:
            services.transition(ep, states.ASSEMBLY, reason="clips done", actor="system")
        except DomainError:
            return []
        return advance(ep, mode)
    if ep.state == states.ASSEMBLY:
        return [_enqueue_step(ep, "prod.assemble", mode, _h(timeline_hash(ep, mode)), "مونتاژ ویدئو")]
    return []


def timeline_hash(ep: Episode, mode: str) -> str:
    parts = []
    for s in services.all_shots(ep):
        kf, nar, clip = current(s, "keyframe"), current(s, "narration"), current(s, "shot_clip")
        parts.append([s.pk, kf.sha256 if kf else "", nar.sha256 if nar else "", clip.sha256 if clip else "", s.camera, s.duration_sec,
                      s.transition, s.narration, s.technique])
    return _h(mode, parts, page_of(ep).profile("visual")["subtitle"], page_of(ep).profile("audio")["target_lufs"])


# ------------------------------------------------------------------ steps (called by job handlers)

def media_dir(ep: Episode) -> Path:
    d = Path(settings.MEDIA_ROOT) / "episodes" / str(ep.pk)
    d.mkdir(parents=True, exist_ok=True)
    return d


def step_keyframes(ctx, ep: Episode, mode: str) -> dict:
    shots = missing_keyframes(ep, mode)
    engine = image_engine()
    if not shots:
        return {"generated": 0}
    w, h = KF_SIZE[mode]
    done = 0
    client = spec = lease_cm = None
    if engine != "placeholder":
        client, spec = _comfy_ready()
    try:
        if client:
            from instai.gpu.arbiter import ARBITER

            lease_cm = ARBITER.hold(ctx, "comfy")
            lease_cm.__enter__()
        for i, shot in enumerate(shots):
            ctx.check()
            ctx.progress(i / len(shots), f"keyframe {i + 1}/{len(shots)}")
            if shot.seed is None:
                shot.seed = int(_h("seed", ep.pk, shot.pk), 16) % (2 ** 31)
                shot.save(update_fields=["seed"])
            hsh = keyframe_hash(shot, ep, mode)
            rel = f"episodes/{ep.pk}/keyframes/shot{shot.pk}-{hsh[:8]}.png"
            if client and spec:
                prompt = ", ".join(x for x in (shot.image_prompt, style_prompt(ep)) if x)
                inputs = {"prompt": prompt, "negative_prompt": shot.negative_prompt, "width": w, "height": h, "seed": shot.seed,
                          "steps": 12 if mode == PREVIEW else 24}
                graph = spec.build(inputs)
                _, files = client.run(graph, timeout=1800, on_tick=lambda s: ctx.progress(i / len(shots), f"keyframe {i + 1}/{len(shots)} ({int(s)}s)"),
                                      cancel=lambda: _cancelled(ctx))
                if not files:
                    raise ProviderError("ComfyUI returned no image", retryable=True)
                tmp = Path(tempfile.mkdtemp(prefix="kf-", dir=settings.MEDIA_ROOT)) / "kf.png"
                client.download(files[0], tmp)
                prov = {**spec.provenance(inputs), "provider": "comfyui", "job_id": ctx.job.pk, "engine": "comfyui"}
            else:
                tmp = Path(tempfile.mkdtemp(prefix="kf-", dir=settings.MEDIA_ROOT)) / "kf.png"
                make_placeholder(tmp, w, h, f"shot {shot.scene.index}.{shot.index}", seed=f"{ep.pk}-{shot.pk}")
                prov = {"provider": "placeholder", "engine": "placeholder", "prompt": shot.image_prompt, "seed": shot.seed, "job_id": ctx.job.pk,
                        "note": "demo mode: generated placeholder, not an AI image"}
            asset_storage.register(tmp, rel, kind="image", role="keyframe", page=page_of(ep), episode=ep, shot=shot, input_hash=hsh, provenance=prov)
            _cleanup(tmp.parent)
            Shot.objects.filter(pk=shot.pk).update(status="done", last_error="")
            done += 1
    finally:
        if lease_cm:
            lease_cm.__exit__(None, None, None)
    return {"generated": done}


def _cancelled(ctx) -> bool:
    return queue.is_cancel_requested(ctx.job.pk)


def _cleanup(d: Path) -> None:
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def _comfy_ready(workflow: str | None = None):
    from instai.core import hardware, runtime
    from instai.providers.comfy.client import ComfyClient
    from instai.providers.comfy.workflows import get_workflow, workflow_availability

    wid = workflow or str(settings_store.effective("image_workflow"))
    info = hardware.comfy_object_info(runtime.comfyui_url(), force=True)
    if info is None:
        raise ProviderError("ComfyUI در دسترس نیست. آن را اجرا کنید (یا در تنظیمات حالت آزمایشی را روشن کنید).", retryable=False, code="not_ready")
    av = next((w for w in workflow_availability(info) if w["id"] == wid), None)
    if not av or not av["available"]:
        miss = (av or {}).get("missing_models", []) + (av or {}).get("missing_nodes", [])
        raise ProviderError(f"گردش‌کار {wid} روی این ComfyUI آماده نیست؛ موارد ناموجود: {', '.join(miss[:4])}", retryable=False, code="not_ready")
    return ComfyClient(runtime.comfyui_url()), get_workflow(wid)


def step_tts(ctx, ep: Episode, mode: str) -> dict:
    from instai.providers.tts import get_tts

    shots = missing_narration(ep)
    done = 0
    lang = ep.series.page.language
    for i, shot in enumerate(shots):
        ctx.check()
        ctx.progress(i / max(1, len(shots)), f"narration {i + 1}/{len(shots)}")
        voice = voice_for(shot, ep)
        tts = get_tts(voice["engine"] if voice["engine"] != "auto" else None)
        hsh = narration_hash(shot, ep)
        tmp = Path(tempfile.mkdtemp(prefix="tts-", dir=settings.MEDIA_ROOT)) / "n.wav"
        if tts.resource == "gpu":
            from instai.gpu.arbiter import ARBITER

            with ARBITER.hold(ctx, "tts"):
                res = tts.synthesize(shot.narration, tmp, voice=voice["voice"] or None, language=lang, seed=shot.seed, reference=voice["reference"] or None)
        else:
            res = tts.synthesize(shot.narration, tmp, voice=voice["voice"] or None, language=lang, seed=shot.seed, reference=voice["reference"] or None)
        rel = f"episodes/{ep.pk}/audio/shot{shot.pk}-{hsh[:8]}.wav"
        asset_storage.register(tmp, rel, kind="audio", role="narration", page=page_of(ep), episode=ep, shot=shot, input_hash=hsh,
                               provenance={"engine": res.engine, "voice": res.voice, "provider": res.engine, "job_id": ctx.job.pk,
                                           "render_seconds": round(res.render_seconds, 2), "text": shot.narration[:200]})
        _cleanup(tmp.parent)
        done += 1
    return {"generated": done}


def step_clips(ctx, ep: Episode, mode: str) -> dict:
    """Wan 2.2 hero shots from the approved/current keyframe. Unavailable ComfyUI/workflow is not fatal: those shots keep Ken Burns."""
    shots = missing_clips(ep)
    if not shots:
        return {"generated": 0}
    try:
        client, spec = _comfy_ready("wan22_i2v_a14b_fp8")
    except ProviderError as e:
        ctx.log(f"video clips skipped, Ken Burns is used instead: {e}", "warning")
        return {"generated": 0, "skipped": len(shots), "reason": str(e)}
    from instai.gpu.arbiter import ARBITER

    done = 0
    with ARBITER.hold(ctx, "comfy"):
        for i, shot in enumerate(shots):
            ctx.check()
            kf = current(shot, "keyframe")
            name = client.upload_image(asset_storage.storage.path_for(kf.path), f"instai-shot{shot.pk}.png")
            frames = max(9, min(81, int(round(shot.duration_sec * 16)) + 1))
            inputs = {"prompt": shot.image_prompt or shot.description, "image": name, "width": 480, "height": 832, "length": frames,
                      "seed": shot.seed or 1, "negative_prompt": shot.negative_prompt}
            graph = spec.build(inputs)
            _, files = client.run(graph, timeout=3600, on_tick=lambda s: ctx.progress(i / len(shots), f"Wan {i + 1}/{len(shots)} ({int(s)}s)"),
                                  cancel=lambda: _cancelled(ctx))
            vids = [f for f in files if f.kind in ("video", "images", "gifs") and f.filename.lower().endswith((".mp4", ".webm", ".mkv", ".mov"))]
            if not vids:
                raise ProviderError("ComfyUI returned no video file", retryable=True)
            tmp = Path(tempfile.mkdtemp(prefix="clip-", dir=settings.MEDIA_ROOT)) / vids[0].filename
            client.download(vids[0], tmp)
            rel = f"episodes/{ep.pk}/clips/shot{shot.pk}-{clip_hash(shot, kf)[:8]}{tmp.suffix}"
            asset_storage.register(tmp, rel, kind="video", role="shot_clip", page=page_of(ep), episode=ep, shot=shot, input_hash=clip_hash(shot, kf),
                                   provenance={**spec.provenance(inputs), "provider": "comfyui", "job_id": ctx.job.pk})
            _cleanup(tmp.parent)
            done += 1
    return {"generated": done}


def shot_specs(ep: Episode, mode: str) -> tuple[list[asm.ShotSpec], list[str]]:
    """ShotSpecs from current assets + notes about fallbacks (shown in QC and the job log)."""
    specs, notes = [], []
    shots = services.all_shots(ep)
    for i, s in enumerate(shots):
        kf, nar, clip = current(s, "keyframe"), current(s, "narration"), current(s, "shot_clip")
        layers = None
        if s.technique == "parallax_25d":
            notes.append(f"shot {s.scene.index}.{s.index}: no cut-out layers yet (Phase 3), Ken Burns used instead of parallax")
        if s.technique not in costs.IMPLEMENTED:
            notes.append(f"shot {s.scene.index}.{s.index}: technique {s.technique} not implemented yet, Ken Burns used")
        if s.technique == "wan_i2v" and not clip and mode == FINAL:
            notes.append(f"shot {s.scene.index}.{s.index}: no Wan clip available, Ken Burns used")
        last = i == len(shots) - 1
        specs.append(asm.ShotSpec(
            key=str(s.pk), duration=s.duration_sec, image=str(asset_storage.storage.path_for(kf.path)) if kf else None,
            video=str(asset_storage.storage.path_for(clip.path)) if (clip and mode == FINAL) else None, layers=layers, camera=s.camera or {},
            technique=s.technique, transition="cut" if last else (s.transition or "cut"),
            audio=str(asset_storage.storage.path_for(nar.path)) if nar else None, audio_duration=(nar.duration_sec or 0.0) if nar else 0.0,
            subtitle=s.narration))
    return specs, notes


def step_assemble(ctx, ep: Episode, mode: str) -> dict:
    specs, notes = shot_specs(ep, mode)
    if not specs:
        raise DomainError("not_ready", "قسمت هیچ شاتی ندارد.")
    for n in notes:
        ctx.log(n, "warning")
    if any(s.image is None and s.video is None for s in specs):
        raise ProviderError("some shots have no image yet; run the production step again", retryable=False, code="not_ready")
    opts = render_options(ep, mode)
    work = Path(tempfile.mkdtemp(prefix="asm-", dir=settings.MEDIA_ROOT))
    try:
        clips: list[Path] = []
        shots = services.all_shots(ep)
        for i, (spec, shot) in enumerate(zip(specs, shots)):
            ctx.check()
            ctx.progress(0.05 + 0.55 * i / len(specs), f"shot clip {i + 1}/{len(specs)}")
            dur = asm.shot_duration(spec)
            chash = _h("clip", spec.image and Path(spec.image).name, spec.video and Path(spec.video).name, spec.camera, round(dur, 3),
                       opts.width, opts.height, opts.fps, mode)
            cached = Asset.objects.filter(shot=shot, role="render_clip", is_current=True, input_hash=chash).first()
            if cached and asset_storage.storage.exists(cached.path):
                clips.append(asset_storage.storage.path_for(cached.path))
                continue
            out = work / f"clip{i:03d}.mp4"
            asm.render_shot_clip(spec, opts, out, duration=dur, ctx=ctx)
            rel = f"episodes/{ep.pk}/clips/render-shot{shot.pk}-{chash[:8]}.mp4"
            a = asset_storage.register(out, rel, kind="video", role="render_clip", page=page_of(ep), episode=ep, shot=shot, input_hash=chash,
                                       provenance={"mode": mode, "technique": spec.technique, "camera": spec.camera, "job_id": ctx.job.pk})
            clips.append(asset_storage.storage.path_for(a.path))
        ctx.progress(0.6, "joining, mixing, subtitles")
        out = work / "episode.mp4"
        info = asm.assemble(specs, clips, opts, out, work / "work", ctx=ctx, on_progress=lambda f: ctx.progress(0.6 + 0.35 * f, "encoding"))
        stamp = _h(ctx.job.pk, mode)[:6]
        rel = f"episodes/{ep.pk}/renders/{mode}-{stamp}.mp4"
        thash = timeline_hash(ep, mode)
        video = asset_storage.register(out, rel, kind="video", role=mode, page=page_of(ep), episode=ep, input_hash=thash, loudness=True,
                                       provenance={"mode": mode, "width": opts.width, "height": opts.height, "fps": opts.fps, "job_id": ctx.job.pk,
                                                   "shots": len(specs), "techniques": sorted({s.technique for s in specs}), "notes": notes,
                                                   "subtitle_cues": info["cues"], "workflow": "ffmpeg-assembly@1", "expected_duration": info["duration"]})
        cover_tmp = work / "cover.png"
        asm.extract_cover(asset_storage.storage.path_for(video.path), cover_tmp, at=min(1.0, info["duration"] / 2))
        asset_storage.register(cover_tmp, f"episodes/{ep.pk}/renders/{mode}-{stamp}-cover.png", kind="image", role="cover", page=page_of(ep), episode=ep,
                               provenance={"from": video.pk})
        ass = work / "work" / "sub.ass"
        if ass.exists():
            asset_storage.register(ass, f"episodes/{ep.pk}/renders/{mode}-{stamp}.ass", kind="subtitle", role="subtitles", page=page_of(ep),
                                   episode=ep, probe=False, provenance={"from": video.pk})
    finally:
        _cleanup(work)
    return {"asset_id": video.pk, "duration": info["duration"], "notes": notes, "mode": mode}


# ------------------------------------------------------------------ quality control

def run_qc(ep: Episode, video: Asset) -> dict:
    from instai.render import qc

    page = page_of(ep)
    report = qc.technical(asset_storage.storage.path_for(video.path), expected_duration=_expected_duration(ep, video),
                          width=video.width, height=video.height, target_lufs=float(page.profile("audio")["target_lufs"]),
                          loudness=video.loudness_lufs)
    checks = report["checks"]
    sc = ep.script_checks or {}
    checks.append({"name": "script", "level": "ok" if sc.get("ok", True) else "warn", "value": sc.get("warnings", []),
                   "message": "فیلم‌نامه: کامل بودن، طول و سرعت خواندن" if sc.get("ok", True) else "هشدار فیلم‌نامه: " + "، ".join(sc.get("warnings", []))})
    chars = {c.name for c in page.characters.all()} | {"", "راوی", "Narrator", "narrator"}
    unknown = sorted({s.speaker for s in services.all_shots(ep) if s.speaker not in chars})
    checks.append({"name": "continuity", "level": "warn" if unknown else "ok", "value": unknown,
                   "message": "گوینده‌هایی که در لیست شخصیت‌ها نیستند: " + "، ".join(unknown) if unknown else "هماهنگی با شخصیت‌ها و حافظه‌ی داستان"})
    mem = services.memory_digest(ep.series, before_episode=ep.number)
    checks.append({"name": "open_threads", "level": "info", "value": len(mem["open_threads"]),
                   "message": f"{len(mem['open_threads'])} رشته‌ی باز داستان از قسمت‌های قبل"})
    if ep.series.page.format == formats.EXPLAINER:
        nums = services.unsupported_numbers(ep)
        unsup = (ep.research or {}).get("unsupported_count", 0) if ep.research else None
        checks.append({"name": "claims", "level": "warn" if (nums or unsup or not ep.research) else "ok", "value": {"numbers": nums, "unsupported": unsup},
                       "message": ("ادعای بدون منبع / عددِ بی‌منبع: " + "، ".join(nums)) if (nums or unsup) else (
                           "ادعاها منبع دارند" if ep.research else "پژوهش و منبع برای این قسمت ثبت نشده است")})
    report["ok"] = not any(c["level"] == "fail" for c in checks)
    report["warnings"] = sum(1 for c in checks if c["level"] == "warn")
    return report


def _expected_duration(ep: Episode, video: Asset) -> float:
    prov = video.provenance or {}
    return float(prov.get("expected_duration") or video.duration_sec or 0)
