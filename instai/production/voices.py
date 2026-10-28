"""Voice casting: which engine and voice speak for a character, per language (fa / en), and the consent rules for cloned voices.

Resolution order for a shot: VoiceCast(character, language) -> Character.voice (older free-form JSON) -> the page's narration voice
(audio profile) -> engine defaults per language. A cloned voice is only ever used when its recording carries the owner's consent.
"""
from __future__ import annotations

import base64
import binascii
import tempfile
import wave
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from instai.assets import storage as asset_storage
from instai.core.errors import DomainError
from instai.providers import tts as tts_mod

CONSENT_TEMPLATE_FA = ("تأیید می‌کنم که صاحبِ این صدا ({person}) خودم هستم یا رضایتِ او را گرفته‌ام که از روی صدایش یک صدای مصنوعی ساخته شود "
                       "و فقط برای «{purpose}» به کار رود. از این صدا برای فریب یا جعلِ هویت استفاده نمی‌شود و هر وقت صاحبِ صدا بخواهد پاک می‌شود.")
CONSENT_TEMPLATE_EN = ("I confirm that I am the owner of this voice ({person}) or have their consent to make a synthetic voice from it, to be used only for "
                       "\"{purpose}\". It will not be used to deceive or impersonate, and it will be deleted whenever the voice owner asks.")
MIN_REF_SECONDS, MAX_REF_SECONDS = 3.0, 30.0


def language_of(page) -> str:
    return (page.language or "fa")[:2]


def resolve(character, language: str, page=None) -> dict:
    """{engine, voice, reference, speed, source, ref_id, consent_ok} for one character; `character` may be None (narrator)."""
    from instai.production.models import VoiceCast

    language = (language or "fa")[:2]
    cast = VoiceCast.objects.select_related("reference__asset").filter(character=character, language=language).first() if character else None
    if cast:
        ref_path, ref_id, consent_ok = "", None, True
        if cast.reference_id:
            ref = cast.reference
            ref_id = ref.pk
            consent_ok = bool(ref.consent_given and ref.consent_text.strip())
            if consent_ok and ref.asset_id and asset_storage.storage.exists(ref.asset.path):
                ref_path = str(asset_storage.storage.path_for(ref.asset.path))
        return {"engine": cast.engine or "auto", "voice": cast.voice_id, "reference": ref_path, "speed": cast.speed, "source": "cast",
                "ref_id": ref_id, "consent_ok": consent_ok}
    cv = (character.voice if character else None) or {}
    aud = page.profile("audio") if page is not None else {}
    return {"engine": cv.get("engine") or aud.get("narration_engine") or "auto", "voice": cv.get("voice_id") or aud.get("narration_voice") or "",
            "reference": cv.get("reference") or "", "speed": 1.0, "source": "character" if cv.get("engine") else "page", "ref_id": None, "consent_ok": True}


def effective_engine(engine: str, language: str) -> str:
    """The engine that will really speak ("auto" = MOSS when it is ready, else Piper)."""
    if engine != "auto":
        return engine
    try:
        return tts_mod.get_tts().id
    except Exception:  # noqa: BLE001
        return "auto"


def default_voice(engine: str, language: str) -> str:
    return tts_mod.DEFAULT_VOICES.get(engine, {}).get(language[:2], "")


def engines_payload(language: str = "fa") -> list[dict]:
    """Everything the voice picker needs: availability, licence badge/warning (fa+en), languages, voices."""
    out = []
    for p in tts_mod.all_engines() + [tts_mod.FakeTTS()]:
        ok, detail = p.available()
        lic = p.licence_info()
        out.append({"id": p.id, "label": p.label, "available": ok, "detail": detail, "resource": p.resource, "languages": list(p.languages),
                    "online": p.online, "needs_reference": p.needs_reference, "licence": p.licence, "commercial": lic["commercial"],
                    "badge": lic["badge"], "warning": lic["warning"], "warning_text": lic["warning_text"],
                    "default_voice": default_voice(p.id, language), "voices": p.voices(language) if ok else []})
    return out


def save_reference(character, *, language: str, label: str, person_name: str, consent_given: bool, consent_text: str, purpose: str,
                   audio_b64: str, filename: str = "reference.wav"):
    """Store a consented recording as a VoiceReference (+ an audio Asset). Rejects missing consent and unusable audio."""
    from instai.production.models import VoiceReference
    from instai.render import ffmpeg

    if not consent_given or not (consent_text or "").strip():
        raise DomainError("validation_error", "بدون رضایتِ صاحبِ صدا نمی‌توان صدایی ساخت: متنِ رضایت را تأیید کنید.", http_status=400,
                          details={"consent_given": ["required"]})
    try:
        raw = base64.b64decode(audio_b64 or "", validate=False)
    except (binascii.Error, ValueError):
        raw = b""
    if len(raw) < 1000:
        raise DomainError("validation_error", "فایل صدا خالی یا خراب است.", http_status=400, details={"audio": ["invalid"]})
    tmpdir = Path(tempfile.mkdtemp(prefix="vref-", dir=settings.MEDIA_ROOT))
    try:
        src = tmpdir / ("in" + (Path(filename).suffix.lower() or ".wav")[:6])
        src.write_bytes(raw)
        wav = tmpdir / "ref.wav"
        try:
            ffmpeg.run(["-i", str(src), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)])
            with wave.open(str(wav), "rb") as w:
                seconds = w.getnframes() / float(w.getframerate())
                frames = w.readframes(min(w.getnframes(), 24000 * 30))
        except Exception as e:  # noqa: BLE001
            raise DomainError("validation_error", "فایل صدا خوانده نشد؛ WAV یا MP3 بدهید.", http_status=400, details={"audio": [str(e)[:80]]}) from e
        if not MIN_REF_SECONDS <= seconds <= MAX_REF_SECONDS:
            raise DomainError("validation_error", f"طول نمونهٔ صدا باید بین {MIN_REF_SECONDS:.0f} و {MAX_REF_SECONDS:.0f} ثانیه باشد (الان {seconds:.1f}).",
                              http_status=400, details={"audio": ["length"]})
        import array
        import math

        samples = array.array("h", frames[: len(frames) // 2 * 2])
        rms = math.sqrt(sum(x * x for x in samples) / max(1, len(samples))) / 32768.0
        if rms < 0.003:
            raise DomainError("validation_error", "صدای ضبط‌شده تقریباً بی‌صداست؛ دوباره ضبط کنید.", http_status=400, details={"audio": ["silent"]})
        ref = VoiceReference.objects.create(character=character, language=language[:2], label=label or person_name, person_name=person_name,
                                            consent_given=True, consent_text=consent_text.strip(), consented_at=timezone.now(), purpose=purpose)
        asset = asset_storage.register(wav, f"characters/{character.pk}/voice/ref{ref.pk}.wav", kind="audio", role="reference", page=character.page,
                                       provenance={"voice_reference": ref.pk, "person": person_name, "consent": True})
        ref.asset = asset
        ref.save(update_fields=["asset"])
        return ref
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def ref_dict(r) -> dict:
    return {"id": r.pk, "character": r.character_id, "language": r.language, "label": r.label, "person_name": r.person_name,
            "consent_given": r.consent_given, "consented_at": r.consented_at, "purpose": r.purpose,
            "audio_url": r.asset.url if r.asset_id else None, "duration_sec": r.asset.duration_sec if r.asset_id else None}


def cast_dict(c) -> dict:
    lic = tts_mod.licence_of(c.engine if c.engine != "auto" else "moss")
    return {"id": c.pk, "character": c.character_id, "language": c.language, "engine": c.engine, "voice_id": c.voice_id,
            "reference": c.reference_id, "speed": c.speed, "licence": lic if c.engine != "auto" else None}
