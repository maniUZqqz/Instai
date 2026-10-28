"""Voice stack API: engines with licence badges, per-character voice casting (fa / en), consented voice references, previews."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import Character
from instai.providers import tts as tts_mod
from instai.providers.audio import audio_status, services

from . import voices
from .models import VoiceCast, VoiceReference

LANGS = ("fa", "en")


@api_view(["GET"])
def voice_engines(request):
    lang = (request.query_params.get("language") or "fa")[:2]
    return Response({"language": lang, "engines": voices.engines_payload(lang), "services": services.describe(), "audio": audio_status(),
                     "consent_templates": {"fa": voices.CONSENT_TEMPLATE_FA, "en": voices.CONSENT_TEMPLATE_EN},
                     "auto_note": "auto = MOSS when ready, else Piper; Pocket and Edge are never chosen automatically"})


def _character_payload(ch: Character) -> dict:
    return {"character": {"id": ch.pk, "name": ch.name, "page": ch.page_id}, "languages": list(LANGS),
            "casts": [voices.cast_dict(c) for c in ch.voice_casts.all()], "refs": [voices.ref_dict(r) for r in ch.voice_refs.select_related("asset")]}


@api_view(["GET"])
def character_voices(request, pk):
    return Response(_character_payload(get_object_or_404(Character, pk=pk)))


@api_view(["PUT", "DELETE"])
def character_voice(request, pk, lang):
    ch = get_object_or_404(Character, pk=pk)
    if lang not in LANGS:
        raise DomainError("validation_error", "زبان باید fa یا en باشد.", http_status=400)
    if request.method == "DELETE":
        VoiceCast.objects.filter(character=ch, language=lang).delete()
        return Response(_character_payload(ch))
    d = request.data
    engine = str(d.get("engine") or "auto")
    if engine != "auto" and engine not in tts_mod.ENGINE_IDS:
        raise DomainError("validation_error", "موتور صدا نامعتبر است.", http_status=400, details={"engine": ["invalid"]})
    ref = None
    if d.get("reference"):
        ref = get_object_or_404(VoiceReference, pk=d["reference"], character=ch)
        if not (ref.consent_given and ref.consent_text.strip()):
            raise DomainError("validation_error", "این نمونهٔ صدا رضایت‌نامه ندارد.", http_status=400)
        engine = "moss"  # only MOSS speaks in a reference voice
    try:
        speed = max(0.6, min(1.6, float(d.get("speed") or 1.0)))
    except (TypeError, ValueError):
        speed = 1.0
    VoiceCast.objects.update_or_create(character=ch, language=lang, defaults={"engine": engine, "voice_id": str(d.get("voice_id") or ""),
                                                                             "reference": ref, "speed": speed})
    return Response(_character_payload(ch))


@api_view(["POST"])
def character_voice_refs(request, pk):
    ch = get_object_or_404(Character, pk=pk)
    d = request.data
    ref = voices.save_reference(ch, language=str(d.get("language") or "fa"), label=str(d.get("label") or ""), person_name=str(d.get("person_name") or ""),
                                consent_given=bool(d.get("consent_given")), consent_text=str(d.get("consent_text") or ""), purpose=str(d.get("purpose") or ""),
                                audio_b64=str(d.get("audio_base64") or ""), filename=str(d.get("filename") or "reference.wav"))
    return Response(voices.ref_dict(ref), status=201)


@api_view(["DELETE"])
def voice_ref_detail(request, pk):
    ref = get_object_or_404(VoiceReference, pk=pk)
    VoiceCast.objects.filter(reference=ref).update(engine="auto", reference=None)
    ref.delete()  # the recording is moved aside by nobody: it is a person's voice, so the asset row stays only if referenced elsewhere
    return Response(status=204)


@api_view(["POST"])
def voice_preview(request):
    d = request.data
    text = str(d.get("text") or "").strip()
    if not text:
        raise DomainError("validation_error", "متن نمونه خالی است.", http_status=400, details={"text": ["required"]})
    payload = {"engine": str(d.get("engine") or "auto"), "voice": str(d.get("voice") or ""), "language": str(d.get("language") or "fa")[:2],
               "text": text[:400], "reference_id": d.get("reference_id")}
    return job_response(queue.enqueue("voice.preview", payload, title="نمونهٔ صدا", priority=5))


urlpatterns = [
    path("voices/engines", voice_engines),
    path("voices/preview", voice_preview),
    path("characters/<int:pk>/voices", character_voices),
    path("characters/<int:pk>/voices/<str:lang>", character_voice),
    path("characters/<int:pk>/voice-refs", character_voice_refs),
    path("voice-refs/<int:pk>", voice_ref_detail),
]
