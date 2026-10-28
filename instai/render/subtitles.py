"""Persian (RTL) subtitles as an ASS file burned in by ffmpeg's libass (HarfBuzz shaping + FriBidi ordering).

The bundled Vazirmatn font (SIL OFL, instai/render/fonts) makes the result identical on every PC. Cues are timed from the real
narration audio of each shot, split into short readable chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

RLM = "‏"  # right-to-left mark: forces an RTL paragraph even when a line starts with a number or Latin word
MAX_WORDS, MAX_CHARS = 7, 38


@dataclass
class Cue:
    start: float
    end: float
    text: str


def split_text(text: str) -> list[str]:
    """Chunks of at most MAX_WORDS words / MAX_CHARS characters, preferring to break after punctuation."""
    words = text.split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        line = " ".join(cur)
        end_punct = bool(re.search(r"[.!?؟،,؛:…]$", w))
        if len(cur) >= MAX_WORDS or len(line) >= MAX_CHARS or (end_punct and len(cur) >= 3):
            chunks.append(line)
            cur = []
    if cur:
        if chunks and len(cur) == 1 and len(chunks[-1].split()) < MAX_WORDS:  # no one-word orphan
            chunks[-1] += " " + cur[0]
        else:
            chunks.append(" ".join(cur))
    return chunks


def make_cues(text: str, start: float, duration: float) -> list[Cue]:
    chunks = split_text(text)
    if not chunks or duration <= 0:
        return []
    weights = [max(1, len(c)) for c in chunks]
    total = float(sum(weights))
    t, cues = start, []
    for c, w in zip(chunks, weights):
        d = duration * w / total
        cues.append(Cue(round(t, 3), round(t + d, 3), c))
        t += d
    return cues


def _ts(sec: float) -> str:
    cs = int(round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _ass_color(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    h = h if len(h) == 6 else "FFFFFF"
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()  # ASS is BGR


def build_ass(cues: list[Cue], width: int, height: int, style: dict | None = None) -> str:
    style = style or {}
    size = int(style.get("size") or 64) * height / 1920
    font = "Vazirmatn" if style.get("font") in (None, "", "Tahoma", "Vazirmatn") else style["font"]
    pos = style.get("position", "bottom")
    align, margin_v = {"top": (8, 0.08), "middle": (5, 0.0)}.get(pos, (2, 0.09))
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{size:.0f},{_ass_color(style.get('color', '#FFFFFF'))},&H000000FF,{_ass_color(style.get('outline', '#000000'))},"
        f"&H64000000,-1,0,0,0,100,100,0,0,1,{max(2, size / 14):.1f},0,{align},{int(width * 0.06)},{int(width * 0.06)},{int(height * margin_v)},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Default,,0,0,0,,{RLM}{_esc(c.text)}" for c in cues]
    return head + "\n".join(lines) + "\n"


def write_ass(path: str | Path, cues: list[Cue], width: int, height: int, style: dict | None = None) -> Path:
    Path(path).write_text(build_ass(cues, width, height, style), encoding="utf-8")
    return Path(path)
