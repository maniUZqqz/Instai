"""A real check of the caption engine, used by the PC self-test (`instai/ops/pcselftest.py`, row `captions`) and by tests/test_captions_render.py.

Each preset renders one second of a flat dark clip through the REAL ffmpeg + libass, and the frame is judged:
  * there is caption ink at all (the font loaded, the shaper worked, libass drew it),
  * every inked pixel lies inside the safe zone of the platform (the captions never sit under the app's buttons),
  * the ASS script has no unescaped brace (a hostile text cannot inject tags),
  * the colours passed the contrast rule (4.5:1) - that is part of `captions.plan`'s info.
It skips (not fails) when this ffmpeg has no `ass` filter: the ffmpeg row of the self-test already says so.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from . import captions, ffmpeg, safezones, titles_ass

BG = "#101820"
SIZES = {"vertical": (360, 640), "landscape": (640, 360)}
SAMPLE = {"fa": "سلام دنیا، این یک آزمون است", "en": "Hello world, this is a test"}
HOSTILE = "{\\an9\\pos(1,1)}بد}{ \\N \\h"       # tags, braces and escapes typed into a caption
TOLERANCE = 0.02                                 # of the frame size: antialiasing and the outline


def braces_clean(ass: str) -> bool:
    """True when every brace of the Dialogue texts is either escaped or part of OUR own override block (one that starts with a backslash tag)."""
    for line in ass.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        text = line.split(",", 9)[9]
        text = re.sub(r"\\[{}]", "", text)                      # escaped braces are just characters
        text = re.sub(r"\{\\[^{}]*\}", "", text)                # the engine's own tag blocks
        if "{" in text or "}" in text:
            return False
    return True


def injection_ok() -> bool:
    """A caption with tags and braces typed into its text makes an ASS whose only tag blocks are the engine's, and the typed braces survive as escaped characters."""
    plan = captions.plan([{"text": HOSTILE, "start": 0.0, "duration": 2.0}], {"preset": "pop", "mode": "burned"}, 360, 640)
    ass = plan["ass"] or ""
    return bool(ass) and braces_clean(ass) and "\\{" in ass and "\\}" in ass


def _ink_box(png: Path) -> tuple[tuple[int, int, int, int] | None, int]:
    """(bounding box, pixel count) of everything that differs from the flat background."""
    from PIL import Image, ImageChops

    base = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    im = Image.open(png).convert("RGB")
    r, g, b = ImageChops.difference(im, Image.new("RGB", im.size, base)).split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda v: 255 if v > 24 else 0)
    return mask.getbbox(), mask.histogram()[255]


def check_preset(preset: str, work: str | Path, *, shape: str = "vertical", language: str = "fa", platform: str = "instagram", look: dict | None = None,
                 text: str | None = None, zone: str = safezones.AUTO) -> dict:
    """Render `preset` once and judge the frame. {preset, shape, ok, ink, bbox, inside, braces, contrast, zone, seconds, reason}."""
    t0 = time.time()
    w, h = SIZES[shape]
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    seg = [{"text": text or SAMPLE["en" if language == "en" else "fa"], "start": 0.0, "duration": 1.0}]
    plan = captions.plan(seg, {"preset": preset, "mode": "burned", "zone": zone}, w, h, look=look, language=language, platform=platform)
    row = {"preset": preset, "shape": shape, "ok": False, "ink": 0, "bbox": None, "inside": False, "braces": True, "contrast": (plan["info"] or {}).get("contrast"),
           "zone": (plan["info"] or {}).get("zone"), "reason": ""}
    if not plan["ass"]:
        row["reason"] = "no ASS script (the preset is the plain classic look)"
        return row
    row["braces"] = braces_clean(plan["ass"])
    fonts = work / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in titles_ass.FONTS_DIR.glob("*.ttf"):
        shutil.copyfile(f, fonts / f.name)
    (work / "sub.ass").write_text(plan["ass"], encoding="utf-8")
    clip = plan["clips"][0]
    t = clip["at"] + min(clip["duration"] - 0.1, titles_ass.entrance_seconds(clip) + 0.25)
    png = work / f"{preset}-{shape}.png"
    ffmpeg.run(["-f", "lavfi", "-i", f"color=c={BG}:s={w}x{h}:d=1.5:r=25", "-ss", f"{t:.2f}", "-vf", titles_ass.ass_filter("sub.ass", "fonts"), "-frames:v", "1", str(png)],
               cwd=work, timeout=60)
    bbox, ink = _ink_box(png)
    row.update(ink=ink, bbox=list(bbox) if bbox else None)
    if not bbox or ink < 40:
        row["reason"] = "the frame has no caption ink"
        return row
    m = safezones.margins(row["zone"])
    tol_x, tol_y = TOLERANCE * w, TOLERANCE * h
    left, top, right, bottom = bbox
    row["inside"] = (left >= m["left"] * w - tol_x and right <= (1 - m["right"]) * w + tol_x and top >= m["top"] * h - tol_y and bottom <= (1 - m["bottom"]) * h + tol_y)
    if not row["inside"]:
        row["reason"] = f"the captions leave the safe zone {row['zone']}: ink {bbox}, frame {w}x{h}"
    elif not row["braces"]:
        row["reason"] = "the ASS has an unescaped brace"
    else:
        row["ok"] = True
    row["seconds"] = round(time.time() - t0, 2)
    return row


def run(work: str | Path, *, shapes=("vertical",), language: str = "fa", presets=None) -> list[dict]:
    """The check for every preset (the seven of NM) in each frame shape. Raises `ffmpeg.FFmpegError` when ffmpeg is missing or a render fails."""
    return [check_preset(p, Path(work) / f"{p}-{s}", shape=s, language=language) for s in shapes for p in (presets or captions.NEW_PRESETS)]
