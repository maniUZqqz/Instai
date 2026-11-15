"""SubRip (.srt) files: the "soft" copy of the captions that travels next to the video. A platform that takes a subtitle file (YouTube, for one) shows it as the video's own
subtitles and lets the viewer switch it off; it is also what accessibility checks ask for.

SOURCE: ported from NMarketing:backend/services/video/subtitles.py (wrap, tidy, to_srt, write_srt) @ v3.02 (c23f861), adapted for InstAI: the NM scene /
Whisper plumbing is left out (InstAI already knows the text of every cue).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Longer than this and a line stops being readable in the two seconds it is on screen. The number is on the low side for Persian, where the script is dense.
MAX_LINE = 42
#: Two lines is the ceiling every subtitle guideline agrees on.
MAX_LINES = 2
#: A cue shorter than this flashes. One longer than that outstays a short scene.
MIN_CUE = 0.8
MAX_CUE = 7.0


@dataclass
class SrtCue:
    index: int
    start: float
    end: float
    text: str

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


def _stamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms_total = int(round(seconds * 1000))
    hours, rest = divmod(ms_total, 3600 * 1000)
    minutes, rest = divmod(rest, 60 * 1000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def wrap(text: str, width: int = MAX_LINE) -> str:
    """Break one cue across at most two lines, on a space. Never mid-word: Persian joins letters, and a word split across two subtitle lines is unreadable."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) <= MAX_LINES:
        return "\n".join(lines)
    # too long for two lines: split near the middle instead of truncating (losing half a sentence is worse than a slightly wide line)
    middle = len(words) // 2
    return "\n".join([" ".join(words[:middle]), " ".join(words[middle:])])


def _join(first: SrtCue, second: SrtCue) -> SrtCue:
    first.end = second.end
    first.text = wrap(f"{first.text} {second.text}".replace("\n", " "))
    return first


def tidy(cues: list[SrtCue]) -> list[SrtCue]:
    """Merge cues too short to read, and cap ones that outstay their welcome. A short cue joins whichever neighbour it can: backwards normally, forwards
    when it is the first one (a 0.3-second flash at the very start has no predecessor to merge into)."""
    if not cues:
        return []
    merged: list[SrtCue] = []
    pending: SrtCue | None = None
    for cue in cues:
        if pending is not None:
            cue = _join(pending, cue)
            pending = None
        if cue.seconds < MIN_CUE:
            if merged and merged[-1].seconds < MAX_CUE:
                _join(merged[-1], cue)
                continue
            pending = cue
            continue
        merged.append(cue)
    if pending is not None:
        pending.end = max(pending.end, pending.start + MIN_CUE)       # a short final cue with nothing after it: stretch rather than flash
        merged.append(pending)
    for cue in merged:
        if cue.seconds > MAX_CUE:
            cue.end = cue.start + MAX_CUE
    for position, cue in enumerate(merged, start=1):
        cue.index = position
    return merged


def to_srt(cues: list[SrtCue]) -> str:
    blocks = [f"{c.index}\n{_stamp(c.start)} --> {_stamp(c.end)}\n{c.text}\n" for c in cues]
    return "\n".join(blocks)


def write_srt(cues: list[SrtCue], out_path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 with a BOM: some players still guess the encoding of a subtitle file, and a Persian subtitle guessed as cp1256 is unreadable mojibake.
    out.write_text(to_srt(cues), encoding="utf-8-sig")
    return out


def cues_from_groups(groups: list[dict]) -> list[SrtCue]:
    """Word groups ([{text, s, e}] in timeline seconds) -> tidy, wrapped, numbered cues. A cue is held until the next one starts (a gap shorter than a
    second is closed, so the line does not blink between two sentences)."""
    cues = [SrtCue(i + 1, g["s"], g["e"], wrap(g["text"])) for i, g in enumerate(groups) if g.get("text", "").strip()]
    for a, b in zip(cues, cues[1:]):
        if 0 < b.start - a.end < 1.0:
            a.end = b.start
    return tidy(cues)
