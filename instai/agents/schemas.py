"""JSON schemas at every agent boundary. Outputs are validated (and repaired / retried) against these."""
from __future__ import annotations

TECHNIQUES = ["still_kenburns", "parallax_25d", "puppet_2d", "motion_graphics", "wan_i2v", "wan_flf", "talking_video", "three_d"]
CAMERA_MOVES = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down", "static"]
STANCES = ["established", "contested", "speculative"]


def _s(min_len: int = 1, **kw) -> dict:
    return {"type": "string", "minLength": min_len, **kw}


def _arr(items: dict, **kw) -> dict:
    return {"type": "array", "items": items, **kw}


STRATEGY = {
    "type": "object",
    "required": ["positioning", "audience_insight", "tone_guidelines", "content_pillars", "series_ideas", "posting_plan", "hashtags"],
    "properties": {
        "positioning": _s(),
        "audience_insight": _s(),
        "tone_guidelines": _s(),
        "content_pillars": _arr({"type": "object", "required": ["title", "description"],
                                 "properties": {"title": _s(), "description": _s()}}, minItems=2, maxItems=6),
        "series_ideas": _arr({"type": "object", "required": ["title", "premise"],
                              "properties": {"title": _s(), "premise": _s(), "branch_point": {"type": "string"},
                                             "episodes": {"type": "integer", "minimum": 1, "maximum": 60}}}, minItems=1, maxItems=4),
        "characters": _arr({"type": "object", "required": ["name", "role"],
                            "properties": {"name": _s(), "role": _s(), "personality": {"type": "string"},
                                           "appearance": {"type": "string"}, "is_original": {"type": "boolean", "default": True}}},
                           maxItems=8),
        "posting_plan": {"type": "object", "required": ["per_week"],
                         "properties": {"per_week": {"type": "integer", "minimum": 1, "maximum": 21},
                                        "best_times": _arr({"type": "string"}),
                                        "episode_length_sec": {"type": "integer", "minimum": 10, "maximum": 180}}},
        "hashtags": _arr({"type": "string"}, maxItems=30),
        "risks": _arr({"type": "string"}, maxItems=8),
    },
}

SERIES_PLAN = {
    "type": "object",
    "required": ["title", "premise", "arcs", "episodes"],
    "properties": {
        "title": _s(),
        "premise": _s(),
        "branch_point": {"type": "string"},
        "alternative_timeline": {"type": "string"},
        "content_rules": _arr({"type": "string"}, maxItems=12),
        "arcs": _arr({"type": "object", "required": ["title", "summary"],
                      "properties": {"title": _s(), "summary": _s(), "goal": {"type": "string"},
                                     "cliffhanger": {"type": "string"}}}, minItems=1, maxItems=12),
        "episodes": _arr({"type": "object", "required": ["number", "title", "logline"],
                          "properties": {"number": {"type": "integer", "minimum": 1}, "arc": {"type": "integer", "minimum": 1},
                                         "title": _s(), "logline": _s(), "goal": {"type": "string"},
                                         "cliffhanger": {"type": "string"},
                                         "duration_sec": {"type": "integer", "minimum": 10, "maximum": 180}}},
                         minItems=1, maxItems=60),
    },
}

SCRIPT = {
    "type": "object",
    "required": ["title", "hook", "blocks"],
    "properties": {
        "title": _s(),
        "hook": _s(),
        "language": {"type": "string"},
        "blocks": _arr({"type": "object", "required": ["speaker", "text"],
                        "properties": {"speaker": _s(), "text": _s(), "emotion": {"type": "string"}}}, minItems=3, maxItems=60),
        "cta": {"type": "string"},
    },
}

STORYBOARD = {
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "scenes": _arr({
            "type": "object", "required": ["title", "shots"],
            "properties": {
                "title": _s(), "summary": {"type": "string"}, "location": {"type": "string"},
                "characters": _arr({"type": "string"}),
                "shots": _arr({
                    "type": "object", "required": ["description", "image_prompt", "technique", "duration_sec"],
                    "properties": {
                        "description": _s(), "image_prompt": _s(),
                        "technique": {"type": "string", "enum": TECHNIQUES},
                        "camera": {"type": "object", "properties": {"move": {"type": "string", "enum": CAMERA_MOVES},
                                                                     "intensity": {"type": "number", "minimum": 0, "maximum": 1}}},
                        "duration_sec": {"type": "number", "minimum": 1, "maximum": 20},
                        "narration": {"type": "string"}, "speaker": {"type": "string"},
                        "sfx": {"type": "string"}, "transition": {"type": "string"},
                    }}, minItems=1, maxItems=12),
            }}, minItems=1, maxItems=20),
    },
}

RESEARCH_QUERIES = {
    "type": "object", "required": ["queries"],
    "properties": {"queries": _arr(_s(), minItems=1, maxItems=8), "key_points": _arr({"type": "string"}, maxItems=12)},
}

RESEARCH_CLAIMS = {
    "type": "object", "required": ["claims"],
    "properties": {
        "claims": _arr({"type": "object", "required": ["claim", "stance"],
                        "properties": {"claim": _s(), "stance": {"type": "string", "enum": STANCES},
                                       "source_ids": _arr({"type": "integer"}), "explanation": {"type": "string"}}},
                       minItems=1, maxItems=30),
        "analogies": _arr({"type": "string"}, maxItems=8),
        "visual_metaphors": _arr({"type": "string"}, maxItems=8),
        "caveats": _arr({"type": "string"}, maxItems=8),
    },
}

CONTINUITY = {
    "type": "object", "required": ["episode_summary"],
    "properties": {
        "episode_summary": _s(),
        "facts": _arr({"type": "string"}, maxItems=20),
        "character_states": _arr({"type": "object", "required": ["character", "state"],
                                  "properties": {"character": _s(), "state": _s()}}, maxItems=12),
        "relationships": _arr({"type": "object", "required": ["a", "b", "status"],
                               "properties": {"a": _s(), "b": _s(), "status": _s()}}, maxItems=12),
        "timeline": _arr({"type": "object", "required": ["event"],
                          "properties": {"when": {"type": "string"}, "event": _s()}}, maxItems=12),
        "open_threads": _arr({"type": "object", "required": ["text"],
                              "properties": {"text": _s(), "status": {"type": "string", "enum": ["open", "resolved"]}}}, maxItems=12),
        "future_goals": _arr({"type": "string"}, maxItems=8),
    },
}

SCHEMAS = {
    "strategy": STRATEGY, "series_plan": SERIES_PLAN, "script": SCRIPT, "storyboard": STORYBOARD,
    "research_queries": RESEARCH_QUERIES, "research_claims": RESEARCH_CLAIMS, "continuity": CONTINUITY,
}
