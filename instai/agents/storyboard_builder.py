"""Deterministic script -> shots builder. Used as the storyboard fallback when the model's storyboard does not cover the
script, and by the fake provider. Plain Python: no model, no GPU."""
from __future__ import annotations

WORDS_PER_SECOND = {"fa": 2.4, "en": 2.6}
FORMAT_TECHNIQUES = {
    "anime_whatif": ["still_kenburns", "parallax_25d", "still_kenburns", "wan_i2v"],
    "recurring_character": ["puppet_2d", "puppet_2d", "still_kenburns"],
    "concept_explainer": ["motion_graphics", "still_kenburns", "motion_graphics", "parallax_25d"],
}
MOVES = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "pan_down"]
CHEAPEST_FIRST = ["motion_graphics", "still_kenburns", "puppet_2d", "parallax_25d", "three_d", "wan_flf", "wan_i2v", "talking_video"]


def words(text: str) -> int:
    return len((text or "").split())


def shots_from_script(script: dict, *, fmt: str, language: str, allowed: list[str] | None = None, style: str = "",
                      characters: list[str] | None = None, per_scene: int = 2) -> dict:
    allowed = allowed or []
    techs = [t for t in FORMAT_TECHNIQUES.get(fmt, ["still_kenburns"]) if not allowed or t in allowed]
    if not techs:
        techs = [t for t in CHEAPEST_FIRST if t in allowed][:1] or ["still_kenburns"]
    wps = WORDS_PER_SECOND.get(language[:2], 2.5)
    fa = language.startswith("fa")
    blocks = script.get("blocks") or []
    scenes = []
    for si in range(0, len(blocks), per_scene):
        grp = blocks[si: si + per_scene]
        shots = []
        for bi, b in enumerate(grp):
            idx = si + bi
            dur = round(max(3.0, min(12.0, words(b["text"]) / wps + 0.8)), 1)
            shots.append({
                "description": (f"نمای {idx + 1}: " if fa else f"Shot {idx + 1}: ") + b["text"][:60],
                "image_prompt": f"{style or 'illustration'}; {b['text'][:90]}; vertical 9:16, clean composition",
                "technique": techs[idx % len(techs)],
                "camera": {"move": MOVES[idx % len(MOVES)], "intensity": 0.5},
                "duration_sec": dur, "narration": b["text"], "speaker": b.get("speaker", ""), "sfx": "",
                "transition": "crossfade" if bi == len(grp) - 1 else "cut",
            })
        scenes.append({"title": (f"صحنه {si // per_scene + 1}" if fa else f"Scene {si // per_scene + 1}"),
                       "summary": grp[0]["text"][:90], "location": "", "characters": (characters or [])[:2], "shots": shots})
    return {"scenes": scenes}
