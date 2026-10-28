"""Sound-effect and music generators (MOSS-SoundEffect, ACE-Step 1.5) plus the on-demand local servers (`services`).
Protocols follow the NMarketing agent (Qasem processing-server/agent.py h_voice_sfx / h_voice_music)."""
from __future__ import annotations

import abc
import math
import struct
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import requests

from instai.core import settings_store
from instai.providers.base import ProviderError

from . import services


@dataclass
class AudioResult:
    path: Path
    seconds: float
    engine: str
    render_seconds: float
    licence: str


def write_tone(path: Path, seconds: float, freq: float = 220.0, rate: int = 24000) -> Path:
    """Deterministic test audio (demo mode / fake engines): a slow pulsing tone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(max(0.2, seconds) * rate)
    frames = bytearray()
    for i in range(n):
        env = 0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * i / rate)
        frames += struct.pack("<h", int(0.18 * env * math.sin(2 * math.pi * freq * i / rate) * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


class AudioGenerator(abc.ABC):
    id = "base"
    label = ""
    kind = "sfx"            # sfx | music
    resource = "gpu"
    licence = ""
    max_seconds = 30.0

    @abc.abstractmethod
    def available(self) -> tuple[bool, str]: ...

    @abc.abstractmethod
    def generate(self, prompt: str, seconds: float, out_path: Path, *, seed: int | None = None, ctx=None, **kw) -> AudioResult: ...


class FakeAudio(AudioGenerator):
    id, label, resource, licence = "fake", "Fake (test tone)", "cpu", "n/a"

    def __init__(self, kind: str = "sfx"):
        self.kind = kind
        self.max_seconds = 240.0

    def available(self):
        return True, "test tone"

    def generate(self, prompt, seconds, out_path, *, seed=None, ctx=None, **kw):
        t0 = time.time()
        write_tone(out_path, min(seconds, 60.0), freq=330.0 if self.kind == "music" else 660.0)
        return AudioResult(out_path, min(seconds, 60.0), self.id, time.time() - t0, self.licence)


class MossSFX(AudioGenerator):
    """MOSS-SoundEffect v2.0 (Apache-2.0): POST /run {prompt (English), seconds 0.5-30, out, seed, ...} -> wav."""

    id, label, kind, licence = "moss-sfx", "MOSS-SoundEffect v2.0", "sfx", "Apache-2.0"
    max_seconds = 30.0

    def available(self):
        h = services.health("sfx")
        if h["status"] == "ready":
            return True, "server ready"
        if services.installed("sfx"):
            return True, "installed; started on demand"
        return False, "MOSS-SoundEffect is not installed (Download-Models.bat --only moss-sfx)"

    def generate(self, prompt, seconds, out_path, *, seed=None, ctx=None, **kw):
        url = services.MANAGER.ensure_ready("sfx", ctx)
        t0 = time.time()
        seconds = max(0.5, min(self.max_seconds, float(seconds)))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.post(url + "/run", json={"prompt": prompt, "seconds": seconds, "out": str(out_path), "seed": seed or 0,
                                                  "steps": kw.get("steps"), "cfg_scale": kw.get("cfg_scale"),
                                                  "negative_prompt": kw.get("negative_prompt") or ""}, timeout=1800)
        except requests.RequestException as e:
            raise ProviderError(f"MOSS-SoundEffect request failed: {type(e).__name__}") from e
        if r.status_code != 200 or not out_path.exists():
            raise ProviderError(f"MOSS-SoundEffect failed (HTTP {r.status_code}): {r.text[:160]}", retryable=r.status_code >= 500)
        services.MANAGER.last_use["sfx"] = time.time()
        return AudioResult(out_path, seconds, self.id, time.time() - t0, self.licence)


class AceStepMusic(AudioGenerator):
    """ACE-Step 1.5 (MIT) through its own REST API: POST /release_task, POST /query_result, GET /v1/audio?path=..."""

    id, label, kind, licence = "acestep", "ACE-Step 1.5 (turbo)", "music", "MIT"
    max_seconds = 240.0

    def available(self):
        h = services.health("music")
        if h["status"] == "ready":
            return True, "server ready"
        if services.installed("music"):
            return True, "installed; started on demand"
        return False, "ACE-Step is not installed (Download-Models.bat --only acestep)"

    @staticmethod
    def _call(url, method, path, body=None, timeout=120):
        r = requests.request(method, url + path, json=body, timeout=timeout)
        j = r.json()
        if isinstance(j, dict) and "data" in j and ("code" in j or "error" in j):
            if j.get("code") not in (None, 200) or j.get("error"):
                raise ProviderError(f"ACE-Step: {j.get('error') or 'code ' + str(j.get('code'))}")
            return j.get("data")
        return j

    def generate(self, prompt, seconds, out_path, *, seed=None, ctx=None, **kw):
        import json

        url = services.MANAGER.ensure_ready("music", ctx)
        seconds = max(10.0, min(self.max_seconds, float(seconds)))
        body = {"prompt": prompt, "lyrics": "[Instrumental]", "instrumental": True, "thinking": False, "use_cot_caption": False,
                "use_cot_language": False, "audio_duration": seconds, "inference_steps": int(kw.get("steps") or 8), "batch_size": 1,
                "audio_format": "wav", "use_random_seed": seed in (None, ""), "seed": int(seed) if seed not in (None, "") else -1}
        if kw.get("bpm"):
            body["bpm"] = int(kw["bpm"])
        t0 = time.time()
        try:
            task = self._call(url, "POST", "/release_task", body)
            task_id = (task or {}).get("task_id") if isinstance(task, dict) else None
            if not task_id:
                raise ProviderError(f"ACE-Step did not accept the task: {str(task)[:200]}")
            end = time.time() + 1800
            while time.time() < end:
                rows = self._call(url, "POST", "/query_result", {"task_id_list": [task_id]}) or []
                row = rows[0] if isinstance(rows, list) and rows else {}
                status = row.get("status") if isinstance(row, dict) else None
                if status == 1:
                    items = row.get("result")
                    items = json.loads(items) if isinstance(items, str) else (items or [])
                    file_url = (items[0] or {}).get("file") if items else None
                    if not file_url:
                        raise ProviderError("ACE-Step finished without a file")
                    data = requests.get(url + file_url if file_url.startswith("/") else file_url, timeout=600)
                    if data.status_code != 200 or len(data.content) < 64:
                        raise ProviderError("ACE-Step returned no audio file")
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(data.content)
                    services.MANAGER.last_use["music"] = time.time()
                    return AudioResult(out_path, seconds, self.id, time.time() - t0, self.licence)
                if status == 2:
                    raise ProviderError(f"ACE-Step failed: {str(row.get('result') or row)[:200]}")
                if ctx is not None:
                    ctx.check()
                time.sleep(0.5 if services.fake_mode() else 2.0)
        except requests.RequestException as e:
            raise ProviderError(f"ACE-Step request failed: {type(e).__name__}") from e
        raise ProviderError("ACE-Step did not finish in time")


def get_generator(kind: str) -> AudioGenerator:
    """kind: sfx | music. Setting `sfx_engine` / `music_engine`: auto | fake | the engine id."""
    key = "sfx_engine" if kind == "sfx" else "music_engine"
    eng = str(settings_store.effective(key) or "auto")
    if eng == "fake":
        return FakeAudio(kind)
    return MossSFX() if kind == "sfx" else AceStepMusic()


def audio_status() -> list[dict]:
    out = []
    for g in (MossSFX(), AceStepMusic()):
        ok, detail = g.available()
        out.append({"id": f"audio_{g.id}", "label": g.label, "status": "ok" if ok else "missing", "detail": detail,
                    "data": {"engine": g.id, "kind": g.kind, "licence": g.licence, "resource": g.resource}, "hint": ""})
    return out
