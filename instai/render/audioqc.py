"""Quality control of a RENDERED mix: is the same speech playing twice, is the music on top of the voice, is one channel the other's opposite?

SOURCE: ported from NMarketing:backend/services/editing/audioqc.py (decode, echo_report, channel_report, level/peak helpers, masking_report) @ v3.02 (c23f861),
adapted for episodes: the checks are re-calibrated on InstAI's own mixes (narration per shot + side-chain-ducked music/ambience + effects, see
`production/mixing.py` and `render/assemble.py`), and a failed check NAMES the shot and the track, because an InstAI episode knows its parts.

Three different things make a finished video sound like several people talking at once, and each is a property of the FILE, not of the project:

* **the same speech twice, a little apart** - a narration clip placed twice, a sound effect that contains a voice, two takes of one sentence. The mix has an
  *echo*: its auto-correlation has a clear peak at the offset;
* **music as loud as the voice** - no ducking, or a bed that is too loud even after ducking: the words cannot be told apart. Measured on the STEMS of the
  episode (the narration alone, the ducked bed alone, the unducked effects alone), because InstAI knows them; NMarketing could only guess from the mix;
* **phase cancellation / a mono-in-one-ear mix** - the two channels anti-correlate.

`analyze_file` measures the file; `analyze_episode` also renders the stems and names shots and tracks. Nothing here changes a file, nothing needs a model,
and it never raises: a QC must not fail a render. `numpy` is the one requirement; without it the checks say so (`available() is False`) and the render goes on.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import ffmpeg

try:  # numpy is listed in requirements.txt; the render never needs it, only these checks do
    import numpy as np
except ImportError:  # pragma: no cover - exercised by a test that hides it
    np = None

log = logging.getLogger("instai.audioqc")

SR = 16000
#: an echo/duplicate this close or closer is "the same moment" and is heard as a chorus/comb filter; beyond MAX_LAG it is another sentence
MIN_LAG = 0.040
MAX_LAG = 1.2
WINDOW = 6.0
HOP = 3.0
#: normalised auto-correlation at the echo lag. A mix of x(t) + g*x(t-d) has r = g / (1 + g^2): 0.40 for an equal copy, 0.28 at -6 dB, 0.15 at -12 dB.
#: Natural speech sits below 0.08 once pre-whitened (NMarketing) and noise-excited synthetic speech below 0.05 (measured here, docs/BENCHMARKS.md).
ECHO_R = 0.16
#: the share of the speech windows that must show the SAME lag before it counts (a single window can be a held vowel)
ECHO_SHARE = 0.34
#: Looking at ONE shot's slice (a few seconds, one or two windows) there is no "a third of the episode" to lean on, so the bar is higher: a copy louder than about -10 dB
#: (r = 0.28). Measured on real narration (docs/BENCHMARKS.md): clean windows reach 0.20 at the very most, a copy at -10 dB gives 0.30, an equal copy 0.49.
SHOT_ECHO_R = 0.28
SHOT_ECHO_SHARE = 0.5
SHOT_MIN_S = 2.0
ACTIVE_DB = -45.0
#: the band a human voice lives in; the echo test looks only here so a hum or the hiss above the voice cannot pose as a repeat
SPEECH_BAND = (200.0, 3500.0)
#: a strictly periodic signal (a sine burst, a synthetic tone) correlates with itself at MANY lags: peaks of about the same height recur all over the lag range (the fake
#: narration engine's sine bursts show 9 or more of them away from the highest one). A real echo of speech has ONE peak: the copy sits at its lag and nowhere else.
#: A window with this many strong peaks far from the highest is "tonal" - a tone, not a doubled voice. Measured (docs/BENCHMARKS.md): real narration, clean or doubled, 0 or 1;
#: noise-like synthetic speech 0; the fake narration engine 9 to 11.
TONAL_PEAKS = 4
TONAL_NEAR_S = 0.025
#: the voice must stand at least this far above each part of the bed while it speaks (NMarketing: 6 dB); below it the words are masked
MASK_MARGIN_DB = 6.0
MASK_FRAME_S = 0.05
VOICE_ACTIVE_DB = -50.0
BED_FLOOR_DB = -60.0


def available() -> bool:
    return np is not None


_FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def fd(v) -> str:
    """A number inside a Persian sentence is written with Persian digits."""
    return str(v).translate(_FA_DIGITS)


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------------------------------------------------------------------- decoding

def decode_stereo(path, *, sr: int = SR, max_seconds: float = 600.0):
    """The audio of a media file as two float32 channels at `sr`: `(left, right)`; two empty arrays when there is none (a mono file comes back as two equal channels)."""
    empty = np.zeros(0, dtype=np.float32)
    try:
        ff, _ = ffmpeg.binaries()
        raw = subprocess.run([ff, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-t", f"{max_seconds:.0f}", "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                             capture_output=True, timeout=300, stdin=subprocess.DEVNULL, creationflags=_flags()).stdout
    except (OSError, subprocess.SubprocessError, ffmpeg.FFmpegError) as exc:
        log.info("audioqc.decode(%s) failed: %s", path, exc)
        return empty, empty
    a = np.frombuffer(raw, dtype=np.float32)
    a = a[: len(a) // 2 * 2]
    if not len(a):
        return empty, empty
    st = a.reshape(-1, 2)
    return st[:, 0].copy(), st[:, 1].copy()


def decode_mono(path, *, sr: int = SR, max_seconds: float = 600.0):
    left, right = decode_stereo(path, sr=sr, max_seconds=max_seconds)
    return ((left + right) * 0.5).astype(np.float32) if len(left) else left


def _raw_mono(path: Path):
    a = np.fromfile(str(path), dtype=np.float32) if Path(path).is_file() else np.zeros(0, dtype=np.float32)
    return a


# ---------------------------------------------------------------------------------------------------------------------------- the three tests

def _whiten(x):
    """Pre-emphasis: removes the slow tonal trend that makes speech correlate with itself at short lags, so what is left in the auto-correlation is repetition,
    not voicing."""
    if len(x) < 4:
        return x
    y = np.empty_like(x)
    y[0] = x[0]
    y[1:] = x[1:] - 0.97 * x[:-1]
    return y


def _bandpass(x, sr: int, band: tuple[float, float] = SPEECH_BAND):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    spec[(f < band[0]) | (f > band[1])] = 0
    return np.fft.irfft(spec, n=len(x)).astype(np.float32)


def _acorr(x, hi: int):
    n = len(x)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    spec = np.fft.rfft(x, size)
    ac = np.fft.irfft(spec * np.conj(spec))[: hi + 1]
    return ac / (ac[0] + 1e-12)


def _tonal(band, peak: float, lag_index: int) -> bool:
    """Does the lag search window hold a crowd of strong peaks away from the highest one instead of one peak? (see TONAL_PEAKS)"""
    floor = max(0.5 * peak, 0.6 * ECHO_R)
    mid = band[1:-1]
    idx = np.flatnonzero((mid >= band[:-2]) & (mid > band[2:]) & (mid >= floor)) + 1
    near = int(TONAL_NEAR_S * SR)
    return int(sum(1 for j in idx if abs(int(j) - lag_index) > near)) >= TONAL_PEAKS


def echo_report(x, sr: int = SR, *, r_min: float = ECHO_R, share_min: float = ECHO_SHARE) -> dict:
    """Is a delayed copy of the speech in this signal? `{"doubled", "lag_s", "strength", "share", "windows", "tonal", "spans"}`; `spans` = the windows
    (seconds) that show the repeat, so a caller can name the shots."""
    out = {"doubled": False, "lag_s": None, "strength": 0.0, "share": 0.0, "windows": 0, "tonal": 0, "spans": []}
    if np is None or len(x) < int(2 * sr):
        return out
    x = x.astype(np.float32, copy=False)
    win, hop = int(WINDOW * sr), int(HOP * sr)
    lo, hi = int(MIN_LAG * sr), int(MAX_LAG * sr)
    found: list[tuple[float, float, float, float]] = []          # (lag, r, start_s, end_s)
    total = tonal = 0
    best_r = 0.0
    pos = 0
    while pos + win // 2 <= len(x):
        seg = x[pos: pos + win]
        start_s, end_s = pos / sr, (pos + len(seg)) / sr
        pos += hop
        if len(seg) < 4 * lo:
            break
        rms = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)) + 1e-12)
        if 20 * np.log10(rms) < ACTIVE_DB:
            continue
        total += 1
        seg = _whiten(_bandpass(seg, sr))
        ac = _acorr(seg * np.hanning(len(seg)), min(len(seg) - 1, hi))
        band = ac[lo:hi + 1]
        if len(band) < 3:
            continue
        i = int(np.argmax(band))
        lag = i + lo
        if _tonal(band, float(band[i]), i):
            tonal += 1
            continue
        best_r = max(best_r, float(band[i]))
        found.append((lag / sr, float(band[i]), start_s, end_s))
    out["windows"], out["tonal"] = total, tonal
    if not total:
        return out
    strong = [f for f in found if f[1] >= r_min]
    if not strong:
        out["strength"] = round(best_r, 3)
        return out
    # the same lag (+-12 ms) in a third of the speech windows
    best_hits: list = []
    for lag, _, _, _ in strong:
        hits = [f for f in strong if abs(f[0] - lag) <= 0.012]
        if len(hits) > len(best_hits):
            best_hits = hits
    share = len(best_hits) / total
    out["share"] = round(share, 3)
    out["strength"] = round(float(np.mean([h[1] for h in best_hits])), 3)
    out["lag_s"] = round(float(np.mean([h[0] for h in best_hits])), 3)
    out["doubled"] = share >= share_min
    if out["doubled"]:
        out["spans"] = [[round(h[2], 2), round(h[3], 2)] for h in best_hits]
    return out


def channel_report(left, right) -> dict:
    n = min(len(left), len(right))
    if np is None or n < SR:
        return {"corr": None, "out_of_phase": False}
    l, r = left[:n], right[:n]
    if float(np.std(l)) < 1e-6 or float(np.std(r)) < 1e-6:
        return {"corr": None, "out_of_phase": False}
    c = float(np.corrcoef(l, r)[0, 1])
    return {"corr": round(c, 3), "out_of_phase": c < -0.25}


def level_db(x) -> float:
    if np is None or not len(x):
        return -120.0
    return round(float(20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-9)), 1)


def peak_db(x) -> float:
    if np is None or not len(x):
        return -120.0
    return round(float(20 * np.log10(np.max(np.abs(x)) + 1e-9)), 1)


def masking_report(voice, bed) -> dict:
    """How far the voice stands above the bed when both are heard (their levels in the final mix, each measured alone)."""
    v, m = level_db(voice), level_db(bed)
    return {"voice_db": v, "bed_db": m, "margin_db": round(v - m, 1), "masked": (v - m) < MASK_MARGIN_DB and m > BED_FLOOR_DB}


def masking_by_window(voice, bed, windows: list[dict], sr: int = SR) -> list[dict]:
    """Per narration window `{"shot", "from", "to"}`: the voice against the bed over the 50 ms frames in which the voice actually speaks (the pauses between
    words do not count as "quiet voice"). `[{"shot", "from", "to", "voice_db", "bed_db", "margin_db", "masked"}]`; windows with too little speech are left out."""
    rows: list[dict] = []
    fr = max(1, int(MASK_FRAME_S * sr))
    for w in windows:
        a, b = int(w["from"] * sr), int(w["to"] * sr)
        v, m = voice[a:b], bed[a:b]
        k = min(len(v), len(m)) // fr
        if k < 3:
            continue
        v2 = (v[: k * fr].astype(np.float64) ** 2).reshape(k, fr).mean(axis=1)
        m2 = (m[: k * fr].astype(np.float64) ** 2).reshape(k, fr).mean(axis=1)
        active = 10 * np.log10(v2 + 1e-12) > VOICE_ACTIVE_DB
        if int(active.sum()) < 3:
            continue
        vp, mp = float(v2[active].mean()), float(m2[active].mean())
        v_db, m_db = 10 * np.log10(vp + 1e-12), 10 * np.log10(mp + 1e-12)
        margin = v_db - m_db
        rows.append({"shot": w["shot"], "from": round(w["from"], 2), "to": round(w["to"], 2), "voice_db": round(float(v_db), 1), "bed_db": round(float(m_db), 1),
                     "margin_db": round(float(margin), 1), "masked": bool(margin < MASK_MARGIN_DB and m_db > BED_FLOOR_DB)})
    return rows


def echo_by_shot(x, timeline: list[dict], sr: int = SR) -> list[dict]:
    """The echo test on each shot's own slice of a signal: `[{"shot", "from", "to", "lag_s", "strength"}]` for the shots that are doubled. A single doubled shot in a
    long episode is far less than a third of the file, so the file-level test alone would never see it."""
    out = []
    for i, t in enumerate(timeline):
        a, b = int(t["start"] * sr), int(t["end"] * sr)
        seg = x[a:b]
        if len(seg) < SHOT_MIN_S * sr:
            continue
        r = echo_report(seg, sr, r_min=SHOT_ECHO_R, share_min=SHOT_ECHO_SHARE)
        if r["doubled"]:
            out.append({"shot": i + 1, "from": round(t["start"], 2), "to": round(t["end"], 2), "lag_s": r["lag_s"], "strength": r["strength"]})
    return out


def merge_shot_echo(echo: dict, by_shot: list[dict]) -> dict:
    """Fold the shots found one by one into the file-level echo report (`doubled`, the lag, the shots and the spans)."""
    if not by_shot:
        return echo
    echo["doubled"] = True
    echo["lag_s"] = echo["lag_s"] if echo.get("lag_s") else by_shot[0]["lag_s"]
    echo["strength"] = max(echo.get("strength") or 0.0, max(r["strength"] for r in by_shot))
    echo["spans"] = (echo.get("spans") or []) + [[r["from"], r["to"]] for r in by_shot]
    echo["shots"] = sorted(set(echo.get("shots", [])) | {r["shot"] for r in by_shot})
    return echo


# ---------------------------------------------------------------------------------------------------------------------------- stems of an episode

def stem_graph(shots, timeline: list[dict], tracks: list[dict], total: float) -> tuple[str, list[str], dict] | None:
    """The filter graph that renders the narration alone and the bed alone, built from the SAME pieces as the final mix (`assemble.track_filters`, the same
    side-chain settings), so what is measured is what was heard. Returns `(graph, inputs, outputs)`; `outputs` maps a stem name (voice, ducked, plain) to its
    label; None when the episode has no narration or no track (nothing to compare)."""
    from . import assemble

    parts: list[str] = []
    inputs: list[str] = []
    labels: list[str] = []
    k = 0
    for s, t in zip(shots, timeline):
        if s.audio:
            ms = int(round(t["audio_start"] * 1000))
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[n{k}]")
            labels.append(f"[n{k}]")
            inputs.append(str(s.audio))
            k += 1
    if not labels or not tracks:
        return None
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,apad=whole_dur={total:.3f}[nar]")
    tparts, duck, plain = assemble.track_filters(tracks, k, total)
    parts += tparts
    inputs += [str(t["file"]) for t in tracks]
    outs: dict[str, str] = {}
    if duck:
        bed = duck[0]
        if len(duck) > 1:
            parts.append("".join(duck) + f"amix=inputs={len(duck)}:duration=longest:normalize=0[bed]")
            bed = "[bed]"
        parts.append("[nar]asplit=2[vkey][vout]")
        parts.append(f"{bed}[vkey]{assemble.DUCK_FILTER}[ducked]")
        outs["voice"], outs["ducked"] = "[vout]", "[ducked]"
    else:
        outs["voice"] = "[nar]"
    if plain:
        if len(plain) > 1:
            parts.append("".join(plain) + f"amix=inputs={len(plain)}:duration=longest:normalize=0[plainbed]")
            outs["plain"] = "[plainbed]"
        else:
            outs["plain"] = plain[0]
    return ";\n".join(parts), inputs, outs


def render_stems(shots, timeline: list[dict], tracks: list[dict], workdir: Path, total: float) -> dict | None:
    """Render the stems to 16 kHz mono float files and read them: `{"voice": array, "ducked": array|None, "plain": array|None}`; None when there is nothing to compare."""
    built = stem_graph(shots, timeline, tracks, total)
    if built is None:
        return None
    graph, inputs, outs = built
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "stems.txt"
    script.write_text(graph, encoding="utf-8")
    args: list[str] = []
    for f in inputs:
        args += ["-i", f]
    args += [*ffmpeg.filter_complex_args(script)]
    paths: dict[str, Path] = {}
    for name, label in outs.items():
        paths[name] = workdir / f"stem_{name}.f32"
        args += ["-map", label, "-t", f"{total:.3f}", "-ac", "1", "-ar", str(SR), "-f", "f32le", str(paths[name])]
    ffmpeg.run(args, cwd=workdir)
    return {n: (_raw_mono(paths[n]) if n in paths else None) for n in ("voice", "ducked", "plain")}


# ---------------------------------------------------------------------------------------------------------------------------- naming shots and tracks

KIND_FA = {"music": "موسیقی", "ambience": "فضا", "sfx": "جلوه"}
KIND_EN = {"music": "music", "ambience": "ambience", "sfx": "effect"}


def shots_between(timeline: list[dict], t0: float, t1: float) -> list[int]:
    """1-based numbers of the shots whose span overlaps [t0, t1] (the numbering the ladder and the storyboard use)."""
    return [i + 1 for i, t in enumerate(timeline) if t["start"] < t1 and t["end"] > t0]


def _range_text(nums: list[int], lang: str) -> str:
    if not nums:
        return ""
    if len(nums) == 1:
        return (f"شات {fd(nums[0])}" if lang == "fa" else f"shot {nums[0]}")
    a, b = nums[0], nums[-1]
    contiguous = nums == list(range(a, b + 1))
    if lang == "fa":
        return f"شات‌های {fd(a)} تا {fd(b)}" if contiguous else "شات‌های " + "، ".join(fd(n) for n in nums[:6])
    return f"shots {a}-{b}" if contiguous else "shots " + ", ".join(str(n) for n in nums[:6])


def tracks_between(tracks: list[dict], t0: float, t1: float, groups: tuple[str, ...] | None = None) -> list[dict]:
    out = []
    for t in tracks:
        if float(t["start"]) < t1 and float(t["end"]) > t0:
            if groups is None or ("ducked" if t.get("duck") else "plain") in groups:
                out.append(t)
    return out


def loudest_track(tracks: list[dict], t0: float, t1: float, group: str) -> dict | None:
    """The track of `group` (ducked / plain) that sits loudest in the window, by its own level plus its mix gain."""
    best, best_db = None, -999.0
    for t in tracks_between(tracks, t0, t1, (group,)):
        x = decode_mono(t["file"], max_seconds=30.0)
        db = (level_db(x) if len(x) else -120.0) + float(t.get("gain_db", -18.0))
        if db > best_db:
            best, best_db = t, db
    return best


def _track_name(t: dict, lang: str) -> str:
    kind = (KIND_FA if lang == "fa" else KIND_EN).get(t.get("kind", ""), t.get("kind", ""))
    label = (t.get("label") or "").strip()
    return f"{kind} «{label}»" if label else kind


# ---------------------------------------------------------------------------------------------------------------------------- the report

def analyze_file(path, *, with_loudness: bool = False) -> dict:
    """Echo and phase of one rendered file (no stems: the project is not known). Never raises: `{"ok": False, "reason": ...}`."""
    if np is None:
        return {"ok": False, "reason": "numpy_missing"}
    try:
        left, right = decode_stereo(path)
        if not len(left):
            return {"ok": False, "reason": "no_audio"}
        mono = ((left + right) * 0.5).astype(np.float32)
        rep: dict = {"ok": True, "seconds": round(len(mono) / SR, 2), "level_db": level_db(mono), "peak_db": peak_db(mono), "echo": echo_report(mono),
                     "channels": channel_report(left, right)}
        if with_loudness:
            from . import loudness

            st = loudness.measure(path) or {}
            rep["lufs"], rep["true_peak_db"] = st.get("lufs"), st.get("tp")
        rep["problems"] = [k for k, bad in (("echo", rep["echo"]["doubled"]), ("phase", rep["channels"]["out_of_phase"])) if bad]
        rep["clean"] = not rep["problems"]
        return rep
    except Exception as exc:  # noqa: BLE001 - a QC must never fail a render
        log.info("audioqc.analyze_file failed for %s: %s", path, exc)
        return {"ok": False, "reason": "error"}


def analyze_episode(path, shots=None, timeline: list[dict] | None = None, tracks: list[dict] | None = None, workdir: Path | None = None) -> dict:
    """`analyze_file` plus, when the episode's parts are given, the stems: the echo is attributed to the narration or to a track and to shots, and the voice is
    compared with the ducked bed and the unducked effects shot by shot. Never raises."""
    rep = analyze_file(path)
    if not rep.get("ok"):
        return rep
    shots, timeline, tracks = shots or [], timeline or [], tracks or []
    rep["shots"] = len(timeline)
    rep["masking"] = {"applicable": False, "windows": [], "masked": []}
    if timeline:
        left, right = decode_stereo(path)
        mono = ((left + right) * 0.5).astype(np.float32)
        rep["echo"]["shots"] = sorted({n for a, b in rep["echo"]["spans"] for n in shots_between(timeline, a, b)}) if rep["echo"]["doubled"] else []
        merge_shot_echo(rep["echo"], echo_by_shot(mono, timeline))
        rep["problems"] = [k for k, bad in (("echo", rep["echo"]["doubled"]), ("phase", rep["channels"]["out_of_phase"])) if bad]
        rep["clean"] = not rep["problems"]
    if not (shots and timeline):
        return rep
    own = workdir is None
    work = Path(tempfile.mkdtemp(prefix="audioqc-")) if own else Path(workdir)
    try:
        total = timeline[-1]["end"]
        stems = render_stems(shots, timeline, tracks, work, total)
        if stems is None:
            if rep["echo"]["doubled"] and not tracks:                 # no other track exists: the repeat can only be the narration itself
                rep["echo"]["narration"] = True
                rep["echo"]["narration_shots"] = rep["echo"].get("shots", [])
            return rep
        voice = stems["voice"]
        windows = [{"shot": i + 1, "from": t["audio_start"], "to": t["audio_start"] + (s.audio_duration or 0.0)}
                   for i, (s, t) in enumerate(zip(shots, timeline)) if s.audio and (s.audio_duration or 0) > 0.2]
        masked: list[dict] = []
        worst: dict | None = None
        all_rows: list[dict] = []
        for group in ("ducked", "plain"):
            bed = stems.get(group)
            if bed is None or not len(bed):
                continue
            for row in masking_by_window(voice, bed, windows):
                row["group"] = group
                all_rows.append(row)
                if worst is None or row["margin_db"] < worst["margin_db"]:
                    worst = row
                if row["masked"]:
                    t = loudest_track(tracks, row["from"], row["to"], group)
                    row["track"] = {"id": t.get("id"), "kind": t.get("kind"), "label": t.get("label", "")} if t else None
                    masked.append(row)
        rep["masking"] = {"applicable": True, "windows": all_rows, "masked": masked, "worst": worst, "margin_db": (worst or {}).get("margin_db")}
        if rep["echo"]["doubled"]:
            voice_echo = merge_shot_echo(echo_report(voice), echo_by_shot(voice, timeline))
            rep["echo"]["narration"] = bool(voice_echo["doubled"])
            if voice_echo["doubled"]:
                rep["echo"]["narration_shots"] = sorted({n for a, b in voice_echo["spans"] for n in shots_between(timeline, a, b)})
            else:
                active = tracks_between(tracks, min(a for a, _ in rep["echo"]["spans"]), max(b for _, b in rep["echo"]["spans"]))
                rep["echo"]["tracks"] = [{"id": t.get("id"), "kind": t.get("kind"), "label": t.get("label", "")} for t in active]
        rep["problems"] = [p for p in rep["problems"] if p != "masking"] + (["masking"] if masked else [])
        rep["clean"] = not rep["problems"]
    except Exception as exc:  # noqa: BLE001
        log.info("audioqc stems failed for %s: %s", path, exc)
        rep["masking"] = {"applicable": False, "windows": [], "masked": [], "error": str(exc)[:200]}
    finally:
        if own:
            shutil.rmtree(work, ignore_errors=True)
    return rep


# ---------------------------------------------------------------------------------------------------------------------------- rows for the quality panel

def _row(name: str, level: str, value, fa: str, en: str) -> dict:
    return {"name": name, "level": level, "value": value, "message": fa, "message_en": en}


def qc_rows(rep: dict | None) -> list[dict]:
    """Rows in `qc.technical`'s format (`name, level, value, message`) plus `message_en`: echo, music over voice, phase. A report without sound or without
    numpy gives ONE info row that says why nothing was checked (never an invented "ok")."""
    if not rep or not rep.get("ok"):
        why = (rep or {}).get("reason", "error")
        fa = {"numpy_missing": "بررسی صدا انجام نشد: بستهٔ numpy روی این رایانه نیست (START.bat آن را نصب می‌کند).", "no_audio": "بررسی صدا انجام نشد: فایل صدا ندارد."}.get(
            why, "بررسی صدا انجام نشد.")
        en = {"numpy_missing": "The sound check did not run: numpy is not installed on this PC (START.bat installs it).", "no_audio": "The sound check did not run: the file has no sound."}.get(
            why, "The sound check did not run.")
        return [_row("audio_check", "info", why, fa, en)]
    rows: list[dict] = []
    echo = rep["echo"]
    if echo["doubled"]:
        ms = int(round((echo["lag_s"] or 0) * 1000))
        shots_fa, shots_en = _range_text(echo.get("shots", []), "fa"), _range_text(echo.get("shots", []), "en")
        where_fa = f" ({shots_fa})" if shots_fa else ""
        where_en = f" ({shots_en})" if shots_en else ""
        if echo.get("narration"):
            ns = echo.get("narration_shots") or echo.get("shots") or []
            cause_fa = f"؛ خودِ گفتارِ راوی دوبار پخش می‌شود ({_range_text(ns, 'fa')})".replace(" ()", "")
            cause_en = f"; the narration itself plays twice ({_range_text(ns, 'en')})".replace(" ()", "")
        elif echo.get("tracks"):
            names_fa = "، ".join(_track_name(t, "fa") for t in echo["tracks"][:3])
            names_en = ", ".join(_track_name(t, "en") for t in echo["tracks"][:3])
            cause_fa = f"؛ راوی تنها درست است و یکی از ترک‌های صدا گفتار دارد: {names_fa}"
            cause_en = f"; the narration alone is fine, one of the tracks carries speech: {names_en}"
        else:
            cause_fa = cause_en = ""
        rows.append(_row("audio_echo", "warn", {"lag_s": echo["lag_s"], "strength": echo["strength"], "share": echo["share"], "shots": echo.get("shots", []),
                                                "narration": echo.get("narration"), "tracks": echo.get("tracks", [])},
                         f"همان گفتار دوبار و با فاصلهٔ حدود {fd(ms)} میلی‌ثانیه شنیده می‌شود{where_fa}{cause_fa}. یک روایت یا یک ترکِ صدا دوبار گذاشته شده است؛ یکی را بردارید.",
                         f"The same speech is heard twice about {ms} ms apart{where_en}{cause_en}. A narration clip or a sound track is placed twice; remove one."))
    else:
        rows.append(_row("audio_echo", "ok", {"strength": echo["strength"], "windows": echo["windows"]}, "گفتار تکراری (اکو) پیدا نشد", "No doubled speech (echo) found"))
    mk = rep.get("masking") or {}
    if mk.get("masked"):
        w = min(mk["masked"], key=lambda r: r["margin_db"])
        t = w.get("track")
        name_fa = _track_name(t, "fa") if t else ("جلوه‌ها" if w["group"] == "plain" else "موسیقی و فضا")
        name_en = _track_name(t, "en") if t else ("the effects" if w["group"] == "plain" else "the music and ambience")
        extra_fa = " «کم‌شدن زیر صدا» را روشن کنید یا بلندیِ آن را کم کنید." if w["group"] == "plain" else " بلندیِ آن را کم کنید."
        extra_en = " Turn on ducking under the voice or lower its level." if w["group"] == "plain" else " Lower its level."
        m = w["margin_db"]
        gap_fa = f"فقط {fd(m)} دسی‌بل پایین‌تر از او" if m >= 0 else f"{fd(abs(m))} دسی‌بل بلندتر از او"
        gap_en = f"only {m} dB below the voice" if m >= 0 else f"{abs(m)} dB louder than the voice"
        rows.append(_row("audio_masking", "warn", {"shot": w["shot"], "margin_db": m, "group": w["group"], "track": t, "shots": sorted({r["shot"] for r in mk["masked"]})},
                         f"{name_fa} در {_range_text([w['shot']], 'fa')} تقریباً هم‌بلندیِ صدای راوی است ({gap_fa}) و کلمات گم می‌شوند.{extra_fa}",
                         f"{name_en} in {_range_text([w['shot']], 'en')} is nearly as loud as the narrator ({gap_en}) and the words get lost.{extra_en}"))
    elif mk.get("applicable"):
        m = mk.get("margin_db")
        rows.append(_row("audio_masking", "ok", {"margin_db": m}, f"صدای راوی بالای موسیقی و جلوه‌ها شنیده می‌شود (کمترین فاصله {fd(m)} دسی‌بل)",
                         f"The narrator stays above the music and effects (smallest margin {m} dB)"))
    else:
        rows.append(_row("audio_masking", "ok", {"applicable": False}, "موسیقی یا جلوه‌ای که روی صدای راوی بیفتد در این قسمت نیست", "No music or effects under the narration in this episode"))
    ch = rep["channels"]
    if ch["out_of_phase"]:
        rows.append(_row("audio_phase", "warn", ch, f"دو کانال صدا ناهمفاز است (همبستگی {fd(ch['corr'])}) و در پخشِ تک‌بلندگو صدا کم می‌شود یا از بین می‌رود",
                         f"The two audio channels are out of phase (correlation {ch['corr']}); on a single speaker the sound thins out or vanishes"))
    else:
        rows.append(_row("audio_phase", "ok", ch, "فازِ دو کانال صدا سالم است", "The two channels are in phase"))
    return rows
