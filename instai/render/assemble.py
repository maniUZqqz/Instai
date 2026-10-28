"""FFmpeg assembly: shot clips (2.5D camera motion over stills, or generated video) -> one 9:16 episode with narration,
optional music with ducking, loudness normalisation and burned-in Persian subtitles.

Two stages so that editing one shot re-renders only that shot: (1) `render_shot_clip` makes a silent clip per shot (cacheable),
(2) `assemble` joins clips with crossfades/cuts, places each narration at its shot's start, mixes, normalises and burns subtitles.
Timeline maths is pure Python (`plan_timeline`) and unit-tested without ffmpeg.
"""
from __future__ import annotations

import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import camera, ffmpeg, subtitles

FONT_DIR = Path(__file__).parent / "fonts"
LEAD_IN = 0.15       # seconds of silence before narration starts in a shot
TAIL = 0.35          # seconds after narration ends before the next shot
XFADE = 0.4


@dataclass
class ShotSpec:
    key: str                              # stable id (shot pk) - names the cached clip
    duration: float                       # planned seconds (narration may extend it)
    image: str | None = None
    video: str | None = None
    layers: tuple[str, str] | None = None  # (background, foreground RGBA) for parallax
    camera: dict = field(default_factory=dict)
    technique: str = "still_kenburns"
    transition: str = "cut"               # transition INTO the next shot: cut | crossfade
    audio: str | None = None
    audio_duration: float = 0.0
    subtitle: str = ""
    puppet: dict | None = None            # puppet-2D scene (rig, background layers, camera); see production/puppet.py


@dataclass
class RenderOptions:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    mode: str = "final"
    subtitle_style: dict = field(default_factory=dict)
    target_lufs: float = -16.0
    music: str | None = None
    music_db: float = -22.0
    subtitles: bool = True
    tracks: list = field(default_factory=list)    # mix tracks resolved to timeline positions (production/mixing.py): music, ambience, sfx

    @classmethod
    def for_mode(cls, mode: str, final_height: int = 1920, preview_height: int = 640, fps: int = 30, **kw) -> "RenderOptions":
        if mode == "preview":
            h = preview_height // 2 * 2
            return cls(width=int(h * 9 / 16) // 2 * 2, height=h, fps=min(fps, 15), crf=30, preset="ultrafast", mode="preview", **kw)
        h = final_height // 2 * 2
        return cls(width=int(h * 9 / 16) // 2 * 2, height=h, fps=fps, crf=20, preset="medium", mode="final", **kw)


def shot_duration(s: ShotSpec) -> float:
    """Narration drives the length: never cut speech off."""
    if s.audio and s.audio_duration:
        return round(max(s.duration, LEAD_IN + s.audio_duration + TAIL), 3)
    return round(s.duration, 3)


def plan_timeline(shots: list[ShotSpec]) -> list[dict]:
    """[{key, start, duration, end, overlap_next, audio_start}] on one absolute timeline (crossfades overlap clips)."""
    out, t = [], 0.0
    for i, s in enumerate(shots):
        d = shot_duration(s)
        ov = min(XFADE, d / 3, shot_duration(shots[i + 1]) / 3) if (s.transition == "crossfade" and i + 1 < len(shots)) else 0.0
        out.append({"key": s.key, "start": round(t, 3), "duration": d, "end": round(t + d, 3), "overlap_next": round(ov, 3),
                    "audio_start": round(t + LEAD_IN, 3)})
        t = t + d - ov
    return out


def total_duration(timeline: list[dict]) -> float:
    return timeline[-1]["end"] if timeline else 0.0


# ------------------------------------------------------------------ stage 1: shot clips

def render_shot_clip(spec: ShotSpec, opts: RenderOptions, out_path: Path, *, duration: float | None = None, ctx=None) -> Path:
    """One silent clip. Stills get camera motion (Ken Burns, or parallax when layers exist); videos are fitted and padded."""
    d = duration or shot_duration(spec)
    frames = max(2, int(round(d * opts.fps)))
    w, h, fps = opts.width, opts.height, opts.fps
    enc = ["-c:v", "libx264", "-preset", "veryfast" if opts.mode == "final" else "ultrafast", "-crf", "17" if opts.mode == "final" else "30",
           "-pix_fmt", "yuv420p", "-r", str(fps), "-an", "-movflags", "+faststart"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mv = spec.camera.get("move", "zoom_in")
    inten = float(spec.camera.get("intensity", 0.5))
    if spec.puppet:
        from django.conf import settings

        from .puppet.renderer import PuppetRenderer

        scene = {**spec.puppet, "width": w, "height": h, "fps": fps, "duration": d}
        PuppetRenderer(scene, Path(settings.MEDIA_ROOT)).render(out_path, ctx=ctx, crf=17 if opts.mode == "final" else 30,
                                                               preset="veryfast" if opts.mode == "final" else "ultrafast")
        return out_path
    if spec.video and Path(spec.video).is_file():
        vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},setpts=PTS-STARTPTS,format=yuv420p")
        ffmpeg.run(["-i", spec.video, "-vf", vf, *enc, str(out_path)], ctx=ctx)
    elif spec.layers and all(Path(p).is_file() for p in spec.layers):
        ffmpeg.run(["-i", spec.layers[0], "-i", spec.layers[1], "-filter_complex", camera.parallax(mv, inten, frames, w, h, fps),
                    "-map", "[out]", "-frames:v", str(frames), *enc, str(out_path)], ctx=ctx)
    elif spec.image and Path(spec.image).is_file():
        ffmpeg.run(["-i", spec.image, "-vf", camera.ken_burns(mv, inten, frames, w, h, fps), "-frames:v", str(frames), *enc, str(out_path)], ctx=ctx)
    else:
        raise ffmpeg.FFmpegError(f"shot {spec.key} has no image/video to render")
    return out_path


# ------------------------------------------------------------------ stage 2: join, mix, subtitle

def build_cues(shots: list[ShotSpec], timeline: list[dict]) -> list[subtitles.Cue]:
    cues: list[subtitles.Cue] = []
    for s, t in zip(shots, timeline):
        if not s.subtitle.strip():
            continue
        dur = s.audio_duration if (s.audio and s.audio_duration) else max(0.5, t["duration"] * 0.85)
        cues += subtitles.make_cues(s.subtitle, t["audio_start"], dur)
    return cues


def build_filter(shots: list[ShotSpec], timeline: list[dict], opts: RenderOptions, n_clips: int, audio_first_input: int,
                 has_subs: bool) -> str:
    parts: list[str] = []
    # video: chain clips with cut (concat) or crossfade (xfade). Every stream gets the same fps/timebase first: ffmpeg 7.1's
    # xfade refuses inputs whose timebases differ (a concat output has 1/1000000, an mp4 clip 1/15360).
    norm = f"settb=AVTB,setpts=PTS-STARTPTS,fps={opts.fps},setsar=1,format=yuv420p"
    for i in range(len(shots)):
        parts.append(f"[{i}:v]{norm}[c{i}]")
    acc, acc_len = "[c0]", timeline[0]["duration"]
    for i in range(1, len(shots)):
        ov = timeline[i - 1]["overlap_next"]
        nxt = f"[v{i}]"
        if ov > 0:
            parts.append(f"{acc}[c{i}]xfade=transition=fade:duration={ov:.3f}:offset={acc_len - ov:.3f},{norm}{nxt}")
        else:
            parts.append(f"{acc}[c{i}]concat=n=2:v=1:a=0,{norm}{nxt}")
        acc_len += timeline[i]["duration"] - ov
        acc = nxt
    parts.append(f"{acc}ass=sub.ass:fontsdir=fonts[vout]" if has_subs else f"{acc}null[vout]")
    # audio: each narration delayed to its shot start, mixed, optional ducked music, loudness normalised
    total = total_duration(timeline)
    labels = []
    k = audio_first_input
    for s, t in zip(shots, timeline):
        if s.audio:
            ms = int(round(t["audio_start"] * 1000))
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[n{k}]")
            labels.append(f"[n{k}]")
            k += 1
    if labels:
        mix = "".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,apad=whole_dur={total:.3f}[nar]"
        parts.append(mix)
        voice = "[nar]"
    else:
        parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[nar]")
        voice = "[nar]"
    if opts.music:
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,aloop=loop=-1:size=2000000000,atrim=0:{total:.3f},"
                     f"volume={opts.music_db}dB[mus]")
        parts.append(f"{voice}asplit=2[v1a][v2a]")
        parts.append("[mus][v2a]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        parts.append("[v1a][duck]amix=inputs=2:duration=first:normalize=0[mixed]")
        voice = "[mixed]"
    if opts.tracks:
        kt = k + (1 if opts.music else 0)
        tparts, duck, plain = track_filters(opts.tracks, kt, total)
        parts += tparts
        voice = mix_with_tracks(parts, voice, duck, plain)
    parts.append(f"{voice}atrim=0:{total:.3f},loudnorm=I={opts.target_lufs}:TP=-1.5:LRA=11,aresample=48000,asetpts=PTS-STARTPTS[aout]")
    return ";\n".join(parts)


def track_filters(tracks: list[dict], first_input: int, total: float) -> tuple[list[str], list[str], list[str]]:
    """Filter chains for the mix tracks. Returns (chains, labels of tracks that duck under dialogue, labels of the others).
    Each track: trimmed/looped to its span, faded, set to its gain, delayed to its start."""
    chains, duck, plain = [], [], []
    for i, t in enumerate(tracks):
        span = max(0.05, float(t["end"]) - float(t["start"]))
        ms = int(round(float(t["start"]) * 1000))
        fi, fo = min(float(t.get("fade_in", 0.0)), span / 2), min(float(t.get("fade_out", 0.0)), span / 2)
        c = f"[{first_input + i}:a]aresample=48000,aformat=channel_layouts=stereo"
        if t.get("loop"):
            c += ",aloop=loop=-1:size=2000000000"
        c += f",atrim=0:{span:.3f},asetpts=PTS-STARTPTS"
        if fi > 0:
            c += f",afade=t=in:st=0:d={fi:.3f}"
        if fo > 0:
            c += f",afade=t=out:st={max(0.0, span - fo):.3f}:d={fo:.3f}"
        c += f",volume={float(t.get('gain_db', -18.0)):.1f}dB,adelay={ms}|{ms}[tr{i}]"
        chains.append(c)
        (duck if t.get("duck") else plain).append(f"[tr{i}]")
    return chains, duck, plain


def mix_with_tracks(parts: list[str], voice: str, duck: list[str], plain: list[str]) -> str:
    """Append the graph that sums dialogue + tracks; the `duck` group is lowered by a side-chain compressor keyed on the dialogue."""
    label = voice
    if duck:
        bed = duck[0]
        if len(duck) > 1:
            parts.append("".join(duck) + f"amix=inputs={len(duck)}:duration=longest:normalize=0[bed]")
            bed = "[bed]"
        parts.append(f"{voice}asplit=2[vkey][vmix]")
        parts.append(f"{bed}[vkey]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[ducked]")
        ins = ["[vmix]", "[ducked]"] + plain
    else:
        ins = [voice] + plain
    if len(ins) == 1:
        return ins[0]
    parts.append("".join(ins) + f"amix=inputs={len(ins)}:duration=first:normalize=0[mixed2]")
    label = "[mixed2]"
    return label


def assemble(shots: list[ShotSpec], clips: list[Path], opts: RenderOptions, out_path: Path, workdir: Path, *, ctx=None,
             on_progress=None) -> dict:
    """Join already-rendered clips. Returns {path, timeline, duration, cues}. Output is probed by the caller."""
    if not shots or len(shots) != len(clips):
        raise ffmpeg.FFmpegError("assemble needs one clip per shot")
    timeline = plan_timeline(shots)
    workdir.mkdir(parents=True, exist_ok=True)
    cues = build_cues(shots, timeline) if opts.subtitles else []
    has_subs = bool(cues)
    if has_subs:
        subtitles.write_ass(workdir / "sub.ass", cues, opts.width, opts.height, opts.subtitle_style)
        fonts = workdir / "fonts"
        fonts.mkdir(exist_ok=True)
        for f in FONT_DIR.glob("*.ttf"):
            shutil.copyfile(f, fonts / f.name)
    graph = build_filter(shots, timeline, opts, len(clips), len(clips), has_subs)
    script = workdir / "filter.txt"
    script.write_text(graph, encoding="utf-8")
    args: list[str] = []
    for c in clips:
        args += ["-i", str(c)]
    for s in shots:
        if s.audio:
            args += ["-i", s.audio]
    if opts.music:
        args += ["-i", opts.music]
    for t in opts.tracks:
        args += ["-i", t["file"]]
    total = total_duration(timeline)
    args += [*ffmpeg.filter_complex_args(script), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", opts.preset,
             "-crf", str(opts.crf), "-pix_fmt", "yuv420p", "-r", str(opts.fps), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_path)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(args, ctx=ctx, cwd=workdir, expected_sec=total, on_progress=on_progress)
    return {"path": str(out_path), "timeline": timeline, "duration": total, "cues": len(cues)}


def extract_cover(video: Path, out_png: Path, at: float = 1.0) -> Path:
    ffmpeg.run(["-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out_png)])
    return out_png


def estimate_render_seconds(total_sec: float, opts: RenderOptions) -> float:
    """Rough CPU estimate (labelled as such in the UI); replaced by measured job times once renders have run."""
    px = opts.width * opts.height * opts.fps
    return round(total_sec * math.sqrt(px / (540 * 960 * 15)) * 1.2, 1)
