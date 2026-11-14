"""Loudness of a finished episode file: measure it the way the platforms do, bring it to the page's target, hold the true-peak ceiling.

SOURCE: ported from NMarketing:backend/services/editing/audioqc.py (loudness_stats, settle_loudness, _encode_audio, _badness) @ v3.02 (c23f861),
adapted for episode renders: the ffmpeg is the one InstAI located (`render/ffmpeg.py`), the targets are named per family of networks (`PROFILES`),
and the result is a plain dict that is kept on the final Asset (`provenance["loudness"]`) and shown in the quality panel.

Why a second pass exists: the assembly normalises with ONE pass of `loudnorm`. That filter is dynamic: on narration with long quiet stretches it lands
1 to 3 LU away from the target (NMarketing measured -16.1 for a -14 request on a real video). So after the render the FILE is measured with the same
meter the platforms use (EBU R128 via `ebur128`, true peak 4x oversampled) and, when it is off by more than the tolerance or its true peak is above
the ceiling, only its SOUND is re-encoded with the missing gain and a peak limiter. The picture stream is copied untouched: seconds, never a re-render.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from . import ffmpeg

log = logging.getLogger("instai.loudness")

#: the limiter works this far BELOW the true-peak ceiling: the AAC encoder re-quantises the signal and the decoded file overshoots the limiter by up to
#: about a dB (NMarketing measured a -1.3 dBFS limiter coming out of the encoder at +0.3 dBFS). It is only the starting point: `settle` MEASURES the
#: decoded result and lowers the ceiling further until the file really holds it.
AAC_HEADROOM_DB = 1.0
#: a measured true peak this far above the ceiling is fixed even when the loudness is already right
PEAK_TRIGGER_DB = 0.25
#: the most gain one pass may add or take away (a very quiet recording needs +20 dB; the limiter keeps the peaks under the ceiling)
GAIN_LIMIT_DB = 24.0
TOLERANCE_LU = 0.8
TP_CEILING_DB = -1.0
MAX_ROUNDS = 3

#: Loudness profiles: the number is what is stored on the page (`audio.target_lufs`); the key is only a name for the choice in the settings screen.
#: New pages start at -14 (what YouTube, Shorts, Reels and TikTok play at); pages made before 0.15 keep the -16 they were saved with.
NEW_PAGE_LUFS = -14.0
LEGACY_LUFS = -16.0
PROFILES: dict[str, dict] = {
    "social": {"lufs": -14.0, "fa": "شبکه‌های اجتماعی (یوتیوب، شورتس، ریلز، تیک‌تاک)", "en": "Social networks (YouTube, Shorts, Reels, TikTok)"},
    "messenger": {"lufs": -16.0, "fa": "تلگرام و آپارات", "en": "Telegram and Aparat"},
    "broadcast": {"lufs": -23.0, "fa": "پخش تلویزیونی (EBU R128)", "en": "Broadcast (EBU R128)"},
}


def profile_for(lufs: float | None) -> str:
    """The profile key of a stored target (`custom` when it is none of the named ones)."""
    for key, p in PROFILES.items():
        if lufs is not None and abs(float(lufs) - p["lufs"]) < 0.05:
            return key
    return "custom"


def catalogue() -> list[dict]:
    return [{"key": k, **v} for k, v in PROFILES.items()]


_NUM = r"(-?[0-9]+(?:\.[0-9]+)?|-inf)"


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(cmd: list[str], timeout: float):
    # text output decoded as UTF-8 with replacement: never a code-page error from a Windows console
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, creationflags=_flags(), encoding="utf-8", errors="replace")


def measure(path) -> dict | None:
    """What the platforms measure on a file, in ONE pass of ffmpeg's ebur128 (4x oversampled true peak included): `{"lufs": integrated loudness or None,
    "tp": true peak in dBTP or None}`; None when the file cannot be measured.

    The true peak is read from the DECODED file (an AAC file decodes to floats that can be above full scale), which is exactly what the platforms' meters see."""
    try:
        ff, _ = ffmpeg.binaries()
        proc = _run([ff, "-nostdin", "-hide_banner", "-i", str(path), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], 300)
    except (OSError, subprocess.SubprocessError, ffmpeg.FFmpegError):
        return None
    text = proc.stderr or ""
    mark = text.rfind("Integrated loudness:")
    if mark < 0:
        return None
    tail = text[mark:]
    lufs = tp = None
    m = re.search(r"I:\s*" + _NUM + r"\s*LUFS", tail)
    if m and m.group(1) != "-inf":
        lufs = round(float(m.group(1)), 1)
    m = re.search(r"True peak:\s*Peak:\s*" + _NUM + r"\s*dBFS", tail)
    if m:
        tp = -120.0 if m.group(1) == "-inf" else round(float(m.group(1)), 1)
    if lufs is None and tp is None:
        return None
    return {"lufs": lufs, "tp": tp}


def _encode_audio(src: Path, dst: Path, gain_db: float, ceiling_db: float) -> bool:
    """The picture copied untouched, the sound re-encoded with `gain_db` and a peak limiter at `ceiling_db` dBFS. True when `dst` is a real file."""
    limit = min(0.99, max(0.0625, 10 ** (float(ceiling_db) / 20)))
    chain = (f"volume={gain_db:.2f}dB," if abs(gain_db) > 0.005 else "") + f"alimiter=limit={limit:.3f}:level=disabled:attack=3:release=40,aresample=48000"
    try:
        ff, _ = ffmpeg.binaries()
        cmd = [ff, "-y", "-v", "error", "-nostdin", "-i", str(src), "-map", "0", "-c", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-af", chain,
               "-movflags", "+faststart", str(dst)]
        done = _run(cmd, 600)
    except (OSError, subprocess.SubprocessError, ffmpeg.FFmpegError):
        dst.unlink(missing_ok=True)
        return False
    if done.returncode != 0 or not dst.is_file() or dst.stat().st_size < 1024:
        dst.unlink(missing_ok=True)
        return False
    return True


def _badness(lufs: float | None, tp: float | None, target: float | None, tp_ceiling: float) -> float:
    """Lower is better: a peak above the ceiling costs 10x what the same distance of loudness costs (a clipped file is a defect, a file 0.5 LU quiet is not)."""
    over = max(0.0, (tp if tp is not None else tp_ceiling) - tp_ceiling)
    off = abs(target - lufs) if (target is not None and lufs is not None) else 0.0
    return 10.0 * over + off


def settle(path, *, target: float | None = -14.0, tp: float = TP_CEILING_DB, tolerance: float = TOLERANCE_LU, max_rounds: int = MAX_ROUNDS,
           peak_trigger: float | None = None) -> dict:
    """Bring a finished mp4 to the target loudness AND under the true-peak ceiling, both measured on the decoded FILE.

    Measure -> when off by more than `tolerance` (or the true peak is above the ceiling) re-encode the sound with the missing gain and a limiter ->
    measure again, at most `max_rounds` times. Every candidate is DECODED and measured: if it still peaks above `tp` the limiter ceiling is lowered by the
    overshoot and the ORIGINAL is encoded again (one generation of AAC, never a re-encode of a re-encode); as a last resort the gain itself comes down.
    The best candidate wins; if none beats the file as it was, the file is left as it was.

    `target=None` = peaks only (a page that did not ask for loudness normalisation keeps its loudness; only a file that really clips is touched).
    Never raises and never leaves a half-written file. Returns
    `{"lufs", "target", "adjusted", "rounds", "gain_db", "before", "tp", "tp_before", "tp_ceiling", "tolerance", "ok"}`, or `{}` when the file has no sound
    or cannot be measured."""
    path = Path(path)
    tried: list[Path] = []
    try:
        first = measure(path)
        if not first or first["lufs"] is None or first["lufs"] < -69.0:
            return {}
        before, tp_before = first["lufs"], first["tp"]
        rep: dict = {"lufs": before, "target": (float(target) if target is not None else None), "adjusted": False, "rounds": 0, "gain_db": 0.0, "before": before,
                     "tp": tp_before, "tp_before": tp_before, "tp_ceiling": float(tp), "tolerance": float(tolerance)}
        trigger = float(peak_trigger) if peak_trigger is not None else (PEAK_TRIGGER_DB + float(tp) if target is not None else -0.1)
        loud_off = target is not None and abs(float(target) - before) > tolerance
        peak_over = tp_before is not None and tp_before > trigger
        if loud_off or peak_over:
            gain = max(-GAIN_LIMIT_DB, min(GAIN_LIMIT_DB, float(target) - before)) if loud_off else 0.0
            ceiling = float(tp) - AAC_HEADROOM_DB
            best_score = _badness(before, tp_before, target, float(tp))
            best: tuple[Path, dict, float] | None = None
            encoded = 0
            for n in range(max(1, max_rounds)):
                tmp = path.with_name(f"{path.stem}.loud{n}{path.suffix}")
                tried.append(tmp)
                if not _encode_audio(path, tmp, gain, ceiling):
                    break
                encoded += 1
                st = measure(tmp)
                if not st or st["lufs"] is None:
                    break
                score = _badness(st["lufs"], st["tp"], target, float(tp))
                if score < best_score - 1e-6:
                    best_score, best = score, (tmp, st, gain)
                over = (st["tp"] if st["tp"] is not None else float(tp)) - float(tp)
                short = (float(target) - st["lufs"]) if target is not None else 0.0          # > 0: still too quiet
                if over > 0.05:
                    ceiling -= over + 0.2                            # the codec overshoot is measured, so the limiter goes under it by exactly that
                    if n >= 1:
                        gain -= over + 0.1                           # a second miss: a plain attenuation is exact
                elif target is not None and abs(short) > tolerance * 0.5 and n + 1 < max_rounds:
                    if over < -0.5:
                        ceiling += -over - 0.1                       # the first guess was too careful: work closer to the ceiling
                    gain = max(-GAIN_LIMIT_DB, min(GAIN_LIMIT_DB, gain + short))      # the limiter eats part of any extra gain; the next measurement tells how much
                else:
                    break                                            # holds the ceiling and the loudness is where it was asked: done
            if best is not None:
                tmp, st, used = best
                tmp.replace(path)
                rep.update(adjusted=True, gain_db=round(used, 1), lufs=st["lufs"], tp=st["tp"])
            rep["rounds"] = encoded
        rep["ok"] = bool((target is None or abs(float(target) - (rep["lufs"] or before)) <= tolerance + 0.05)
                         and (rep["tp"] is None or rep["tp"] <= float(tp) + 0.05))
        return rep
    except Exception as exc:  # noqa: BLE001 - a loudness touch-up must never fail a render
        log.info("settle failed for %s: %s", path, exc)
        return {}
    finally:
        for t in tried:
            t.unlink(missing_ok=True)
