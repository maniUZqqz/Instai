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
