"""Phase 3/4 jobs that are not an episode pipeline step: voice previews, audio (music / SFX) generation, rig building, comparisons,
LoRA training, retakes, benchmarks of a worker. Handlers are thin: the work lives in instai.production / instai.render."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings

from instai.core import settings_store
from instai.jobs.registry import handler


def _preview_resource(payload: dict) -> str:
    eng = str(payload.get("engine") or "auto")
    if eng == "auto":
        eng = str(settings_store.effective("tts_engine") or "auto")
    if eng in ("fake", "piper", "pocket"):
        return "cpu"
    if eng == "edge":
        return "net"
    return "gpu"


@handler("voice.preview", resource=_preview_resource, timeout=900)
def voice_preview(ctx):
    import tempfile

    from instai.assets import storage as asset_storage
    from instai.assets.models import Asset
    from instai.production import pipeline, voices
    from instai.production.models import VoiceReference
    from instai.providers.tts import get_tts

    p = ctx.payload
    engine = p.get("engine") or "auto"
    tts = get_tts(None if engine == "auto" else engine)
    lang = p.get("language") or "fa"
    ref_path = ""
    if p.get("reference_id"):
        ref = VoiceReference.objects.select_related("asset").get(pk=p["reference_id"])
        if not ref.consent_given:
            from instai.providers.base import ProviderError

            raise ProviderError("no consent recorded for this voice", retryable=False, code="consent_missing")
        ref_path = str(asset_storage.storage.path_for(ref.asset.path))
    tmp = Path(tempfile.mkdtemp(prefix="vp-", dir=settings.MEDIA_ROOT)) / "preview.wav"
    ctx.progress(0.2, "speaking")
    voice = {"voice": p.get("voice") or voices.default_voice(tts.id, lang), "reference": ref_path}
    res = pipeline._speak(ctx, tts, p["text"], tmp, voice, lang, 1)
    a = asset_storage.register(tmp, f"previews/voice-{ctx.job.pk}.wav", kind="audio", role="other",
                               provenance={"purpose": "voice_preview", "engine": res.engine, "voice": res.voice, "licence": res.licence})
    pipeline._cleanup(tmp.parent)
    return {"asset_id": a.pk, "url": a.url, "engine": res.engine, "licence": res.licence, "seconds": round(res.seconds, 2)}


# further handlers register themselves from their own modules (imported by handlers/__init__)


@handler("rig.preview", resource="cpu", timeout=900)
def rig_preview(ctx):
    """A short clip of the rig talking (+ one motion): proves the parts, pivots and mouth shapes before an episode uses them."""
    import json
    import tempfile

    from instai.assets import storage as asset_storage
    from instai.production import pipeline
    from instai.production.models import CharacterRig
    from instai.providers.tts import FakeTTS
    from instai.render.puppet import demo, lipsync, motions, renderer

    rig = CharacterRig.objects.select_related("character").get(pk=ctx.payload["rig_id"])
    root = Path(settings.MEDIA_ROOT)
    spec = json.loads(json.dumps(rig.spec))
    for p in spec["parts"].values():
        if p.get("image") and not Path(p["image"]).is_absolute():
            p["image"] = str(root / p["image"])
    tmpdir = Path(tempfile.mkdtemp(prefix="rigprev-", dir=root))
    try:
        wav = tmpdir / "line.wav"
        FakeTTS().synthesize("hello this is a short test line for the mouth shapes", wav, language="en")
        cues = lipsync.amplitude_cues(wav)
        motion = ctx.payload.get("motion") or ""
        dur = 3.6
        timeline = motions.talk_timeline(dur, [(0.2, 3.0)], base=motion if motion in motions.BASE_MOTIONS else "idle",
                                         gestures=[(motion, 0.4)] if motion and motion not in motions.BASE_MOTIONS and motion in motions.MOTIONS else None)
        scene = {"width": 270, "height": 480, "fps": 12, "duration": dur, "background": {"layers": demo.make_background(root / "_cache" / "demo-bg", 540, 960)},
                 "actors": [{"rig": spec, "x": 0.5, "y": 0.94, "height": 0.62, "mouth": [list(c) for c in cues], "timeline": timeline, "seed": 7}],
                 "camera": renderer.camera_from_move("zoom_in", 0.3, dur)}
        out = tmpdir / "preview.mp4"
        ctx.progress(0.1, "rendering")
        renderer.PuppetRenderer(scene, root).render(out, ctx=ctx, crf=28, preset="ultrafast", on_progress=lambda f: ctx.progress(0.1 + 0.85 * f, "rendering"))
        a = asset_storage.register(out, f"characters/{rig.character_id}/rig{rig.version}/preview-{ctx.job.pk}.mp4", kind="video", role="other",
                                   page=rig.character.page, provenance={"purpose": "rig_preview", "rig": rig.pk, "motion": motion, "lipsync": "amplitude"})
    finally:
        pipeline._cleanup(tmpdir)
    return {"asset_id": a.pk, "url": a.url}
