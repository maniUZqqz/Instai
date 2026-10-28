"""Technical quality checks on a rendered video: duration, resolution, audio, loudness, black and frozen frames."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import ffmpeg


def _filter_scan(path: Path, vf: str) -> str:
    ff, _ = ffmpeg.binaries()
    p = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf", vf, "-f", "null", "-"], capture_output=True, text=True,
                       timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return p.stderr


def technical(path: Path, *, expected_duration: float = 0, width: int | None = None, height: int | None = None, target_lufs: float = -16.0,
              loudness: float | None = None) -> dict:
    """Each check: {name, level: ok|warn|fail|info, value, message (Persian)}."""
    info = ffmpeg.probe(path)
    checks: list[dict] = []

    def add(name, level, value, msg):
        checks.append({"name": name, "level": level, "value": value, "message": msg})

    add("video_stream", "ok" if info["has_video"] and info["vcodec"] == "h264" else "fail", info["vcodec"], "ویدئو با کدک H.264" if info["has_video"] else "جریان ویدئو وجود ندارد")
    add("audio_stream", "ok" if info["has_audio"] else "fail", info["acodec"], "صدا وجود دارد" if info["has_audio"] else "صدا وجود ندارد")
    if expected_duration:
        diff = abs(info["duration"] - expected_duration)
        add("duration", "ok" if diff <= 1.0 else "warn", info["duration"], f"مدت {info['duration']:.1f} ثانیه (انتظار {expected_duration:.1f})")
    if width and height:
        ok = (info["width"], info["height"]) == (width, height)
        add("resolution", "ok" if ok else "fail", f"{info['width']}x{info['height']}", f"وضوح {info['width']}×{info['height']}")
    if info["fps"]:
        add("fps", "ok" if 10 <= info["fps"] <= 61 else "warn", info["fps"], f"{info['fps']} فریم بر ثانیه")
    lufs = loudness if loudness is not None else ffmpeg.measure_loudness(path)
    if lufs is not None:
        ok = abs(lufs - target_lufs) <= 3.0
        add("loudness", "ok" if ok else "warn", lufs, f"بلندیِ صدا {lufs:.1f} LUFS (هدف {target_lufs:.0f})")
    try:
        err = _filter_scan(path, "blackdetect=d=0.5:pix_th=0.08")
        blacks = re.findall(r"black_start:([\d.]+)", err)
        add("black_frames", "warn" if blacks else "ok", len(blacks), f"{len(blacks)} بازه‌ی تصویر سیاه" if blacks else "بدون تصویر سیاه")
        err = _filter_scan(path, "freezedetect=n=-60dB:d=2.5")
        freezes = re.findall(r"freeze_start:\s*([\d.]+)", err)
        add("frozen_frames", "info" if freezes else "ok", len(freezes), f"{len(freezes)} بازه‌ی ثابت (برای شات‌های بی‌حرکت طبیعی است)" if freezes else "بدون بازه‌ی ثابت")
    except Exception:  # noqa: BLE001 - analysis filters are best effort
        pass
    return {"checks": checks, "ok": not any(c["level"] == "fail" for c in checks)}
