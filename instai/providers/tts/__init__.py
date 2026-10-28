"""Text-to-speech adapters: Piper (CPU, offline), MOSS-TTS server (GPU) and a fake engine for tests/demo.

MOSS server protocol adapted from Qasem processing-server/audio/_common.py + moss_tts_server.py
(GET /health, POST /run {text, reference, seed, out} -> {ok, seconds}).
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


@dataclass
class TTSResult:
    path: Path
    seconds: float
    engine: str
    voice: str
    sample_rate: int
    render_seconds: float = 0.0


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

    def __init__(self, url: str | None = None):
        self.url = (url or runtime.moss_tts_url()).rstrip("/")

    def available(self) -> tuple[bool, str]:
        if not self.url:
            return False, "MOSS-TTS server URL not set (Settings)"
        try:
            j = requests.get(self.url + "/health", timeout=2).json()
            return (j.get("status") == "ready"), f"status={j.get('status')}"
        except Exception as e:  # noqa: BLE001
            return False, type(e).__name__

    def default_reference(self) -> str | None:
        p = runtime.models_root() / "moss-tts" / "persian-lora" / "ref.wav"
        return str(p) if p.exists() else None

    def synthesize(self, text, out_path, *, voice=None, language="fa", seed=None, reference=None) -> TTSResult:
        ref = reference or self.default_reference()
        if not ref:
            raise ProviderError("MOSS-TTS needs a reference voice file", retryable=False)
        out_path.parent.mkdir(parents=True, exist_ok=True)
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


def get_tts(engine: str | None = None) -> TTSProvider:
    engine = engine or str(settings_store.effective("tts_engine") or "auto")
    if engine == "fake":
        return FakeTTS()
    if engine == "piper":
        return PiperTTS()
    if engine == "moss":
        return MossTTS()
    for cand in (MossTTS(), PiperTTS()):
        if cand.available()[0]:
            return cand
    raise ProviderError("No speech engine is ready (start the MOSS-TTS server or install a Piper voice)", retryable=False,
                        code="not_ready")


def tts_status() -> list[dict]:
    out = []
    for p, hint in ((PiperTTS(), "Download-Models.bat --only piper"), (MossTTS(), "Download-Models.bat --only moss-tts؛ سپس سرور MOSS را اجرا کنید.")):
        ok, detail = p.available()
        out.append({"id": f"tts_{p.id}", "label": p.label, "status": "ok" if ok else "missing", "detail": detail,
                    "data": {"engine": p.id, "resource": p.resource, "licence": p.licence}, "hint": "" if ok else hint})
    return out
