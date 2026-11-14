"""Technical quality checks on a rendered video: duration, resolution, audio, loudness, true peak, black and frozen frames.

Every row is `{name, level: ok|warn|fail|info, value, message (Persian), message_en}` - the quality panel shows the language the owner reads in. The sound checks that
need the episode's parts (echo, music over the voice, phase) live in `render/audioqc.py` and are appended by `production/pipeline.run_qc`."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import ffmpeg
from .audioqc import fd

#: a final render that was settled (render/loudness.py) must be this close to its target; an old render that was not keeps the old, looser limit
SETTLED_TOLERANCE_LU = 1.0
UNSETTLED_TOLERANCE_LU = 3.0
TRUE_PEAK_CEILING_DB = -1.0


def _filter_scan(path: Path, vf: str) -> str:
    ff, _ = ffmpeg.binaries()
    p = subprocess.run([ff, "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf", vf, "-f", "null", "-"], capture_output=True, text=True,
                       timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return p.stderr


def technical(path: Path, *, expected_duration: float = 0, width: int | None = None, height: int | None = None, target_lufs: float = -16.0,
              loudness: float | None = None, settled: dict | None = None) -> dict:
    """Each check: {name, level: ok|warn|fail|info, value, message (Persian), message_en}. `settled` = what `loudness.settle` reported for this file (kept on the
    asset's provenance): it adds the before/after numbers and the true peak to the loudness rows."""
    info = ffmpeg.probe(path)
    checks: list[dict] = []

    def add(name, level, value, msg, msg_en):
        checks.append({"name": name, "level": level, "value": value, "message": msg, "message_en": msg_en})

    add("video_stream", "ok" if info["has_video"] and info["vcodec"] == "h264" else "fail", info["vcodec"],
        "ویدئو با کدک H.264" if info["has_video"] else "جریان ویدئو وجود ندارد", "Video with the H.264 codec" if info["has_video"] else "There is no video stream")
    add("audio_stream", "ok" if info["has_audio"] else "fail", info["acodec"], "صدا وجود دارد" if info["has_audio"] else "صدا وجود ندارد",
        "There is sound" if info["has_audio"] else "There is no sound")
    if expected_duration:
        diff = abs(info["duration"] - expected_duration)
        add("duration", "ok" if diff <= 1.0 else "warn", info["duration"], f"مدت {info['duration']:.1f} ثانیه (انتظار {expected_duration:.1f})",
            f"Duration {info['duration']:.1f} s (expected {expected_duration:.1f})")
    if width and height:
        ok = (info["width"], info["height"]) == (width, height)
        add("resolution", "ok" if ok else "fail", f"{info['width']}x{info['height']}", f"وضوح {info['width']}×{info['height']}", f"Resolution {info['width']}x{info['height']}")
    if info["fps"]:
        add("fps", "ok" if 10 <= info["fps"] <= 61 else "warn", info["fps"], f"{info['fps']} فریم بر ثانیه", f"{info['fps']} frames per second")
    lufs = loudness if loudness is not None else ffmpeg.measure_loudness(path)
    if lufs is not None:
        tol = SETTLED_TOLERANCE_LU if settled and settled.get("target") is not None else UNSETTLED_TOLERANCE_LU
        ok = abs(lufs - target_lufs) <= tol
        value: object = lufs
        fa = f"بلندیِ صدا {fd(round(lufs, 1))} LUFS (هدف {fd(round(target_lufs))})"
        en = f"Loudness {lufs:.1f} LUFS (target {target_lufs:.0f})"
        if settled and settled.get("before") is not None:
            value = {"lufs": lufs, "target": target_lufs, "before": settled.get("before"), "adjusted": bool(settled.get("adjusted")), "rounds": settled.get("rounds", 0),
                     "gain_db": settled.get("gain_db", 0.0)}
            if settled.get("adjusted"):
                fa += f"؛ بعد از ساخت اندازه‌گیری و اصلاح شد (پیش از اصلاح {fd(settled['before'])}، {fd(settled.get('rounds', 0))} دور)"
                en += f"; measured after the render and corrected (before {settled['before']}, {settled.get('rounds', 0)} round(s))"
            else:
                fa += "؛ بعد از ساخت اندازه‌گیری شد و در محدودهٔ هدف بود"
                en += "; measured after the render and already on target"
        add("loudness", "ok" if ok else "warn", value, fa, en)
    tp = (settled or {}).get("tp")
    if tp is not None:
        ok = tp <= TRUE_PEAK_CEILING_DB + 0.05
        add("true_peak", "ok" if ok else "warn", tp, f"اوجِ صدا {fd(tp)} dBTP (سقف {fd(TRUE_PEAK_CEILING_DB)})" + ("" if ok else "؛ بالاتر از سقف است و ممکن است در پلتفرم‌ها بشکند"),
            f"True peak {tp} dBTP (ceiling {TRUE_PEAK_CEILING_DB})" + ("" if ok else "; above the ceiling, it may distort on the platforms"))
    try:
        err = _filter_scan(path, "blackdetect=d=0.5:pix_th=0.08")
        blacks = re.findall(r"black_start:([\d.]+)", err)
        add("black_frames", "warn" if blacks else "ok", len(blacks), f"{len(blacks)} بازه‌ی تصویر سیاه" if blacks else "بدون تصویر سیاه",
            f"{len(blacks)} black stretch(es)" if blacks else "No black frames")
        err = _filter_scan(path, "freezedetect=n=-60dB:d=2.5")
        freezes = re.findall(r"freeze_start:\s*([\d.]+)", err)
        add("frozen_frames", "info" if freezes else "ok", len(freezes), f"{len(freezes)} بازه‌ی ثابت (برای شات‌های بی‌حرکت طبیعی است)" if freezes else "بدون بازه‌ی ثابت",
            f"{len(freezes)} still stretch(es) (normal for shots without motion)" if freezes else "No frozen stretches")
    except Exception:  # noqa: BLE001 - analysis filters are best effort
        pass
    return {"checks": checks, "ok": not any(c["level"] == "fail" for c in checks)}
