"""Mouth shapes (visemes) from narration audio.

* Rhubarb Lip Sync (MIT): `rhubarb -f json` gives cues of the 9 standard shapes A-H, X. English uses its PocketSphinx recogniser
  (better with the dialogue text); every other language (Persian) uses the language-independent `phonetic` recogniser.
* Fallback: an amplitude-driven mouth (loudness per 20 ms -> how wide the mouth opens). Always available, no binary, deterministic.

A cue list is [(start, end, shape)] covering the audio; `shape_at()` looks one up. See docs/DECISIONS.md for what was measured.
"""
from __future__ import annotations

import array
import bisect
import hashlib
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path

from instai.core import runtime

SHAPES = "ABCDEFGHX"
Cue = tuple[float, float, str]


# ------------------------------------------------------------------ lookup

def shape_at(cues: list[Cue], t: float, starts: list[float] | None = None) -> str:
    if not cues:
        return "X"
    starts = starts if starts is not None else [c[0] for c in cues]
    i = bisect.bisect_right(starts, t) - 1
    if i < 0 or t >= cues[i][1] + 1e-9:
        return "X"
    return cues[i][2]


def merge(cues: list[Cue]) -> list[Cue]:
    out: list[Cue] = []
    for s, e, v in cues:
        if e <= s:
            continue
        if out and out[-1][2] == v and abs(out[-1][1] - s) < 1e-6:
            out[-1] = (out[-1][0], e, v)
        else:
            out.append((round(s, 4), round(e, 4), v))
    return out


# ------------------------------------------------------------------ amplitude fallback

def read_mono(path: str | Path, max_seconds: float = 600.0) -> tuple[list[float], int]:
    """Samples in -1..1 (mono mix) and the sample rate of a WAV file (16-bit PCM or 8-bit)."""
    with wave.open(str(path), "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(min(w.getnframes(), int(max_seconds * rate)))
    if width == 2:
        a = array.array("h", raw[: len(raw) // 2 * 2])
        scale = 32768.0
    elif width == 1:
        a = array.array("h", [(b - 128) << 8 for b in raw])
        scale = 32768.0
    else:
        raise ValueError("only 8/16-bit WAV is supported for lip-sync")
    if ch > 1:
        a = array.array("h", [int(sum(a[i:i + ch]) / ch) for i in range(0, len(a) - ch + 1, ch)])
    return [x / scale for x in a], rate


def envelope(samples: list[float], rate: int, window: float = 0.02) -> list[float]:
    n = max(1, int(rate * window))
    return [math.sqrt(sum(x * x for x in samples[i:i + n]) / max(1, len(samples[i:i + n]))) for i in range(0, len(samples), n)]


def amplitude_cues(path: str | Path, window: float = 0.02) -> list[Cue]:
    samples, rate = read_mono(path)
    env = envelope(samples, rate, window)
    if not env:
        return []
    loud = sorted(env)
    ref = loud[int(len(loud) * 0.95)] or max(loud) or 1.0
    floor = 0.10
    shapes: list[str] = []
    flip = 0
    prev = "X"
    for e in env:
        lvl = e / ref
        if lvl < floor:
            s = "X"
        elif lvl < 0.30:
            s = "B"
        elif lvl < 0.55:
            s = "C"
        elif lvl < 0.80:
            if prev not in ("C", "E"):
                flip += 1
            s = "E" if flip % 2 else "C"
        else:
            s = "D"
        shapes.append(s)
        prev = s
    # hold each open shape for at least 3 windows (60 ms) so the mouth does not flicker
    hold = 3
    i = 0
    while i < len(shapes):
        j = i
        while j < len(shapes) and shapes[j] == shapes[i]:
            j += 1
        if shapes[i] != "X" and j - i < hold and i > 0:
            for k in range(i, j):
                shapes[k] = shapes[i - 1] if shapes[i - 1] != "X" else shapes[i]
        i = j
    return merge([(k * window, (k + 1) * window, s) for k, s in enumerate(shapes)])


# ------------------------------------------------------------------ Rhubarb

def rhubarb_exe() -> str | None:
    return runtime.find_tool("rhubarb")


def rhubarb_cues(path: str | Path, *, language: str = "fa", text: str = "", timeout: float = 300.0) -> list[Cue]:
    """Run Rhubarb and parse its JSON. Raises RuntimeError with the reason when it cannot produce cues."""
    exe = rhubarb_exe()
    if not exe:
        raise RuntimeError("rhubarb is not installed (Download-Models.bat --only rhubarb)")
    recogniser = "pocketSphinx" if language[:2] == "en" else "phonetic"
    tmp = Path(tempfile.mkdtemp(prefix="rhubarb-"))
    try:
        out = tmp / "cues.json"
        cmd = [exe, "-f", "json", "-r", recogniser, "--extendedShapes", "GHX", "-q", "-o", str(out)]
        if recogniser == "pocketSphinx" and text.strip() and text.isascii():
            (tmp / "dialog.txt").write_text(text, encoding="ascii", errors="ignore")
            cmd += ["-d", str(tmp / "dialog.txt")]
        cmd.append(str(path))
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode != 0 or not out.exists():
            raise RuntimeError("rhubarb failed: " + (p.stderr or p.stdout)[-300:])
        data = json.loads(out.read_text(encoding="utf-8"))
        cues = [(float(c["start"]), float(c["end"]), str(c["value"])) for c in data.get("mouthCues", []) if str(c.get("value")) in SHAPES]
        if not cues:
            raise RuntimeError("rhubarb returned no mouth cues")
        return merge(cues)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise RuntimeError(f"rhubarb could not run: {e}") from e
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def visemes(path: str | Path, *, language: str = "fa", text: str = "", engine: str = "auto") -> dict:
    """{"cues", "engine", "note"}. engine: auto (Rhubarb if installed, else amplitude) | rhubarb | amplitude."""
    note = ""
    if engine in ("auto", "rhubarb") and rhubarb_exe():
        try:
            return {"cues": rhubarb_cues(path, language=language, text=text), "engine": "rhubarb",
                    "note": "recogniser=" + ("pocketSphinx" if language[:2] == "en" else "phonetic")}
        except RuntimeError as e:
            note = f"Rhubarb failed ({e}); amplitude-driven mouth used instead"
            if engine == "rhubarb":
                raise
    elif engine == "rhubarb":
        raise RuntimeError("rhubarb is not installed")
    else:
        note = "Rhubarb is not installed; amplitude-driven mouth used" if engine == "auto" else ""
    return {"cues": amplitude_cues(path), "engine": "amplitude", "note": note}


def cache_key(path: str | Path, language: str, engine: str) -> str:
    h = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    return f"{h}-{language[:2]}-{engine}"
