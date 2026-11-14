"""Synthetic test sound that behaves like speech where the audio checks care: syllable bursts of noise shaped by moving formants, with pauses between
sentences. Deterministic (seeded), no model, no recorded voice. Used by the tests, by the benchmark script and by the PC self-test rows.

Why not the fake narration engine: `FakeTTS` makes sine bursts, which are strictly periodic. A periodic signal correlates with itself at many lags and is
never a fair test of "is the same speech playing twice" (see `audioqc.echo_report`, which says so on purpose); noise-excited syllables are.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 16000


def speechlike(seconds: float, *, seed: int = 1, sr: int = SR, level_db: float = -22.0, pause_every: int = 6, pause_s: float = 0.55) -> np.ndarray:
    """Mono float32 signal of `seconds`: 0.16-0.30 s syllables of formant-shaped noise, a pause of `pause_s` after every `pause_every` syllables (the quiet
    stretches that make a one-pass loudness filter miss its target). RMS of the speaking parts is `level_db` dBFS."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    out = np.zeros(n, dtype=np.float32)
    pos, k = int(0.12 * sr), 0
    while pos < n:
        length = int(rng.uniform(0.16, 0.30) * sr)
        length = min(length, n - pos)
        if length < 64:
            break
        spec = np.fft.rfft(rng.standard_normal(length))
        freqs = np.fft.rfftfreq(length, 1.0 / sr)
        f1, f2 = rng.uniform(300, 800), rng.uniform(900, 2600)
        shape = np.exp(-0.5 * ((freqs - f1) / 160.0) ** 2) + 0.6 * np.exp(-0.5 * ((freqs - f2) / 300.0) ** 2) + 0.03
        syl = np.fft.irfft(spec * shape, n=length) * np.hanning(length)
        out[pos:pos + length] += syl.astype(np.float32)
        pos += length + int(rng.uniform(0.02, 0.06) * sr)
        k += 1
        if pause_every and k % pause_every == 0:
            pos += int(pause_s * sr)
    active = np.abs(out) > 1e-6
    if active.any():
        rms = float(np.sqrt(np.mean(out[active].astype(np.float64) ** 2)))
        out *= np.float32(10 ** (level_db / 20) / (rms + 1e-12))
    return np.clip(out, -1.0, 1.0)


def pulse_music(seconds: float, *, sr: int = SR, level_db: float = -24.0, freq: float = 220.0) -> np.ndarray:
    """A steady two-chord pad with a slow pulse: a stand-in for a music bed (tonal, rhythmic, nothing like speech)."""
    t = np.arange(int(seconds * sr)) / sr
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t)
    sig = np.sin(2 * np.pi * freq * t) + 0.7 * np.sin(2 * np.pi * freq * 1.5 * t) + 0.5 * np.sin(2 * np.pi * freq * 2.0 * t)
    sig = (sig * env).astype(np.float32)
    sig *= np.float32(10 ** (level_db / 20) / (float(np.sqrt(np.mean(sig.astype(np.float64) ** 2))) + 1e-12))
    return sig


def delayed_copy(x: np.ndarray, delay_s: float, gain: float = 1.0, sr: int = SR) -> np.ndarray:
    """`x` plus a copy of itself `delay_s` later at `gain` (the doubled-narration case); the result is the length of `x`."""
    d = int(delay_s * sr)
    y = x.astype(np.float32).copy()
    if 0 < d < len(x):
        y[d:] += np.float32(gain) * x[:-d]
    return y


def write_wav(path, data: np.ndarray, sr: int = SR) -> Path:
    """16-bit PCM wav; a 2-D array (n, 2) writes stereo."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.clip(np.asarray(data, dtype=np.float32), -1.0, 1.0)
    pcm = (arr * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def synthetic_video(out_mp4, wav, *, ffmpeg_exe: str, seconds: float = 3.0, size: str = "270x480", fps: int = 15, loudnorm_to: float | None = None,
                    stereo: bool = True, gain_db: float = 0.0) -> Path:
    """A small mp4 (a moving test picture + the given sound as AAC). `loudnorm_to` runs the same ONE-pass `loudnorm` the assembly uses
    (`I=<x>:TP=-1.5:LRA=11`), so the file starts where a real render starts: close to the target but not on it. `gain_db` makes a hot file (peaks above full scale)."""
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    af = "aresample=48000" + (",aformat=channel_layouts=stereo" if stereo else "") + (f",volume={gain_db}dB" if gain_db else "")
    if loudnorm_to is not None:
        af += f",loudnorm=I={loudnorm_to}:TP=-1.5:LRA=11,aresample=48000"
    cmd = [ffmpeg_exe, "-y", "-v", "error", "-nostdin", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}", "-i", str(wav), "-af", af,
           "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{seconds}", "-movflags", "+faststart",
           str(out_mp4)]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0 or not out_mp4.is_file():
        raise RuntimeError("synthetic video failed: " + (done.stderr or "")[-300:])
    return out_mp4
