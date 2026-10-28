"""The animatic: timed stills + scratch narration + burned subtitles, rendered with the existing render path (ffmpeg assembly, preview size).

Not production: it never touches the episode state, the shots' own assets or the GPU. A shot with an approved keyframe shows that image; any other
shot shows a labelled placeholder card, so the animatic is available the moment the storyboard exists. Narration is read by the page's TTS engine
when one is ready (scratch quality is fine); otherwise the timing comes from reading speed and the animatic is silent. Its job is to let the director
judge pacing and story flow BEFORE the expensive steps run.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.providers.base import ProviderError
from instai.render import assemble as asm
from instai.render.placeholders import make_placeholder
from instai.story import services as story_services
from instai.story.models import Episode

from . import preprod

log = logging.getLogger("instai.studio.animatic")


def build(ctx, ep: Episode) -> dict:
    from instai.providers.tts import estimate_seconds, get_tts

    shots = story_services.all_shots(ep)
    if not shots:
        raise DomainError("not_ready", "ابتدا استوری‌بورد را بسازید.", message_en="Build the storyboard first.")
    page = ep.series.page
    prod, vis, aud = page.profile("production"), page.profile("visual"), page.profile("audio")
    opts = asm.RenderOptions.for_mode("preview", final_height=prod["final_height"], preview_height=prod["preview_height"], fps=prod["fps"],
                                      subtitle_style=vis["subtitle"], target_lufs=float(aud["target_lufs"]))
    lang = page.language
    work = Path(tempfile.mkdtemp(prefix="animatic-", dir=settings.MEDIA_ROOT))
    notes: list[str] = []
    stills = {"keyframes": 0, "placeholders": 0}
    spoken, silent = 0, 0
    tts_cache: dict[str, object] = {}
    try:
        specs: list[asm.ShotSpec] = []
        for i, shot in enumerate(shots):
            ctx.check()
            ctx.progress(0.05 + 0.4 * i / len(shots), f"shot {i + 1}/{len(shots)}")
            kf = preprod.keyframe_for(shot)
            if kf and asset_storage.storage.exists(kf.path):
                image = str(asset_storage.storage.path_for(kf.path))
                stills["keyframes"] += 1
            else:
                image = str(make_placeholder(work / f"still{i:03d}.png", 448, 800, f"{shot.scene.index}.{shot.index}", seed=f"animatic-{ep.pk}-{shot.pk}"))
                stills["placeholders"] += 1
            audio, audio_dur, duration = None, 0.0, float(shot.duration_sec)
            text = shot.narration.strip()
            if text:
                vf = _voice(shot, ep)
                try:
                    engine = vf["engine"] if vf["engine"] not in ("", "auto") else None
                    key = engine or "auto"
                    if key not in tts_cache:
                        tts_cache[key] = get_tts(engine)
                    res = tts_cache[key].synthesize(text, work / f"nar{i:03d}.wav", voice=vf["voice"] or None, language=lang, reference=vf["reference"] or None)  # type: ignore[attr-defined]
                    audio, audio_dur = str(res.path), res.seconds
                    spoken += 1
                except (ProviderError, OSError) as e:
                    silent += 1
                    duration = max(duration, estimate_seconds(text, lang))
                    if not notes or "scratch narration" not in notes[-1]:
                        notes.append(f"scratch narration unavailable ({str(e)[:90]}); timing follows reading speed")
            specs.append(asm.ShotSpec(key=str(shot.pk), duration=duration, image=image, camera=shot.camera or {}, technique="still_kenburns", transition="cut",
                                      audio=audio, audio_duration=audio_dur, subtitle=text))
        clips: list[Path] = []
        for i, spec in enumerate(specs):
            ctx.check()
            ctx.progress(0.45 + 0.3 * i / len(specs), f"clip {i + 1}/{len(specs)}")
            out = work / f"clip{i:03d}.mp4"
            asm.render_shot_clip(spec, opts, out, duration=asm.shot_duration(spec), ctx=ctx)
            clips.append(out)
        ctx.progress(0.78, "joining, subtitles")
        final = work / "animatic.mp4"
        info = asm.assemble(specs, clips, opts, final, work / "asm", ctx=ctx, on_progress=lambda f: ctx.progress(0.78 + 0.2 * f, "encoding"))
        scratch = "tts" if spoken and not silent else ("partial" if spoken else "none")
        h = preprod.animatic_hash(ep)
        rel = f"episodes/{ep.pk}/animatic/animatic-{h[:8]}.mp4"
        asset = asset_storage.register(final, rel, kind="video", role="animatic", page=page, episode=ep, input_hash=h,
                                       provenance={"workflow": "animatic@1", "mode": "preview", "job_id": ctx.job.pk, "shots": len(specs), "notes": notes,
                                                   "scratch_audio": scratch, "stills": stills, "tts_engine": settings_store.effective("tts_engine"),
                                                   "expected_duration": info["duration"]})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    preprod.clear_approval(ep, "animatic")
    return {"asset_id": asset.pk, "duration": info["duration"], "shots": len(specs), "stills": stills, "scratch_audio": scratch, "notes": notes}


def _voice(shot, ep) -> dict:
    """The speaking character's voice, else the page's narration voice: the production voice stack decides (VoiceCast -> character -> page)."""
    from instai.production import voices

    page = ep.series.page
    char = page.characters.filter(name=shot.speaker).first() if shot.speaker else None
    v = voices.resolve(char, voices.language_of(page), page)
    return {"engine": v["engine"] or "auto", "voice": v["voice"], "reference": v["reference"] if v.get("consent_ok", True) else ""}
