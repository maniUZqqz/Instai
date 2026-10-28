"""Retake: regenerate one time range of a rendered episode and stitch it back without touching the rest.

Idea from NMarketing's regen tool (Qasem services/video/regen: the frame before the cut and the first frame after it are the model's first and
last frame; colour match; seam blending; exact A/V sync; audio replace / mute / cut), reimplemented here with ffmpeg + Pillow only:

  1. plan      frame numbers of the range (exact on the source's frame grid), the boundary frames b (just before) and a (just after).
  2. piece     (done by production/retakes.py through the GPU router) a Wan clip from b to a, `n` frames long.
  3. fit       colour-match to the boundaries, scale/crop/re-time to the source's size, fps and exactly `n` frames; the first/last few frames are
               cross-blended with the original frames so the seams do not pop.
  4. stitch    ONE ffmpeg pass: source[0:s) + piece + source[e:], video re-encoded once; audio per mode.
  5. verify    duration, frame count, A/V length and a seam score (frame difference at the seam vs the clip's normal motion).

Audio modes: keep (original untouched), mute (silence over the range), replace (another audio file over the range), cut (remove the range from
video and audio, no generation).
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from . import colormatch, ffmpeg

MIN_SECONDS, MAX_SECONDS = 0.4, 10.0
BLEND = 3                          # frames cross-blended at each seam
AUDIO_MODES = ("keep", "mute", "replace", "cut")


class RetakeError(ValueError):
    pass


@dataclass
class Plan:
    fps: float
    width: int
    height: int
    total_frames: int
    start: int            # first replaced frame
    end: int              # first frame after the range (exclusive end)
    before: int           # frame just before the range (the model's first frame)
    after: int            # frame at `end` (the model's last frame)

    @property
    def n(self) -> int:
        return self.end - self.start

    @property
    def t_start(self) -> float:
        return self.start / self.fps

    @property
    def t_end(self) -> float:
        return self.end / self.fps

    @property
    def seconds(self) -> float:
        return self.n / self.fps


def plan_range(info: dict, start_sec: float, end_sec: float, *, cut: bool = False) -> Plan:
    fps = float(info["fps"] or 0)
    if fps <= 0 or not info.get("has_video"):
        raise RetakeError("the source has no video stream")
    total = int(round(info["duration"] * fps))
    if end_sec <= start_sec:
        raise RetakeError("the end of the range must be after its start")
    s = max(0, int(round(start_sec * fps)))
    e = min(total, int(round(end_sec * fps)))
    if s >= total:
        raise RetakeError("the range is outside the video")
    if (e - s) / fps < MIN_SECONDS and not cut:
        raise RetakeError(f"the range must be at least {MIN_SECONDS} s")
    if (e - s) / fps > MAX_SECONDS and not cut:
        raise RetakeError(f"a retake is at most {MAX_SECONDS:.0f} s; split the range")
    if e - s < 1 or s >= total:
        raise RetakeError("the range is outside the video")
    return Plan(fps=fps, width=int(info["width"]), height=int(info["height"]), total_frames=total, start=s, end=e, before=max(0, s - 1), after=min(total - 1, e))


def extract_frame(video: Path, index: int, fps: float, out_png: Path) -> Path:
    ffmpeg.run(["-i", str(video), "-vf", f"select=eq(n\\,{index})", "-vsync", "0", "-frames:v", "1", str(out_png)])
    if not out_png.exists():
        raise RetakeError(f"could not read frame {index}")
    return out_png


def extract_frames(video: Path, first: int, count: int, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(["-i", str(video), "-vf", f"select=between(n\\,{first}\\,{first + count - 1})", "-vsync", "0", str(folder / "f%03d.png")])
    return sorted(folder.glob("f*.png"))


def reference_between(before_png: Path, after_png: Path, out_png: Path) -> Path:
    """The colour reference of the piece: the average of the two boundary frames."""
    a, b = Image.open(before_png).convert("RGB"), Image.open(after_png).convert("RGB").resize(Image.open(before_png).size)
    Image.blend(a, b, 0.5).save(out_png)
    return out_png


def fit_piece(piece: Path, plan: Plan, source: Path, out: Path, *, blend: int = BLEND, edge: int = 0, ctx=None) -> Path:
    """Scale/crop/re-time `piece` to the source's size and fps and EXACTLY plan.n frames; blend the seams with the original frames.
    `edge` = frames at each end of the piece that are the boundary frames themselves (the model's first and last frame): they are made and then dropped."""
    pinfo = ffmpeg.probe(piece)
    p_dur = max(0.1, pinfo["duration"] or (pinfo["fps"] and 1.0) or 1.0)
    total_in = plan.n + 2 * edge
    stretch = (total_in / plan.fps) / p_dur
    w, h, fps, n = plan.width, plan.height, plan.fps, plan.n
    work = Path(tempfile.mkdtemp(prefix="retake-"))
    fitted = work / "fitted.mp4"
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setpts=PTS*{stretch:.6f},fps={fps},setsar=1,"
          f"tpad=stop_mode=clone:stop_duration=1,format=yuv420p")
    ffmpeg.run(["-i", str(piece), "-vf", vf, "-frames:v", str(total_in), "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-an", str(fitted)], ctx=ctx)
    k = min(blend, max(0, n // 2 - 1))
    head = extract_frames(source, plan.start, k, work / "head") if k else []
    tail = extract_frames(source, plan.end - k, k, work / "tail") if k else []
    ff, _ = ffmpeg.binaries()
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-", "-an",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    written = 0
    try:
        for raw_i, fr in enumerate(colormatch.read_frames(fitted, w, h)):
            i = raw_i - edge
            if i < 0:
                continue
            if i >= n:
                break
            if i < len(head):                               # at the start the original still dominates, then the new footage takes over
                wgt = (i + 1) / (k + 1)
                fr = Image.blend(Image.open(head[i]).convert("RGB").resize((w, h)), fr, wgt)
            elif i >= n - len(tail):
                j = i - (n - len(tail))
                wgt = 1 - (j + 1) / (k + 1)
                fr = Image.blend(Image.open(tail[j]).convert("RGB").resize((w, h)), fr, wgt)
            enc.stdin.write(fr.tobytes())
            written += 1
        enc.stdin.close()
        err = enc.stderr.read().decode("utf-8", "replace")
        if enc.wait() != 0:
            raise ffmpeg.FFmpegError("could not encode the piece: " + err[-300:])
    except BaseException:
        enc.kill()
        raise
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
    if written != n:
        raise RetakeError(f"the piece has {written} frames, {n} were needed")
    return out


def stitch(source: Path, piece: Path | None, plan: Plan, out: Path, *, audio_mode: str = "keep", audio_file: Path | None = None, ctx=None) -> Path:
    """source[0:start) + piece + source[end:], video encoded once with the source's size/fps, audio as the mode says (A/V stay in sync)."""
    if audio_mode not in AUDIO_MODES:
        raise RetakeError("unknown audio mode")
    info = ffmpeg.probe(source)
    has_audio = info["has_audio"]
    t0, t1 = plan.t_start, plan.t_end
    s, e = plan.start, plan.end
    parts = []
    vf = []
    if s > 0:
        vf.append(f"[0:v]trim=start_frame=0:end_frame={s},setpts=PTS-STARTPTS[a]")
        parts.append("[a]")
    if piece is not None:
        vf.append("[1:v]setpts=PTS-STARTPTS[b]")
        parts.append("[b]")
    if e < plan.total_frames:
        vf.append(f"[0:v]trim=start_frame={e},setpts=PTS-STARTPTS[c]")
        parts.append("[c]")
    if not parts:
        raise RetakeError("nothing would be left of the video")
    vf.append("".join(parts) + f"concat=n={len(parts)}:v=1:a=0,fps={plan.fps},setsar=1,format=yuv420p[v]")
    args = ["-i", str(source)]
    if piece is not None:
        args += ["-i", str(piece)]
    af = []
    amap: list[str] = []
    if has_audio:
        if audio_mode == "keep" and piece is not None:
            amap = ["-map", "0:a", "-c:a", "copy"]
        elif audio_mode == "mute" and piece is not None:
            af.append(f"[0:a]volume=enable='between(t,{t0:.4f},{t1:.4f})':volume=0[a_out]")
            amap = ["-map", "[a_out]", "-c:a", "aac", "-b:a", "160k"]
        elif audio_mode == "replace" and piece is not None:
            if audio_file is None:
                raise RetakeError("audio mode 'replace' needs an audio file")
            idx = 2
            args += ["-i", str(audio_file)]
            ms = int(round(t0 * 1000))
            af.append(f"[0:a]volume=enable='between(t,{t0:.4f},{t1:.4f})':volume=0[a0]")
            af.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{t1 - t0:.4f},asetpts=PTS-STARTPTS,adelay={ms}|{ms}[a1]")
            af.append("[a0]aformat=channel_layouts=stereo[a0s]")
            af.append("[a0s][a1]amix=inputs=2:normalize=0:duration=first[a_out]")
            amap = ["-map", "[a_out]", "-c:a", "aac", "-b:a", "160k"]
        elif audio_mode == "cut":
            segs = []
            if t0 > 0:
                af.append(f"[0:a]atrim=0:{t0:.4f},asetpts=PTS-STARTPTS,afade=t=out:st={max(0.0, t0 - 0.01):.4f}:d=0.01[x]")
                segs.append("[x]")
            if s < plan.total_frames and e < plan.total_frames:
                af.append(f"[0:a]atrim=start={t1:.4f},asetpts=PTS-STARTPTS,afade=t=in:d=0.01[y]")
                segs.append("[y]")
            af.append("".join(segs) + f"concat=n={len(segs)}:v=0:a=1[a_out]")
            amap = ["-map", "[a_out]", "-c:a", "aac", "-b:a", "160k"]
        else:
            amap = ["-map", "0:a", "-c:a", "copy"]
    graph = ";".join(vf + af)
    script = out.parent / (out.stem + ".filter.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(graph, encoding="utf-8")
    ffmpeg.run([*args, *ffmpeg.filter_complex_args(script), "-map", "[v]", *amap, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-r", f"{plan.fps}",
                "-movflags", "+faststart", str(out)], ctx=ctx, expected_sec=info["duration"])
    script.unlink(missing_ok=True)
    return out


def frame_difference(video: Path, first: int, count: int) -> list[float]:
    """Mean absolute luma difference between consecutive frames of a window (small thumbnails)."""
    work = Path(tempfile.mkdtemp(prefix="seam-"))
    try:
        frames = extract_frames(video, max(0, first), count, work)
        prev, out = None, []
        for f in frames:
            im = Image.open(f).convert("L").resize((96, 96))
            if prev is not None:
                out.append(ImageStat.Stat(ImageChops.difference(prev, im)).mean[0])
            prev = im
        return out
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


def seam_ratio(video: Path, seam_frame: int, window: int = 12) -> float:
    """Frame difference AT a seam divided by the median difference around it (1 = as smooth as the rest; > 3 = a visible pop)."""
    first = max(0, seam_frame - window)
    d = frame_difference(video, first, window * 2 + 1)
    if len(d) < 4:
        return 1.0
    at = seam_frame - first - 1
    around = sorted(x for i, x in enumerate(d) if abs(i - at) > 1)
    med = around[len(around) // 2] or 0.5
    return round(max(d[max(0, at - 1):at + 2] or [0]) / max(med, 0.5), 2)


def verify(source_info: dict, out: Path, plan: Plan, audio_mode: str) -> dict:
    """Exact-sync checks on the result."""
    info = ffmpeg.probe(out)
    removed = plan.seconds if audio_mode == "cut" else 0.0
    expected = source_info["duration"] - removed
    frames = int(round(info["duration"] * (info["fps"] or plan.fps)))
    expected_frames = plan.total_frames - (plan.n if audio_mode == "cut" else 0)
    res = {"duration": info["duration"], "expected_duration": round(expected, 3), "duration_error": round(info["duration"] - expected, 3), "frames": frames,
           "expected_frames": expected_frames, "fps": info["fps"], "size": f"{info['width']}x{info['height']}", "has_audio": info["has_audio"]}
    if info["has_audio"]:
        a = ffmpeg.probe(out)
        res["audio_video_diff"] = None
        try:
            ff, _ = ffmpeg.binaries()
            p = subprocess.run([ff, "-hide_banner", "-i", str(out)], capture_output=True, text=True, timeout=60)
            import re

            m = re.findall(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
            if m:
                res["container_duration"] = int(m[0][0]) * 3600 + int(m[0][1]) * 60 + float(m[0][2])
            streams = re.findall(r"Stream #0:\d.*?(Video|Audio):", p.stderr)
            res["streams"] = streams
            del a
        except (OSError, subprocess.SubprocessError):
            pass
    res["ok"] = abs(res["duration_error"]) <= 1.5 / (info["fps"] or plan.fps) + 0.05 and abs(frames - expected_frames) <= 2 and (info["has_audio"] == source_info["has_audio"])
    return res
