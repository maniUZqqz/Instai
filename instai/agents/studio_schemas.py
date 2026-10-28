"""JSON schemas for the studio (development + pre-production) agent roles."""
from __future__ import annotations

from .schemas import _arr, _s

NODE_KINDS = ["divergence", "direct", "ripple", "character", "world", "theme"]
DESIGN_KINDS = ["character", "expression", "background", "prop", "colour_script"]

IDEA = {
    "type": "object", "required": ["title", "logline"],
    "properties": {
        "title": _s(1, maxLength=160),
        "logline": _s(),
        "why_it_works": {"type": "string"},
        "details": {"type": "object"},
        "tags": _arr({"type": "string"}, maxItems=8),
    },
}
IDEAS = {
    "type": "object", "required": ["ideas"],
    "properties": {"ideas": _arr(IDEA, minItems=1, maxItems=14)},
}

CANON = {
    "type": "object", "required": ["summary", "characters", "key_events"],
    "properties": {
        "summary": _s(),
        "characters": _arr({"type": "object", "required": ["name", "role"],
                            "properties": {"name": _s(), "role": _s(), "abilities": {"type": "string"}, "arc": {"type": "string"},
                                           "relationships": {"type": "string"}, "source_ids": _arr({"type": "integer"})}}, minItems=1, maxItems=30),
        "arcs": _arr({"type": "object", "required": ["title", "summary"],
                      "properties": {"title": _s(), "summary": _s(), "source_ids": _arr({"type": "integer"})}}, maxItems=20),
        "key_events": _arr({"type": "object", "required": ["event"],
                            "properties": {"when": {"type": "string"}, "event": _s(), "importance": {"type": "string"},
                                           "source_ids": _arr({"type": "integer"})}}, minItems=1, maxItems=40),
        "world_rules": _arr({"type": "object", "required": ["rule"],
                             "properties": {"rule": _s(), "source_ids": _arr({"type": "integer"})}}, maxItems=20),
        "themes": _arr({"type": "string"}, maxItems=10),
        "caveats": _arr({"type": "string"}, maxItems=8),
    },
}

MAP = {
    "type": "object", "required": ["nodes"],
    "properties": {"nodes": _arr({"type": "object", "required": ["id", "title"],
                                  "properties": {"id": _s(), "title": _s(), "description": {"type": "string"},
                                                 "kind": {"type": "string", "enum": NODE_KINDS, "default": "ripple"},
                                                 "parent": {"type": "string"}, "episode_hint": {"type": "integer", "minimum": 0, "maximum": 60}}},
                                 minItems=2, maxItems=40)},
}

TIMELINE = {
    "type": "object", "required": ["rows"],
    "properties": {"rows": _arr({"type": "object", "required": ["when", "alternate"],
                                 "properties": {"when": _s(), "canon": {"type": "string"}, "alternate": _s(), "note": {"type": "string"}}},
                                minItems=2, maxItems=40),
                   "summary": {"type": "string"}},
}

CHARACTER_BIBLE = {
    "type": "object", "required": ["characters"],
    "properties": {"characters": _arr({"type": "object", "required": ["name", "role"],
                                       "properties": {"name": _s(), "role": _s(), "appearance": {"type": "string"}, "personality": {"type": "string"},
                                                      "motivations": {"type": "string"}, "abilities": {"type": "string"},
                                                      "catchphrases": _arr({"type": "string"}, maxItems=6),
                                                      "visual_hooks": _arr({"type": "string"}, maxItems=6), "voice_notes": {"type": "string"},
                                                      "is_original": {"type": "boolean", "default": True}}}, minItems=1, maxItems=8)},
}

BIBLE = {
    "type": "object", "required": ["title", "logline", "premise", "characters", "arcs"],
    "properties": {
        "title": _s(), "logline": _s(), "premise": _s(),
        "world_rules": _arr({"type": "string"}, maxItems=15),
        "characters": _arr({"type": "object", "required": ["name", "role"],
                            "properties": {"name": _s(), "role": _s(), "appearance": {"type": "string"}, "personality": {"type": "string"},
                                           "motivations": {"type": "string"}, "abilities": {"type": "string"},
                                           "is_original": {"type": "boolean", "default": True}}}, minItems=1, maxItems=12),
        "tone": {"type": "string"},
        "themes": _arr({"type": "string"}, maxItems=8),
        "arcs": _arr({"type": "object", "required": ["title", "summary"],
                      "properties": {"title": _s(), "summary": _s(), "goal": {"type": "string"}, "cliffhanger": {"type": "string"}}}, minItems=1, maxItems=12),
        "branch_point": {"type": "string"}, "alternative_timeline": {"type": "string"},
        "episode_count": {"type": "integer", "minimum": 1, "maximum": 60, "default": 5},
        "episode_length_sec": {"type": "integer", "minimum": 10, "maximum": 180, "default": 45},
        "visual_notes": {"type": "string"},
        "content_rules": _arr({"type": "string"}, maxItems=12),
    },
}

DESIGN = {
    "type": "object", "required": ["sheets"],
    "properties": {"sheets": _arr({"type": "object", "required": ["kind", "subject", "prompt"],
                                   "properties": {"kind": {"type": "string", "enum": DESIGN_KINDS}, "subject": _s(), "prompt": _s(),
                                                  "negative": {"type": "string"}, "notes": {"type": "string"},
                                                  "palette": _arr({"type": "string"}, maxItems=8)}}, minItems=1, maxItems=40)},
}

CASTING = {
    "type": "object", "required": ["casting"],
    "properties": {"casting": _arr({"type": "object", "required": ["character", "voice_id"],
                                    "properties": {"character": _s(), "voice_id": _s(), "reason": {"type": "string"}}}, minItems=1, maxItems=20)},
}

TRANSLATION = {
    "type": "object", "required": ["blocks"],
    "properties": {"title": {"type": "string"}, "hook": {"type": "string"}, "cta": {"type": "string"},
                   "blocks": _arr({"type": "object", "required": ["text"],
                                   "properties": {"id": {"type": "integer"}, "speaker": {"type": "string"}, "text": _s(), "emotion": {"type": "string"}}},
                                  minItems=1, maxItems=80)},
}
SHOT_LINES = {
    "type": "object", "required": ["lines"],
    "properties": {"lines": _arr({"type": "object", "required": ["id", "text"], "properties": {"id": _s(), "text": {"type": "string"}}}, minItems=1, maxItems=200)},
}

SCHEMAS = {"ideas": IDEAS, "idea_refine": IDEA, "idea_merge": IDEA, "canon": CANON, "consequence_map": MAP, "timeline": TIMELINE,
           "character_bible": CHARACTER_BIBLE, "bible": BIBLE, "design": DESIGN, "casting": CASTING, "translate": TRANSLATION,
           "translate_shots": SHOT_LINES}
