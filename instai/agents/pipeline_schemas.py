"""JSON schemas of the animation-studio pipeline roles (ladder stages, character identity, choice stories, mini-series channels)."""
from __future__ import annotations

from .schemas import _arr, _s

STR = {"type": "string"}
NUM = {"type": "number"}

IDENTITY_ANCHOR = {
    "type": "object", "required": ["anchor"],
    "properties": {"anchor": _s(1, maxLength=700), "avoid": {"type": "string"}, "visual_hooks": _arr(STR, maxItems=6),
                   "palette": _arr({"type": "object", "required": ["hex"], "properties": {"role": STR, "hex": _s(4, maxLength=9)}}, maxItems=8)},
}

LOGLINE = {
    "type": "object", "required": ["logline"],
    "properties": {"logline": _s(1, maxLength=400), "hook": STR, "stakes": STR, "alternatives": _arr(_s(1, maxLength=400), maxItems=5)},
}

TREATMENT = {
    "type": "object", "required": ["synopsis", "acts"],
    "properties": {"synopsis": _arr(_s(), minItems=1, maxItems=8),
                   "acts": _arr({"type": "object", "required": ["name", "summary"], "properties": {"name": _s(), "summary": _s()}}, minItems=1, maxItems=6),
                   "tone": STR, "themes": _arr(STR, maxItems=8)},
}

BEAT_SHEET = {
    "type": "object", "required": ["beats"],
    "properties": {"beats": _arr({"type": "object", "required": ["name", "summary"],
                                 "properties": {"name": _s(), "summary": _s(), "seconds": NUM, "purpose": STR}}, minItems=3, maxItems=16)},
}

DIALOGUE = {
    "type": "object", "required": ["lines"],
    "properties": {"lines": _arr({"type": "object", "required": ["speaker", "text"],
                                  "properties": {"speaker": _s(), "text": _s(), "emotion": STR, "subtext": STR, "pause_after": NUM}}, minItems=2, maxItems=80)},
}

SHOT_LIST = {
    "type": "object", "required": ["shots"],
    "properties": {"shots": _arr({"type": "object", "required": ["action"],
                                 "properties": {"scene": {"type": "integer", "minimum": 1, "maximum": 60}, "size": STR, "angle": STR, "movement": STR,
                                                "characters": _arr(STR, maxItems=6), "action": _s(), "seconds": NUM, "transition": STR, "notes": STR}},
                                minItems=2, maxItems=80)},
}

LAYOUT = {
    "type": "object", "required": ["layouts"],
    "properties": {"layouts": _arr({"type": "object", "required": ["shot"],
                                    "properties": {"shot": {"type": "integer", "minimum": 1, "maximum": 200}, "background": STR, "staging": STR, "camera": STR,
                                                   "lighting": STR, "props": _arr(STR, maxItems=8)}}, minItems=1, maxItems=80)},
}

SOUND_DESIGN = {
    "type": "object", "required": ["cues"],
    "properties": {"cues": _arr({"type": "object", "required": ["kind", "description"],
                                 "properties": {"kind": {"type": "string", "enum": ["ambience", "foley", "sfx", "music", "silence"]}, "shot": {"type": "integer", "minimum": 0, "maximum": 200},
                                                "start_sec": NUM, "end_sec": NUM, "description": _s(), "prompt": STR, "gain_db": NUM, "duck": {"type": "boolean"}}},
                                minItems=1, maxItems=60),
                   "mix_notes": STR, "loudness_target": NUM},
}

GRADE = {
    "type": "object", "required": ["scenes"],
    "properties": {"scenes": _arr({"type": "object", "required": ["scene", "preset"],
                                   "properties": {"scene": {"type": "integer", "minimum": 1, "maximum": 60}, "preset": STR, "mood": STR,
                                                  "palette": _arr(STR, maxItems=6), "notes": STR}}, minItems=1, maxItems=30),
                   "global_notes": STR},
}

CHOICE_PLAN = {
    "type": "object", "required": ["posts"],
    "properties": {"title": STR, "posts": _arr({"type": "object", "required": ["id", "title", "text"],
                                                "properties": {"id": _s(), "title": _s(), "text": _s(), "kind": STR, "location": STR, "characters": _arr(STR, maxItems=4),
                                                               "pose": STR, "expression": STR, "ending": STR,
                                                               "choices": _arr({"type": "object", "required": ["label", "to"],
                                                                                "properties": {"label": _s(), "to": _s()}}, maxItems=4)}}, minItems=4, maxItems=60)},
}

CHOICE_POSTS = {
    "type": "object", "required": ["posts"],
    "properties": {"posts": _arr({"type": "object", "required": ["id", "caption"],
                                 "properties": {"id": _s(), "caption": _s(), "hashtags": _arr(STR, maxItems=12), "alt": STR}}, minItems=1, maxItems=60)},
}

SEASON_PLAN = {
    "type": "object", "required": ["episodes"],
    "properties": {"season_title": STR, "season_arc": STR,
                   "episodes": _arr({"type": "object", "required": ["number", "title", "hook", "cliffhanger"],
                                     "properties": {"number": {"type": "integer", "minimum": 1, "maximum": 60}, "title": _s(), "hook": _s(), "logline": STR,
                                                    "escalation": STR, "twist": STR, "cliffhanger": _s(), "payoff_of_previous": STR, "characters": _arr(STR, maxItems=6),
                                                    "location": STR, "runtime_sec": {"type": "integer", "minimum": 8, "maximum": 180}, "opens": _arr(STR, maxItems=4),
                                                    "closes": _arr(STR, maxItems=4)}}, minItems=2, maxItems=60)},
}
