"""Real pictures of the caption presets for the picker: one frame of a gradient in the series' own colours with a sample line burned in by the SAME engine that
renders the episode (ASS through ffmpeg / libass) - never a CSS imitation, so the picker shows exactly what the video will have.

The picture is made with a one-frame lavfi source (`gradients`, or a plain `color` when this ffmpeg lacks it) and the `ass` filter; it is cached on disk under a hash of
everything that changes it (preset, palette, typography, language, frame shape, safe zone), so the picker is instant the second time and a new look makes new pictures.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from . import captions, contrast, ffmpeg, safezones, subtitles, titles_ass

SAMPLES = {"fa": "این یک نمونهٔ زیرنویسِ کلمه‌به‌کلمه است", "en": "This is how your captions will look"}
SHAPES = {"vertical": (450, 800), "landscape": (800, 450)}
SAMPLE_SECONDS = 2.8
VERSION = "captions-preview@1"


def _hash(preset: str, look: dict | None, language: str, shape: str, zone: str, platform: str, position: str) -> str:
    blob = json.dumps([preset, captions.palette_of(look), ((look or {}).get("typography") or {}), language, shape, zone, platform, position, VERSION], sort_keys=True,
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def sample_segments(language: str) -> list[dict]:
    return [{"text": SAMPLES["en" if language == "en" else "fa"], "start": 0.0, "duration": SAMPLE_SECONDS}]


def _frame_time(plan: dict, segments: list[dict]) -> float:
    """When to take the frame: the entrance animation is over, and a word in the middle of the first line is the one being spoken (so the highlight shows)."""
    clip = plan["clips"][0] if plan["clips"] else None
    if clip is None:
        return 1.0
    words = clip.get("words") or []
    d_in = titles_ass.entrance_seconds(clip)
    mid = (words[min(2, len(words) - 1)]["s"] + words[min(2, len(words) - 1)]["e"]) / 2 if words else clip["duration"] / 2
    return clip["at"] + min(clip["duration"] - 0.1, max(mid, d_in + 0.05))


def _source(w: int, h: int, look: dict | None, gradient: bool) -> str:
    pal = captions.palette_of(look)
    a, b = pal["background"], pal["primary"]
    if gradient:
        return f"gradients=s={w}x{h}:c0={a}:c1={b}:x0=0:y0=0:x1={w}:y1={h}:d=3:r=25"
    return f"color=c={contrast.mix(a, b, 0.5)}:s={w}x{h}:d=3:r=25"


def render_preview(preset: str, look: dict | None, out_png: str | Path, *, language: str = "fa", shape: str = "vertical", zone: str = safezones.AUTO,
                   platform: str = "instagram", position: str = "bottom", subtitle_style: dict | None = None) -> dict:
    """One picture of `preset` (a key of `captions.PRESETS`). Returns {path, zone, contrast, ...}. Raises ffmpeg.FFmpegError when ffmpeg / libass is missing."""
    w, h = SHAPES.get(shape, SHAPES["vertical"])
    segments = sample_segments(language)
    cfg = {"preset": preset, "mode": "burned", "zone": zone}
    plan = captions.plan(segments, cfg, w, h, look=look, language=language, platform=platform, position=position)
    work = Path(tempfile.mkdtemp(prefix="capprev-"))
    try:
        fonts = work / "fonts"
        fonts.mkdir()
        for f in titles_ass.FONTS_DIR.glob("*.ttf"):
            shutil.copyfile(f, fonts / f.name)
        if plan["ass"]:
            (work / "sub.ass").write_text(plan["ass"], encoding="utf-8")
            t = _frame_time(plan, segments)
        else:                                                        # "classic": the plain look InstAI always had
            cues = subtitles.make_cues(segments[0]["text"], 0.0, SAMPLE_SECONDS)
            subtitles.write_ass(work / "sub.ass", cues, w, h, subtitle_style)
            t = 1.0
        out = Path(out_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        err = None
        for gradient in (True, False):
            try:
                ffmpeg.run(["-f", "lavfi", "-i", _source(w, h, look, gradient), "-ss", f"{t:.2f}", "-vf", titles_ass.ass_filter("sub.ass", "fonts"), "-frames:v", "1",
                            str(work / "out.png")], cwd=work, timeout=60)
                err = None
                break
            except ffmpeg.FFmpegError as e:
                err = e
        if err is not None:
            raise err
        shutil.move(str(work / "out.png"), str(out))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    info = plan["info"]
    return {"path": str(out), "zone": info.get("zone"), "contrast": info.get("contrast"), "width": w, "height": h}


KEEP_PICTURES = 400            # a preview is a cache (it is made again when missing); the folder never grows past this many files


def prune(cache_dir: str | Path, keep: int = KEEP_PICTURES) -> int:
    """Delete the oldest preview pictures beyond `keep`. Only files of this cache folder, only *.png. Returns how many were removed."""
    files = sorted(Path(cache_dir).glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    removed = 0
    for f in files[keep:]:
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def previews(look: dict | None, cache_dir: str | Path, url_base: str, *, language: str = "fa", shape: str = "vertical", zone: str = safezones.AUTO,
             platform: str = "instagram", position: str = "bottom", subtitle_style: dict | None = None) -> list[dict]:
    """Every preset with the URL of its picture (made now when it is not on disk yet). A preset whose picture cannot be made carries `error` and no `url`."""
    cache = Path(cache_dir)
    out = []
    for key in captions.ORDER:
        p = captions.PRESETS[key]
        row = {"key": key, "fa": p["fa"], "en": p["en"], "hint_fa": p["hint_fa"], "hint_en": p["hint_en"], "legacy": bool(p.get("legacy")), "url": None}
        salt = position + json.dumps(subtitle_style or {}, sort_keys=True) if p.get("legacy") else position      # the plain look follows the page's own subtitle settings
        h = _hash(key, look, language, shape, zone, platform, salt)
        png = cache / f"{h}.png"
        if not p.get("legacy"):
            row["contrast"] = captions.resolve_style(key, look, language=language)["contrast"]
        try:
            if not png.is_file():
                render_preview(key, look, png, language=language, shape=shape, zone=zone, platform=platform, position=position, subtitle_style=subtitle_style)
            row["url"] = f"{url_base.rstrip('/')}/{h}.png"
        except (ffmpeg.FFmpegError, OSError) as e:
            row["error"] = str(e)[:200]
        out.append(row)
    prune(cache)
    return out
