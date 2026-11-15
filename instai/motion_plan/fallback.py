"""The deterministic scene plan: a motion-graphics shot gets a real plan from its NARRATION alone, with no model.

Used when no text model is reachable (and by the tests): the narration is cut into short chunks at sentence and clause ends; each chunk becomes the component
that fits it - a number => `stat`, a listing of three or more things => `list`, a sequence («first ... then ...») => `steps`, anything else => `kinetic_title` -
and the scenes share the shot's duration. The scene's `cues` (when each word is spoken) are estimated from the characters of the words inside the scene's
own span of the narration audio, exactly as InstAI times its subtitles.

Nothing is invented: every text on screen is a piece of the narration, and a number gets a `source` only when one of the episode's VERIFIED sources
contains it (otherwise specs.py marks the scene «example»).
"""
from __future__ import annotations

import re

from . import motionlib, specs, timeline

_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")
SENT_END = re.compile(r"(?<=[.!?؟…])\s+|\n+")
CLAUSE = re.compile(r"(?<=[،,؛;:])\s+")
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s*(%|٪|درصد|percent|per cent)?", re.I)
SEQ_FA = ("ابتدا", "اول", "سپس", "بعد", "پس از آن", "در نهایت", "آخر", "نهایتاً", "مرحله")
SEQ_EN = ("first", "then", "next", "after that", "finally", "step")
MAX_CHUNK_WORDS = 14
MIN_SCENE_S = 2.0


def _words(t: str) -> list:
    return [w for w in re.split(r"\s+", t.strip()) if w]


def chunks(narration: str, *, max_words: int = MAX_CHUNK_WORDS) -> list:
    """Short readable pieces: sentences first, a long sentence is cut after a comma, else at the word limit. A one-word tail is joined to the piece before."""
    text = re.sub(r"\s+", " ", (narration or "").replace("\r", "")).strip()
    if not text:
        return []
    out: list = []
    for sent in [s.strip() for s in SENT_END.split(text) if s.strip()]:
        parts = [sent]
        if len(_words(sent)) > max_words:
            parts = [p.strip() for p in CLAUSE.split(sent) if p.strip()]
        cur: list = []
        for p in parts:
            w = _words(p)
            if cur and len(cur) + len(w) > max_words:
                out.append(" ".join(cur))
                cur = []
            cur += w
            while len(cur) > max_words + 4:                 # a clause that is too long: cut at the word limit
                out.append(" ".join(cur[:max_words]))
                cur = cur[max_words:]
        if cur:
            if len(cur) == 1 and out:
                out[-1] += " " + cur[0]
            else:
                out.append(" ".join(cur))
    return out


def _clean(t: str, n: int) -> str:
    return re.sub(r"\s+", " ", t).strip(" \t\n.,،؛;:!؟?…")[:n]


def _is_year(num: str, unit: str) -> bool:
    return not unit and re.fullmatch(r"\d{4}", num) is not None and 1000 <= int(num) <= 2200


def _numbers(chunk: str) -> list:
    out = []
    for m in NUM.finditer(chunk.translate(_DIG)):
        num = m.group(1).replace(",", "")
        if m.group(1).count(",") and not re.fullmatch(r"\d{1,3}(,\d{3})+", m.group(1)):
            num = m.group(1).replace(",", ".")
        if _is_year(num, m.group(2) or ""):
            continue
        out.append((num, bool(m.group(2))))
    return out


def _items(chunk: str):
    """«A، B و C» => [A, B, C] when there are 3 to 6 short items; else None."""
    t = _clean(chunk, 600)
    parts = re.split(r"\s*[،,;؛]\s*|\s+(?:و|and)\s+", t)
    parts = [_clean(p, 120) for p in parts if _clean(p, 120)]
    if 3 <= len(parts) <= 6 and all(len(_words(p)) <= 6 for p in parts) and max(len(_words(p)) for p in parts) >= 1:
        return parts
    return None


def _is_sequence(chunk: str, lang: str) -> bool:
    low = chunk.lower()
    marks = SEQ_FA if lang == "fa" else SEQ_EN
    return sum(1 for m in marks if m in low) >= 2


def _steps(chunk: str, lang: str):
    seps = r"(?:سپس|بعد از آن|بعد|در نهایت|و آخر)" if lang == "fa" else r"(?:then|next|after that|finally)"
    parts = [_clean(p, 60) for p in re.split(seps, chunk, flags=re.I)]
    parts = [re.sub(r"^(?:ابتدا|اول|first)\s*", "", p, flags=re.I).strip() for p in parts if p]
    parts = [p for p in parts if p]
    return [{"title": p} for p in parts[:5]] if 2 <= len(parts) <= 5 else None


def estimate_cues(text: str, span: float, *, start: float = 0.05) -> list:
    """Word timings inside a scene, scene-local seconds: the words are said from `start` on, for `span` seconds, and characters weigh the time a word takes
    (the way InstAI times its subtitles)."""
    words = _words(text)
    if not words or span <= 0:
        return []
    usable = max(0.2, span * 0.92)
    weights = [len(w) + 1 for w in words]
    total = float(sum(weights))
    t, out = max(0.0, start), []
    for w, k in zip(words, weights):
        d = usable * k / total
        out.append({"w": w[:40], "s": round(t, 3), "e": round(t + d, 3)})
        t += d
    return out


def _source_for(num: str, sources) -> str:
    """The title of a VERIFIED source whose own text contains this number (else ''): the only way a number on screen is not an example."""
    for s in sources or []:
        body = str(s.get("extract") or "").translate(_DIG)
        if num and re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", body):
            return str(s.get("title") or "")[:160]
    return ""


def _scene_for(chunk: str, idx: int, count: int, *, lang: str, prev: str, sources) -> dict:
    nums = _numbers(chunk)
    text = _clean(chunk, 140)
    if nums and len(_words(chunk)) <= 18 and prev != "stat":
        num, pct = nums[0]
        sc = {"type": "stat", "value": num[:24], "label": _clean(chunk, 160)}
        if pct:
            sc["suffix"] = "%"
        src = _source_for(num, sources)
        if src:
            sc["source"] = src
        return sc
    if _is_sequence(chunk, lang):
        st = _steps(chunk, lang)
        if st:
            return {"type": "steps", "steps": st}
    items = _items(chunk)
    if items and prev != "list":
        return {"type": "list", "items": items, "numbered": False}
    sc = {"type": "kinetic_title", "text": text}
    if idx == 0 and count > 1:
        sc["camera"] = {"move": "push-in", "amount": 0.35}
    return sc


def _allocate(chunk_list: list, total: float) -> list:
    """The seconds of each scene, in proportion to how long its words take to say; at least MIN_SCENE_S each (fewer scenes when the shot is too short)."""
    w = [max(1, sum(len(x) + 1 for x in _words(c))) for c in chunk_list]
    s = float(sum(w))
    return [max(MIN_SCENE_S, total * x / s) for x in w]


def _merge_to_fit(chunk_list: list, total: float) -> list:
    """Fewer scenes when the shot cannot give every chunk MIN_SCENE_S seconds."""
    cl = list(chunk_list)
    while len(cl) > 1 and total / len(cl) < MIN_SCENE_S + 0.25:
        i = min(range(len(cl) - 1), key=lambda k: len(cl[k]) + len(cl[k + 1]))
        cl[i:i + 2] = [cl[i] + " " + cl[i + 1]]
    return cl


def make_plan(narration: str, duration: float, *, lang: str = "fa", style: str = "", theme: str = "", size: str = "vertical", series: dict | None = None,
              platform: str = "", sources=None, fps: int = 30, kit: dict | None = None, captions: bool = False, allowed_sources=None) -> dict:
    """A validated plan whose total length is `duration` seconds (the shot's real length) and whose texts are pieces of `narration`.
    An empty narration gives one `kinetic_title` of the episode title (or the series name); nothing at all => SpecError."""
    kit = kit or timeline.kit_of({"style": style, "theme": theme})
    cl = chunks(narration)
    duration = max(1.0, float(duration or 4.0))
    ser = series or {}
    if not cl:
        text = _clean(str(ser.get("episode_title") or ser.get("title") or ""), 140)
        if not text:
            raise specs.SpecError("برای ساختن طرح، گفتار یا عنوانی لازم است.", "A narration or a title is needed to make a plan.")
        raw = [{"type": "kinetic_title", "text": text, "duration": duration}]
        return specs.normalize_spec({"style": style, "theme": theme, "size": size, "lang": lang, "fps": fps, "series": ser, "platform": platform, "scenes": raw},
                                    max_total=max(duration + 1, specs.MAX_TOTAL_S), allowed_sources=allowed_sources, kit=kit)
    cl = _merge_to_fit(cl, duration)[: specs.MAX_SCENES]
    scenes, prev = [], ""
    for i, c in enumerate(cl):
        sc = _scene_for(c, i, len(cl), lang=lang, prev=prev, sources=sources)
        sc["narration"] = c[: specs.MAX_NARRATION]
        scenes.append(sc)
        prev = sc["type"]
    # the plan's total = the shot's duration: the transitions overlap, so the scenes are a little longer than the shot; iterate the factor
    secs = _allocate(cl, duration)
    spec = {"style": style, "theme": theme, "size": size, "lang": lang, "fps": fps, "series": ser, "platform": platform}
    if captions:
        spec["captions"] = {"on": True, "position": "lower"}
    for _ in range(4):
        for sc, d in zip(scenes, secs):
            sc["duration"] = round(max(specs.MIN_SCENE_S - 1.0, d), 2)
        tot = timeline.total_seconds({**spec, "scenes": scenes}, kit)
        if abs(tot - duration) < 0.06:
            break
        secs = [max(MIN_SCENE_S, d * duration / max(0.1, tot)) for d in secs]
    # word timings: each scene owns the span of the narration audio that its words take (the same proportion as the allocation)
    tl = timeline.compute({**spec, "scenes": scenes}, kit=kit)
    fps_ = tl["fps"]
    weights = [max(1, sum(len(x) + 1 for x in _words(c))) for c in cl]
    tot_w = float(sum(weights))
    spoken = 0.0
    for sc, c, w, fr, st in zip(scenes, cl, weights, tl["frames"], tl["starts"]):
        span = duration * w / tot_w
        local = spoken - st / fps_                                  # when this piece starts being said, counted from the start of ITS scene
        sc["cues"] = estimate_cues(c, min(span, fr / fps_), start=max(0.05, local + 0.05))
        spoken += span
    return specs.normalize_spec({**spec, "scenes": scenes}, max_total=max(duration + 2, specs.MAX_TOTAL_S), allowed_sources=allowed_sources, kit=kit)


__all__ = ["make_plan", "chunks", "estimate_cues", "motionlib"]
