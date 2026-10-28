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
import shutil
import tempfile
import time
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

from . import hero

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
              settings_store.effective("image_workflow"), mode if image_engine() != "placeholder" else "", "plate" if shot.technique == "puppet_2d" else "",
              _reference_key(shot, ep))


def _reference_key(shot: Shot, ep: Episode) -> str:
    """Changes when the character sheet used as a reference for a hero keyframe changes (so the keyframe is made again)."""
    if shot.technique not in hero.HERO_TECHNIQUES:
        return ""
    sheet, _ = hero.reference_sheet(shot, ep)
    if sheet is None:
        return "no-sheet"
    return _h(Path(sheet).name, Path(sheet).stat().st_size)


PLATE_SUFFIX = "empty background plate, no characters, no people, no text"
PLATE_NEGATIVE = "people, person, character, figure, face, text, watermark"


def narration_hash(shot: Shot, ep: Episode) -> str:
    voice = voice_for(shot, ep)
    return _h("tts", shot.narration, voice, ep.series.page.language)


def voice_for(shot: Shot, ep: Episode) -> dict:
    """Voice of a shot: VoiceCast of the speaking character (per language), else the character's older voice setting, else the page's
    narration voice (see production/voices.py)."""
    from . import voices

    page = page_of(ep)
    char = page.characters.filter(name=shot.speaker).first() if shot.speaker else None
    v = voices.resolve(char, voices.language_of(page), page)
    return {"engine": v["engine"], "voice": v["voice"], "reference": v["reference"], "speed": v["speed"], "consent_ok": v["consent_ok"]}


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
    return [s for s in services.all_shots(ep) if s.technique in hero.HERO_TECHNIQUES]


def next_keyframe(shot: Shot, ep: Episode) -> Asset | None:
    """The keyframe of the shot that follows (the end image of a first/last-frame transition)."""
    shots = services.all_shots(ep)
    for i, s in enumerate(shots):
        if s.pk == shot.pk and i + 1 < len(shots):
            return current(shots[i + 1], "keyframe")
    return None


def clip_hash(shot: Shot, kf: Asset, ep: Episode | None = None) -> str:
    end = next_keyframe(shot, ep) if (ep is not None and shot.technique == "wan_flf") else None
    model = hero.anime_model(ep.series.page) if ep is not None else ""
    return _h("wan", kf.sha256, shot.image_prompt, shot.description, shot.duration_sec, shot.seed, shot.technique, end.sha256 if end else "", model)


def missing_clips(ep: Episode) -> list[Shot]:
    out = []
    for s in wan_shots(ep):
        kf = current(s, "keyframe")
        if kf and not asset_ok(current(s, "shot_clip"), clip_hash(s, kf, ep)):
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
    """Keyframes. Placeholders (demo mode) run here on the CPU. Real images go through the GPU router: every shot is one ComfyUI task, so a
    worker PC takes shots in parallel; hero shots start from the approved character sheet (img2img / Qwen-Image-Edit) when one exists."""
    shots = missing_keyframes(ep, mode)
    engine = image_engine()
    if not shots:
        return {"generated": 0}
    w, h = KF_SIZE[mode]
    wid = str(settings_store.effective("image_workflow"))
    notes: list[str] = []
    for shot in shots:
        if shot.seed is None:
            shot.seed = int(_h("seed", ep.pk, shot.pk), 16) % (2 ** 31)
            shot.save(update_fields=["seed"])
    if engine != "placeholder":
        from instai.gpu import compute
        from instai.providers.comfy.workflows import get_workflow

        if not compute.workflow_available(wid):
            raise ProviderError("ComfyUI در دسترس نیست (یا گردش‌کار تصویر روی هیچ‌یک از رایانه‌ها آماده نیست). آن را اجرا کنید (یا در تنظیمات حالت آزمایشی را روشن کنید).",
                                retryable=False, code="not_ready")

    def make(shot: Shot) -> int:
        hsh = keyframe_hash(shot, ep, mode)
        rel = f"episodes/{ep.pk}/keyframes/shot{shot.pk}-{hsh[:8]}.png"
        tmp = Path(tempfile.mkdtemp(prefix="kf-", dir=settings.MEDIA_ROOT)) / "kf.png"
        if engine == "placeholder":
            make_placeholder(tmp, w, h, f"shot {shot.scene.index}.{shot.index}", seed=f"{ep.pk}-{shot.pk}")
            prov = {"provider": "placeholder", "engine": "placeholder", "prompt": shot.image_prompt, "seed": shot.seed, "job_id": ctx.job.pk,
                    "note": "demo mode: generated placeholder, not an AI image"}
        else:
            plate = shot.technique == "puppet_2d"      # the puppet is drawn on top: the keyframe is only the background
            prompt = ", ".join(x for x in (shot.image_prompt, style_prompt(ep), PLATE_SUFFIX if plate else "") if x)
            neg = ", ".join(x for x in (shot.negative_prompt, PLATE_NEGATIVE if plate else "") if x)
            base = {"prompt": prompt, "negative_prompt": neg, "width": w, "height": h, "seed": shot.seed, "steps": 12 if mode == PREVIEW else 24}
            use_wid, inputs, files, note = hero.keyframe_inputs(shot, ep, base, {})
            use_wid = use_wid or wid
            spec = get_workflow(use_wid)
            res = compute.run_task(ctx, "comfy.graph", {"graph": spec.build(inputs), "workflow": use_wid, "timeout": 1800, "expected": spec.expected_seconds}, inputs=files)
            try:
                pics = res.of_kind(*hero.IMAGE_SUFFIX)
                if not pics:
                    raise ProviderError("ComfyUI returned no image", retryable=True)
                shutil.move(str(pics[0]), tmp)
            finally:
                res.cleanup()
            prov = {**spec.provenance(inputs), "provider": "comfyui", "job_id": ctx.job.pk, "engine": "comfyui", "device": res.device, "reference": bool(files),
                    "note": note}
        asset_storage.register(tmp, rel, kind="image", role="keyframe", page=page_of(ep), episode=ep, shot=shot, input_hash=hsh, provenance=prov)
        _cleanup(tmp.parent)
        Shot.objects.filter(pk=shot.pk).update(status="done", last_error="")
        return 1

    if engine == "placeholder":
        done = 0
        for i, shot in enumerate(shots):
            ctx.check()
            ctx.progress(i / len(shots), f"keyframe {i + 1}/{len(shots)}")
            done += make(shot)
        return {"generated": done}
    from instai.gpu import compute

    counter = {"n": 0}

    def tracked(shot):
        r = make(shot)
        counter["n"] += 1
        ctx.progress(counter["n"] / len(shots), f"keyframe {counter['n']}/{len(shots)}")
        return r
    done = sum(compute.fan_out(ctx, shots, tracked, kind="comfy.graph", payload={"workflow": wid}))
    return {"generated": done, "notes": notes}


def _cancelled(ctx) -> bool:
    return queue.is_cancel_requested(ctx.job.pk)


def _cleanup(d: Path) -> None:
    import shutil

    shutil.rmtree(d, ignore_errors=True)


def step_tts(ctx, ep: Episode, mode: str) -> dict:
    from instai.providers.tts import get_tts

    shots = missing_narration(ep)
    done = 0
    lang = ep.series.page.language
    for i, shot in enumerate(shots):
        ctx.check()
        ctx.progress(i / max(1, len(shots)), f"narration {i + 1}/{len(shots)}")
        voice = voice_for(shot, ep)
        if not voice["consent_ok"]:
            raise ProviderError("The cloned voice of this character has no recorded consent; it will not be used.", retryable=False, code="consent_missing")
        tts = get_tts(voice["engine"] if voice["engine"] != "auto" else None)
        hsh = narration_hash(shot, ep)
        tmp = Path(tempfile.mkdtemp(prefix="tts-", dir=settings.MEDIA_ROOT)) / "n.wav"
        res = _speak(ctx, tts, shot.narration, tmp, voice, lang, shot.seed)
        rel = f"episodes/{ep.pk}/audio/shot{shot.pk}-{hsh[:8]}.wav"
        asset_storage.register(tmp, rel, kind="audio", role="narration", page=page_of(ep), episode=ep, shot=shot, input_hash=hsh,
                               provenance={"engine": res.engine, "voice": res.voice, "provider": res.engine, "job_id": ctx.job.pk, "language": lang,
                                           "speaker": shot.speaker, "render_seconds": round(res.render_seconds, 2), "text": shot.narration[:200],
                                           "licence": res.licence, "device": getattr(res, "device", "local")})
        _cleanup(tmp.parent)
        done += 1
    return {"generated": done}


def _speak(ctx, tts, text: str, out: Path, voice: dict, lang: str, seed):
    """One line of speech. MOSS (GPU) goes through the GPU router, so a worker PC can speak while this PC renders video; CPU/online engines
    (Piper, Pocket, Edge) run right here in parallel with the GPU."""
    kw = dict(voice=voice["voice"] or None, language=lang, seed=seed, reference=voice["reference"] or None)
    if tts.resource == "gpu" and tts.id == "moss":
        from instai.gpu import compute
        from instai.providers.tts import TTSResult

        payload = {"engine": "moss", "text": text, "voice": kw["voice"] or "", "language": lang, "seed": seed}
        files = {}
        if kw["reference"]:
            files["ref.wav"] = Path(kw["reference"])
            payload["reference_input"] = "ref.wav"
        res = compute.run_task(ctx, "voice.tts", payload, inputs=files)
        try:
            src = res.file("speech.wav")
            if src is None:
                raise ProviderError("the speech task returned no audio", retryable=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), out)
        finally:
            res.cleanup()
        r = TTSResult(out, float(res.result.get("seconds") or 0.0), "moss", str(res.result.get("voice") or ""), int(res.result.get("sample_rate") or 24000),
                      float(res.result.get("render_seconds") or res.seconds))
        r.device = res.device
        return r
    if tts.resource == "gpu":
        from instai.gpu.arbiter import ARBITER

        with ARBITER.hold(ctx, "voice"):
            return tts.synthesize(text, out, **kw)
    return tts.synthesize(text, out, **kw)


def step_clips(ctx, ep: Episode, mode: str) -> dict:
    """Wan 2.2 hero shots (image-to-video, first/last-frame transitions, chained for long shots) from the approved keyframes. Every shot is one or
    more ComfyUI tasks on the GPU router (this PC and worker PCs); colour matched to the keyframe and checked against it and the character sheet.
    No device able to run Wan is not fatal: those shots keep the Ken Burns motion."""
    from instai.gpu import compute

    from .models import ShotRender

    shots = missing_clips(ep)
    if not shots:
        return {"generated": 0}
    wid, _ = hero.i2v_workflow(page_of(ep))
    if not compute.workflow_available(wid):
        reason = f"no PC can run the video workflow {wid} (ComfyUI down or model files missing)"
        ctx.log(f"video clips skipped, Ken Burns is used instead: {reason}", "warning")
        return {"generated": 0, "skipped": len(shots), "reason": reason}
    counter = {"n": 0}

    def one(shot: Shot) -> int:
        kf = current(shot, "keyframe")
        rec = ShotRender.objects.create(shot=shot, technique=shot.technique, status="running", params={"workflow": wid, "duration": shot.duration_sec})
        try:
            r = hero.make_clip(ctx, shot, ep, kf, next_keyframe(shot, ep) if shot.technique == "wan_flf" else None, prompt=shot.image_prompt or shot.description,
                               seed=shot.seed or 1, flf=shot.technique == "wan_flf")
        except BaseException as e:
            ShotRender.objects.filter(pk=rec.pk).update(status="failed", error=str(e)[:500])
            raise
        chash = clip_hash(shot, kf, ep)
        rel = f"episodes/{ep.pk}/clips/shot{shot.pk}-{chash[:8]}.mp4"
        asset = asset_storage.register(r["path"], rel, kind="video", role="shot_clip", page=page_of(ep), episode=ep, shot=shot, input_hash=chash,
                                       provenance={"workflow": r["workflow"], "provider": "comfyui", "job_id": ctx.job.pk, "device": r["device"], "segments": r["segments"],
                                                   "colour_match": r["colour"], "consistency": r["qc"], "first_last_frame": r["flf"], "notes": r["notes"]})
        _cleanup(r["path"].parent)
        ShotRender.objects.filter(pk=rec.pk).update(status="done", asset=asset, device=r["device"], seconds=r["seconds"], qc=r["qc"],
                                                    params={"workflow": r["workflow"], "segments": r["segments"], "colour": r["colour"], "notes": r["notes"]})
        counter["n"] += 1
        ctx.progress(counter["n"] / len(shots), f"video {counter['n']}/{len(shots)}")
        return 1
    done = sum(compute.fan_out(ctx, shots, one, kind="comfy.graph", payload={"workflow": wid}))
    return {"generated": done}


def shot_specs(ep: Episode, mode: str) -> tuple[list[asm.ShotSpec], list[str]]:
    """ShotSpecs from current assets + notes about fallbacks (shown in QC and the job log)."""
    specs, notes = [], []
    shots = services.all_shots(ep)
    for i, s in enumerate(shots):
        kf, nar, clip = current(s, "keyframe"), current(s, "narration"), current(s, "shot_clip")
        layers = None
        puppet_scene = None
        if s.technique == "puppet_2d":
            from . import puppet as puppet_mod

            puppet_scene, pnotes = puppet_mod.build_scene(
                s, ep, narration=nar, keyframe=kf, duration=asm.shot_duration(asm.ShotSpec(key=str(s.pk), duration=s.duration_sec,
                                                                                            audio="x" if nar else None, audio_duration=(nar.duration_sec or 0.0) if nar else 0.0)),
                language=page_of(ep).language, demo_mode=image_engine() == "placeholder")
            notes += pnotes
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
            subtitle=s.narration, puppet=puppet_scene))
    return specs, notes


def step_assemble(ctx, ep: Episode, mode: str) -> dict:
    specs, notes = shot_specs(ep, mode)
    if not specs:
        raise DomainError("not_ready", "قسمت هیچ شاتی ندارد.")
    for n in notes:
        ctx.log(n, "warning")
    if any(s.image is None and s.video is None and not s.puppet for s in specs):
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
            from . import puppet as puppet_mod

            chash = _h("clip", spec.image and Path(spec.image).name, spec.video and Path(spec.video).name, spec.camera, round(dur, 3),
                       opts.width, opts.height, opts.fps, mode, puppet_mod.spec_hash_parts(spec.puppet))
            cached = Asset.objects.filter(shot=shot, role="render_clip", is_current=True, input_hash=chash).first()
            if cached and asset_storage.storage.exists(cached.path):
                clips.append(asset_storage.storage.path_for(cached.path))
                continue
            out = work / f"clip{i:03d}.mp4"
            t_clip = time.time()
            asm.render_shot_clip(spec, opts, out, duration=dur, ctx=ctx)
            if spec.puppet:
                from .models import ShotRender

                ShotRender.objects.create(shot=shot, technique="puppet_2d", status="done", device="local", seconds=round(time.time() - t_clip, 2),
                                          params={"mode": mode, "lipsync": spec.puppet.get("lipsync"), "rig": spec.puppet.get("rig"), "duration": round(dur, 2)})
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
    used = _voice_engines_used(ep)
    flagged = [e for e in used if e["commercial"] == "no"]
    checks.append({"name": "voice_licence", "level": "warn" if flagged else "ok", "value": {"engines": [e["engine"] for e in used], "warnings": flagged},
                   "message": ("صدای غیرتجاری یا غیررسمی در این قسمت به کار رفته است: " + "، ".join(e["engine"] for e in flagged)
                               + " — برای انتشار تجاری از MOSS یا Piper (با مجوز بررسی‌شدهٔ صدا) استفاده کنید.") if flagged else
                   "موتورهای صدا: " + ("، ".join(e["engine"] for e in used) or "—")})
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


def _voice_engines_used(ep: Episode) -> list[dict]:
    """Licence facts of every speech engine behind the current narration assets of the episode (from asset provenance)."""
    from instai.providers.tts import licence_of

    seen: dict[str, dict] = {}
    for a in Asset.objects.filter(episode=ep, role="narration", is_current=True):
        eng = (a.provenance or {}).get("engine")
        if eng and eng not in seen:
            seen[eng] = licence_of(eng)
    return list(seen.values())


def _expected_duration(ep: Episode, video: Asset) -> float:
    prov = video.provenance or {}
    return float(prov.get("expected_duration") or video.duration_sec or 0)
