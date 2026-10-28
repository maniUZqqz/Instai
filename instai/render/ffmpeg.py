"""FFmpeg/ffprobe helpers: locate, probe (explicit metadata for every asset), loudness, cancellable runs with progress."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from instai.core import runtime


class FFmpegError(Exception):
    pass


def binaries() -> tuple[str, str | None]:
    """(ffmpeg, ffprobe). ffprobe is optional: the PyPI-sourced build has none and probe() then parses `ffmpeg -i`."""
    info = runtime.ffmpeg_info()
    if not info["ffmpeg"]:
        raise FFmpegError("ffmpeg not found (START.bat downloads a pinned build into the tools folder)")
    return info["ffmpeg"], info["ffprobe"]


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _frac(s: str | None) -> float | None:
    if not s or "/" not in s:
        return None
    n, d = s.split("/")
    return round(float(n) / float(d), 3) if float(d) else None


def probe(path: str | Path) -> dict:
    """{duration, fps, width, height, vcodec, acodec, has_audio, has_video, size_bytes, bit_rate, sample_rate}"""
    ffmpeg_exe, ffprobe = binaries()
    if ffprobe is None:
        return _probe_without_ffprobe(ffmpeg_exe, Path(path))
    p = subprocess.run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True, timeout=60, creationflags=_flags())
    if p.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {p.stderr[-300:]}")
    j = json.loads(p.stdout)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in j.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = j.get("format", {})
    dur = float(fmt.get("duration") or (v or a or {}).get("duration") or 0)
    return {"duration": round(dur, 3), "fps": _frac((v or {}).get("avg_frame_rate")), "width": (v or {}).get("width"),
            "height": (v or {}).get("height"), "vcodec": (v or {}).get("codec_name", ""), "acodec": (a or {}).get("codec_name", ""),
            "has_audio": a is not None, "has_video": v is not None, "size_bytes": int(fmt.get("size") or 0),
            "bit_rate": int(fmt.get("bit_rate") or 0), "sample_rate": int((a or {}).get("sample_rate") or 0)}


def _probe_without_ffprobe(ffmpeg_exe: str, path: Path) -> dict:
    """Same dict from the banner of `ffmpeg -i file` (used when only ffmpeg.exe is installed)."""
    p = subprocess.run([ffmpeg_exe, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60, creationflags=_flags())
    text = p.stderr
    if "Input #0" not in text:
        raise FFmpegError(f"cannot read {path.name}: {text[-200:]}")
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vline = next((ln for ln in text.splitlines() if "Video:" in ln and "Stream #" in ln), "")
    aline = next((ln for ln in text.splitlines() if "Audio:" in ln and "Stream #" in ln), "")
    wh = re.search(r"[ ,](\d{2,5})x(\d{2,5})[ ,\[]", vline)
    fps = re.search(r"([\d.]+) fps", vline)
    br = re.search(r"bitrate:\s*(\d+) kb/s", text)
    return {"duration": round(dur, 3), "fps": float(fps.group(1)) if fps else None, "width": int(wh.group(1)) if wh else None,
            "height": int(wh.group(2)) if wh else None, "vcodec": (re.search(r"Video:\s*(\w+)", vline) or [None, ""])[1],
            "acodec": (re.search(r"Audio:\s*(\w+)", aline) or [None, ""])[1], "has_audio": bool(aline), "has_video": bool(vline),
            "size_bytes": path.stat().st_size, "bit_rate": int(br.group(1)) * 1000 if br else 0,
            "sample_rate": int((re.search(r"(\d+) Hz", aline) or [None, 0])[1] or 0)}


def measure_loudness(path: str | Path) -> float | None:
    """Integrated loudness in LUFS (EBU R128), or None when there is no audio."""
    ffmpeg, _ = binaries()
    p = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-filter_complex", "ebur128=framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=300, creationflags=_flags())
    m = re.findall(r"\bI:\s+(-?[\d.]+)\s+LUFS", p.stderr)
    return float(m[-1]) if m else None


def filter_complex_args(script_path: Path) -> list[str]:
    ver = runtime.ffmpeg_info().get("version") or ""
    major = re.match(r"(\d+)", ver)
    if major and int(major.group(1)) >= 7:
        return ["-/filter_complex", str(script_path)]
    return ["-filter_complex_script", str(script_path)]


def run(args: list[str], *, ctx=None, cwd: str | Path | None = None, expected_sec: float | None = None,
        on_progress: Callable[[float], None] | None = None, timeout: float = 3600) -> str:
    """Run ffmpeg. With a job context the run is cancellable and reports progress (fraction of expected_sec)."""
    ffmpeg, _ = binaries()
    cmd = [ffmpeg, "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-progress", "pipe:1", "-nostats", *args]

    def on_line(line: str) -> None:
        if on_progress and expected_sec and line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=")[1]) / 1e6 / expected_sec))
            except ValueError:
                pass

    if ctx is not None:
        rc, out = ctx.run_cmd(cmd, cwd=str(cwd) if cwd else None, on_line=on_line, timeout=timeout)
    else:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, creationflags=_flags())
        rc, out = p.returncode, (p.stdout or "")[-3000:] + (p.stderr or "")[-3000:]
    if rc != 0:
        lines = [ln for ln in out.splitlines() if ln and "=" not in ln.split(" ")[0]]
        raise FFmpegError("ffmpeg failed: " + " | ".join(lines[-6:])[:900])
    return out
