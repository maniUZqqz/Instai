"""Music, ambience and sound effects of an episode: planning (from the page's audio settings, the scenes' locations and the shots' `sfx` text),
generation (ACE-Step music, MOSS-SoundEffect ambience/SFX through the GPU router - a worker PC can make them), and resolution to absolute
timeline positions for the FFmpeg mix (ducking under dialogue, fades, gains). The filter maths lives in render/assemble.py."""
from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.gpu import compute
from instai.providers.base import ProviderError
from instai.story import services

from .models import MixTrack, PageProductionConfig

MOOD_PROMPTS = {"calm": "calm soft ambient piano and pads", "epic": "epic cinematic orchestral build, drums", "tense": "tense dark suspense underscore",
                "happy": "light happy upbeat acoustic, ukulele and claps", "sad": "melancholic slow piano and strings", "mystery": "mysterious airy pads, subtle plucks"}
SFX_MAX = 30.0


def music_prompt(page) -> str:
    aud = page.profile("audio")
    mood = (aud.get("music_mood") or "calm").lower()
    return f"{MOOD_PROMPTS.get(mood, mood)}, instrumental background music for a short video, no vocals, steady tempo"


def plan(ep) -> list[MixTrack]:
    """Create the planned (not yet generated) tracks of an episode if it has none: one music bed, one ambience per scene with a location,
    one effect per shot with `sfx` text. Existing tracks are never replaced."""
    if ep.mix_tracks.exists():
        return list(ep.mix_tracks.all())
    page = ep.series.page
    aud = page.profile("audio")
    cfg = PageProductionConfig.objects.filter(page=page).first()
    out: list[MixTrack] = []
    if aud.get("music_enabled") and (cfg is None or cfg.music_enabled):
        out.append(MixTrack.objects.create(episode=ep, kind="music", label="موسیقیِ زمینه", prompt=music_prompt(page), gain_db=float(aud.get("music_volume_db", -22)), duck=True,
                                           fade_in=1.0, fade_out=2.0))
    for scene in ep.scenes.all():
        shots = list(scene.shots.all())
        if scene.location and shots and aud.get("sfx_enabled"):
            out.append(MixTrack.objects.create(episode=ep, shot=shots[0], kind="ambience", label=f"فضای {scene.location}"[:160],
                                               prompt=f"ambience of {scene.location}, no music, no speech", gain_db=-26.0, duck=True, fade_in=0.8, fade_out=0.8))
        for s in shots:
            if (s.sfx or "").strip() and aud.get("sfx_enabled"):
                out.append(MixTrack.objects.create(episode=ep, shot=s, kind="sfx", label=s.sfx[:160], prompt=s.sfx.strip(), gain_db=-12.0, duck=False, fade_in=0.02, fade_out=0.15))
    return out


def generate(ctx, track: MixTrack) -> dict:
    """Make the audio of one track on the best free device and register it. Demo mode (sfx/music engine 'fake') makes test tones locally."""
    ep = track.episode
    seconds = 8.0
    if track.kind == "music":
        seconds = min(240.0, max(10.0, float(sum(s.duration_sec for s in services.all_shots(ep)) + 2)))
    elif track.kind == "ambience":
        seconds = SFX_MAX
    elif track.shot_id:
        seconds = min(SFX_MAX, max(1.0, float(track.shot.duration_sec)))
    MixTrack.objects.filter(pk=track.pk).update(status="generating", error="")
    t0 = time.time()
    try:
        kind = "voice.music" if track.kind == "music" else "voice.sfx"
        from instai.core import settings_store

        engine_key = "music_engine" if track.kind == "music" else "sfx_engine"
        payload = {"prompt": track.prompt or track.label, "seconds": seconds, "seed": int(track.pk) * 13 + 5}
        if str(settings_store.effective(engine_key) or "auto") == "fake":
            from instai.providers.audio import get_generator

            tmp = Path(tempfile.mkdtemp(prefix="mix-", dir=settings.MEDIA_ROOT)) / "a.wav"
            r = get_generator("music" if track.kind == "music" else "sfx").generate(payload["prompt"], seconds, tmp, seed=payload["seed"])
            engine, licence, device = r.engine, r.licence, "local"
        else:
            res = compute.run_task(ctx, kind, payload)
            try:
                f = res.file("music.wav" if track.kind == "music" else "sfx.wav")
                if f is None:
                    raise ProviderError("the audio task returned no file", retryable=True)
                tmp = Path(tempfile.mkdtemp(prefix="mix-", dir=settings.MEDIA_ROOT)) / "a.wav"
                shutil.move(str(f), tmp)
            finally:
                res.cleanup()
            engine, licence, device = res.result.get("engine", ""), res.result.get("licence", ""), res.device
        rel = f"episodes/{ep.pk}/mix/track{track.pk}-{int(time.time())}.wav"
        a = asset_storage.register(tmp, rel, kind="audio", role="music" if track.kind in ("music", "ambience") else "sfx", page=ep.series.page, episode=ep,
                                   shot=None, provenance={"purpose": "mix", "track": track.pk, "kind": track.kind, "prompt": payload["prompt"], "engine": engine, "licence": licence,
                                                          "device": device, "seed": payload["seed"], "render_seconds": round(time.time() - t0, 1)})
        shutil.rmtree(tmp.parent, ignore_errors=True)
        MixTrack.objects.filter(pk=track.pk).update(status="ready", asset=a)
        return {"asset_id": a.pk, "engine": engine, "device": device, "seconds": a.duration_sec}
    except BaseException as e:
        MixTrack.objects.filter(pk=track.pk).update(status="failed", error=str(e)[:400])
        raise


def resolve(ep, specs, timeline: list[dict]) -> list[dict]:
    """Ready tracks as absolute positions on the episode timeline: [{file, kind, start, end, gain_db, duck, fade_in, fade_out, loop}]."""
    by_shot = {s.key: t for s, t in zip(specs, timeline)}
    total = timeline[-1]["end"] if timeline else 0.0
    scenes: dict[int, list[str]] = {}
    for shot in services.all_shots(ep):
        scenes.setdefault(shot.scene_id, []).append(str(shot.pk))
    out = []
    for tr in ep.mix_tracks.select_related("asset", "shot").all():
        if tr.status != "ready" or tr.asset_id is None or not asset_storage.storage.exists(tr.asset.path):
            continue
        path = str(asset_storage.storage.path_for(tr.asset.path))
        natural = tr.asset.duration_sec or 0.0
        if tr.kind == "music":
            start, end, loop = tr.start_sec, tr.end_sec if tr.end_sec is not None else total, True
        elif tr.kind == "ambience" and tr.shot_id:
            keys = scenes.get(tr.shot.scene_id, [])
            tl = [by_shot[k] for k in keys if k in by_shot]
            if not tl:
                continue
            start, end, loop = tl[0]["start"], tl[-1]["end"], True
        else:
            base = by_shot.get(str(tr.shot_id))["start"] if tr.shot_id and str(tr.shot_id) in by_shot else 0.0
            start = base + tr.start_sec
            end = tr.end_sec if tr.end_sec is not None else min(total, start + natural) if natural else total
            loop = False
        start, end = max(0.0, start), min(total, end)
        if end - start < 0.05:
            continue
        out.append({"file": path, "kind": tr.kind, "start": round(start, 3), "end": round(end, 3), "gain_db": tr.gain_db, "duck": tr.duck, "fade_in": tr.fade_in,
                    "fade_out": tr.fade_out, "loop": loop, "id": tr.pk})
    return out


def mix_hash_parts(ep) -> list:
    return [[t.pk, t.kind, t.start_sec, t.end_sec, t.gain_db, t.duck, t.fade_in, t.fade_out, t.asset.sha256 if t.asset_id else ""]
            for t in ep.mix_tracks.select_related("asset").all()]
