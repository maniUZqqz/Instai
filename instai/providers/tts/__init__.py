"""Text-to-speech adapters: MOSS-TTS server (GPU), Piper (CPU, offline), Pocket-TTS (voice-kit gateway), Edge TTS (online)
and a fake engine for tests/demo.

MOSS server protocol adapted from Qasem processing-server/audio/_common.py + moss_tts_server.py
(GET /health, POST /run {text, reference, seed, out} -> {ok, seconds}). Pocket-TTS is spoken through the voice-kit gateway of
Qasem processing-server/agent.py (POST /api/voice/tts); Edge TTS through the `edge-tts` package.

Licences: every engine carries a `commercial` flag and a warning key. Pocket (non-commercial) and Edge (unofficial online endpoint)
are available because the owner asked for them, but they are NEVER chosen by `auto`, and the UI / QC report show the warning
wherever they are selected or used.
"""
from __future__ import annotations

import abc
import math
import struct
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import requests

from instai.core import runtime, settings_store
from instai.providers.base import ProviderError

WORDS_PER_SECOND = {"fa": 2.4, "en": 2.6}

# engine -> licence facts. `commercial`: yes | unknown | no | n/a. `warning` is a key the UI maps to a text in fa/en.
LICENCE_INFO = {
    "moss": {"commercial": "yes", "badge": "Apache-2.0", "warning": None},
    "piper": {"commercial": "unknown", "badge": "MIT engine; voice licence varies", "warning": "piper_voice_licence"},
    "pocket": {"commercial": "no", "badge": "NON-COMMERCIAL (CC-BY-NC-4.0)", "warning": "pocket_noncommercial"},
    "edge": {"commercial": "no", "badge": "UNOFFICIAL ONLINE ENDPOINT", "warning": "edge_unofficial"},
    "fake": {"commercial": "n/a", "badge": "test audio", "warning": None},
}
WARNING_TEXT = {
    "pocket_noncommercial": {
        "en": "Pocket-TTS is licensed for NON-COMMERCIAL use only. Do not use it for content you publish commercially.",
        "fa": "Pocket-TTS فقط برای استفادهٔ غیرتجاری مجاز است. برای محتوایی که تجاری منتشر می‌کنید از آن استفاده نکنید."},
    "edge_unofficial": {
        "en": "Edge TTS is an unofficial online endpoint (needs internet) and is not licensed for commercial use.",
        "fa": "Edge TTS یک سرویس آنلاین غیررسمی است (اینترنت لازم دارد) و برای استفادهٔ تجاری مجاز نیست."},
    "piper_voice_licence": {
        "en": "Each Piper voice has its own licence: check the voice's model card before publishing commercially.",
        "fa": "هر صدای Piper مجوز خودش را دارد؛ پیش از انتشار تجاری، صفحهٔ مدلِ همان صدا را بررسی کنید."},
}
DEFAULT_VOICES = {
    "piper": {"fa": "fa_IR-gyro-medium", "en": "en_US-lessac-medium"},
    "edge": {"fa": "fa-IR-DilaraNeural", "en": "en-US-JennyNeural"},
    "moss": {"fa": "lora", "en": "lora"},
    "pocket": {"fa": "", "en": ""},
    "fake": {"fa": "fake", "en": "fake"},
}


def licence_of(engine_id: str) -> dict:
    """{engine, commercial, badge, warning, warning_text: {en, fa}} for an engine id."""
    info = LICENCE_INFO.get(engine_id, {"commercial": "unknown", "badge": "unknown", "warning": None})
    key = info.get("warning")
    return {"engine": engine_id, **info, "warning_text": WARNING_TEXT.get(key) if key else None}


@dataclass
class TTSResult:
    path: Path
    seconds: float
    engine: str
    voice: str
    sample_rate: int
    render_seconds: float = 0.0

    @property
    def licence(self) -> dict:
        return licence_of(self.engine)


def estimate_seconds(text: str, language: str = "fa") -> float:
    words = max(1, len(text.split()))
    return round(words / WORDS_PER_SECOND.get(language[:2], 2.5) + 0.3, 2)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


class TTSProvider(abc.ABC):
    id = "base"
    label = ""
    resource = "cpu"
    licence = ""
    languages: tuple[str, ...] = ("fa", "en")
    online = False                   # needs the internet
    needs_reference = False          # speaks in the voice of a reference recording

    def voices(self, language: str = "fa") -> list[dict]:
        """[{id, label, gender, language}] the engine can speak in right now (best effort, never raises)."""
        return []

    def licence_info(self) -> dict:
        return licence_of(self.id)

    @abc.abstractmethod
    def available(self) -> tuple[bool, str]:
        ...

    @abc.abstractmethod
    def synthesize(self, text: str, out_path: Path, *, voice: str | None = None, language: str = "fa",
                   seed: int | None = None, reference: str | None = None) -> TTSResult:
        ...


class FakeTTS(TTSProvider):
    """Speech-shaped synthetic audio (bursts per word); duration follows the reading speed. Pure Python, no models."""

    id, label, resource, licence = "fake", "Fake (آزمایشی)", "cpu", "n/a"

    def available(self) -> tuple[bool, str]:
        return True, "synthetic audio for tests"

    def voices(self, language: str = "fa") -> list[dict]:
        return [{"id": "fake", "label": "Fake", "gender": "", "language": language}]

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        t0 = time.time()
        rate = 24000
        words = max(1, len(text.split()))
        dur = estimate_seconds(text, language)
        n = int(dur * rate)
        per_word = n / words
        frames = bytearray()
        for i in range(n):
            w_pos = (i % per_word) / per_word
            env = math.sin(math.pi * min(1.0, w_pos / 0.85)) if w_pos < 0.85 else 0.0
            f = 140 + 40 * ((i // int(per_word)) % 5)
            v = 0.28 * env * math.sin(2 * math.pi * f * i / rate) + 0.08 * env * math.sin(2 * math.pi * f * 2.7 * i / rate)
            frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        return TTSResult(out_path, n / rate, self.id, voice or "fake", rate, time.time() - t0)


class PiperTTS(TTSProvider):
    id, label, resource, licence = "piper", "Piper (آفلاین، CPU)", "cpu", "MIT (engine); each voice has its own licence - see docs/MODELS.md"

    def __init__(self, voice: str | None = None):
        self.voice = voice or str(settings_store.effective("piper_voice"))

    def _model(self, voice: str) -> Path:
        return runtime.models_root() / "piper" / f"{voice}.onnx"

    def voices(self, language: str = "fa") -> list[dict]:
        folder = runtime.models_root() / "piper"
        out = []
        for f in sorted(folder.glob("*.onnx")) if folder.is_dir() else []:
            if not f.with_suffix(".onnx.json").exists():
                continue
            lang = f.stem.split("_")[0].lower()
            if language and lang != language[:2].lower():
                continue
            out.append({"id": f.stem, "label": f.stem, "gender": "", "language": lang})
        return out

    def available(self) -> tuple[bool, str]:
        exe = runtime.find_tool("piper")
        if not exe:
            return False, "piper.exe not found (tools\\piper)"
        m = self._model(self.voice)
        if not m.exists() or not m.with_suffix(".onnx.json").exists():
            return False, f"voice {self.voice} is not downloaded (models\\piper)"
        return True, f"{exe} / {self.voice}"

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        voice = voice or self.voice
        ok, detail = self.available() if voice == self.voice else (True, "")
        exe = runtime.find_tool("piper")
        if not ok or not exe:
            raise ProviderError(f"Piper unavailable: {detail}", retryable=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        try:
            p = subprocess.run([exe, "--model", str(self._model(voice)), "--output_file", str(out_path)], input=text.encode("utf-8"),
                               capture_output=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            raise ProviderError(f"Piper failed: {e}") from e
        if p.returncode != 0 or not out_path.exists():
            raise ProviderError("Piper failed: " + p.stderr.decode("utf-8", "replace")[-200:])
        w = wave.open(str(out_path), "rb")
        rate = w.getframerate()
        w.close()
        return TTSResult(out_path, wav_duration(out_path), self.id, voice, rate, time.time() - t0)


class MossTTS(TTSProvider):
    id, label, resource, licence = "moss", "MOSS-TTS + LoRA فارسی (GPU)", "gpu", "Apache-2.0 (per Qasem manifest); verify - docs/MODELS.md"

    needs_reference = True

    def __init__(self, url: str | None = None):
        from instai.providers.audio import services

        configured = url or runtime.moss_tts_url()
        self.managed = not configured          # no URL set: InstAI runs its own copy of the server on demand
        self.url = (configured or services.service_url("moss")).rstrip("/")

    def voices(self, language: str = "fa") -> list[dict]:
        return [{"id": "lora", "label": "Persian LoRA default voice", "gender": "female", "language": language}]

    def available(self) -> tuple[bool, str]:
        try:
            j = requests.get(self.url + "/health", timeout=2).json()
            if j.get("status") == "ready":
                return True, "status=ready"
            detail = f"status={j.get('status')}"
        except Exception as e:  # noqa: BLE001
            detail = type(e).__name__
        if self.managed:
            from instai.providers.audio import services

            if services.installed("moss"):
                return True, "installed; started on demand"
            return False, "MOSS-TTS is not installed (Download-Models.bat --only moss-tts) and no server URL is set"
        return False, detail

    def default_reference(self) -> str | None:
        p = runtime.models_root() / "moss-tts" / "persian-lora" / "ref.wav"
        return str(p) if p.exists() else None

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        ref = reference or (voice[4:] if voice and voice.startswith("ref:") else None) or self.default_reference()
        if not ref:
            raise ProviderError("MOSS-TTS needs a reference voice file", retryable=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if self.managed:
            from instai.providers.audio import services

            services.MANAGER.ensure_ready("moss")
        t0 = time.time()
        try:
            r = requests.post(self.url + "/run", json={"text": text, "reference": ref, "seed": seed, "out": str(out_path)}, timeout=900)
            r.raise_for_status()
            j = r.json()
        except requests.RequestException as e:
            raise ProviderError(f"MOSS-TTS request failed: {type(e).__name__}") from e
        if not j.get("ok") or not out_path.exists():
            raise ProviderError("MOSS-TTS returned no audio")
        return TTSResult(out_path, wav_duration(out_path), self.id, voice or "persian-lora", int(j.get("sample_rate") or 24000), time.time() - t0)


class PocketTTS(TTSProvider):
    """Pocket-TTS through the voice-kit gateway (POST /api/voice/tts). NON-COMMERCIAL licence: see LICENCE_INFO."""

    id, label, resource, licence = "pocket", "Pocket-TTS (فقط غیرتجاری)", "cpu", "CC-BY-NC-4.0 - NON-COMMERCIAL"
    languages = ("fa",)

    def __init__(self, url: str | None = None):
        self.url = (url or runtime.pocket_url()).rstrip("/")

    def _engines(self) -> dict:
        r = requests.get(self.url + "/api/voice/engines", timeout=3)
        r.raise_for_status()
        return r.json()

    def available(self) -> tuple[bool, str]:
        if not self.url:
            return False, "Pocket-TTS gateway URL not set (Settings)"
        try:
            j = self._engines()
        except Exception as e:  # noqa: BLE001
            return False, type(e).__name__
        ok = any(isinstance(x, dict) and x.get("id") == "pocket" and x.get("available") for x in j.get("engines") or [])
        return ok, "gateway up" if ok else "gateway up but the Pocket-TTS model is missing"

    def voices(self, language: str = "fa") -> list[dict]:
        try:
            r = requests.get(self.url + "/api/voice/voices", timeout=3)
            rows = r.json() if r.status_code == 200 else []
        except Exception:  # noqa: BLE001
            rows = []
        rows = rows.get("voices", rows) if isinstance(rows, dict) else rows
        return [{"id": str(v.get("id")), "label": v.get("name") or str(v.get("id")), "gender": v.get("gender") or "", "language": "fa"}
                for v in rows if isinstance(v, dict) and v.get("id")]

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        body = {"text": text}
        if voice:
            body["voice"] = voice
        if seed is not None:
            body["seed"] = str(seed)
        t0 = time.time()
        try:
            r = requests.post(self.url + "/api/voice/tts", json=body, timeout=900)
        except requests.RequestException as e:
            raise ProviderError(f"Pocket-TTS gateway not reachable: {type(e).__name__}") from e
        if r.status_code != 200 or len(r.content) < 64:
            raise ProviderError(f"Pocket-TTS failed (HTTP {r.status_code}): {r.text[:160]}", retryable=r.status_code >= 500)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(r.content)
        w = wave.open(str(out_path), "rb")
        rate = w.getframerate()
        w.close()
        return TTSResult(out_path, wav_duration(out_path), self.id, voice or "pocket", rate, time.time() - t0)


EDGE_VOICES = {
    "fa": [("fa-IR-DilaraNeural", "Dilara", "female"), ("fa-IR-FaridNeural", "Farid", "male")],
    "en": [("en-US-JennyNeural", "Jenny", "female"), ("en-US-GuyNeural", "Guy", "male"),
           ("en-GB-SoniaNeural", "Sonia", "female"), ("en-GB-RyanNeural", "Ryan", "male")],
}


class EdgeTTS(TTSProvider):
    """Microsoft Edge neural voices through the `edge-tts` package (online, unofficial endpoint). Not for commercial use."""

    id, label, resource, licence = "edge", "Edge TTS (آنلاین، غیررسمی)", "net", "unofficial online endpoint - not licensed for commercial use"
    online = True

    def available(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "the edge-tts package is not installed (pip install edge-tts)"
        return True, "edge-tts installed (needs internet)"

    def voices(self, language: str = "fa") -> list[dict]:
        return [{"id": v, "label": n, "gender": g, "language": language[:2]} for v, n, g in EDGE_VOICES.get(language[:2], [])]

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        import asyncio
        import shutil
        import tempfile

        try:
            import edge_tts
        except ImportError as e:
            raise ProviderError("edge-tts is not installed", retryable=False, code="not_ready") from e
        from instai.render import ffmpeg

        voice = voice or DEFAULT_VOICES["edge"].get(language[:2], DEFAULT_VOICES["edge"]["fa"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        mp3 = Path(tempfile.mkdtemp(prefix="edge-")) / "edge.mp3"
        t0 = time.time()
        try:
            asyncio.run(edge_tts.Communicate(text, voice).save(str(mp3)))
        except Exception as e:  # noqa: BLE001 - network, endpoint changes, unknown voice
            raise ProviderError(f"Edge TTS failed ({type(e).__name__}: {str(e)[:120]}); it is an unofficial online service") from e
        if not mp3.exists() or mp3.stat().st_size < 64:
            raise ProviderError("Edge TTS returned no audio")
        ffmpeg.run(["-i", str(mp3), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out_path)])
        shutil.rmtree(mp3.parent, ignore_errors=True)
        return TTSResult(out_path, wav_duration(out_path), self.id, voice, 24000, time.time() - t0)


ENGINE_IDS = ("moss", "piper", "pocket", "edge", "fake")


def get_tts(engine: str | None = None) -> TTSProvider:
    engine = engine or str(settings_store.effective("tts_engine") or "auto")
    if engine == "fake":
        return FakeTTS()
    if engine == "piper":
        return PiperTTS()
    if engine == "moss":
        return MossTTS()
    if engine == "pocket":
        return PocketTTS()
    if engine == "edge":
        return EdgeTTS()
    # auto: only engines licensed for commercial use; Pocket and Edge are never picked automatically
    for cand in (MossTTS(), PiperTTS()):
        if cand.available()[0]:
            return cand
    raise ProviderError("No speech engine is ready (start the MOSS-TTS server or install a Piper voice)", retryable=False,
                        code="not_ready")


def all_engines() -> list[TTSProvider]:
    return [MossTTS(), PiperTTS(), PocketTTS(), EdgeTTS()]


def tts_status() -> list[dict]:
    hints = {"piper": "Download-Models.bat --only piper", "moss": "Download-Models.bat --only moss-tts؛ سپس سرور MOSS را اجرا کنید.",
             "pocket": "Pocket-TTS از دروازهٔ کیت صدا (Settings > Pocket URL) گفتار می‌دهد؛ فقط غیرتجاری.",
             "edge": "pip install edge-tts (اینترنت لازم است)"}
    out = []
    for p in all_engines():
        ok, detail = p.available()
        lic = p.licence_info()
        out.append({"id": f"tts_{p.id}", "label": p.label, "status": "ok" if ok else "missing", "detail": detail,
                    "data": {"engine": p.id, "resource": p.resource, "licence": p.licence, "commercial": lic["commercial"],
                             "warning": lic["warning"], "online": p.online}, "hint": "" if ok else hints.get(p.id, "")})
    return out
