"""The prompt kit for the text model: a compact motion-design guide + the tokens of the chosen style + only the components that fit the request + a few examples
+ the JSON schema for the constrained output (Ollama format=schema).

SOURCE: ported from NMarketing:backend/apps/motion/promptkit.py @ motion v2, adapted for InstAI: the request is the NARRATION of one shot of an episode (not a shop
idea), the style tokens come from the style kit (instai/remotion/kit.py), the examples are about episodes, series and explainers, the language of the screen
text follows the page (fa / en), and the numbers rule is InstAI's: nothing invented, a number is an example unless a verified source is named.

The principle: the model draws no video; it writes a SCENE PLAN (JSON) that puts ready-made components (components.py) side by side and sets their numbers.
The size of the prompt is bounded (MAX_PROMPT_CHARS); a test measures it with a very long narration too.
"""
from __future__ import annotations

import json
import re

from . import colors, components, motionlib

MAX_PROMPT_CHARS = 9500
MAX_COMPONENTS = 8
MAX_IDEA_CHARS = 1800
CORE = ("kinetic_title", "list", "stat")      # always offered: a headline, a list and a number fit nearly every explainer shot

GUIDE = """You are a motion-graphics DIRECTOR for one SHOT of an animated episode. You do not draw video: you write a SCENE PLAN (JSON) that assembles READY-MADE components and sets their numbers.
Rules of craft:
- The shot lasts as long as its narration. One idea per scene. Each scene 2-6 s; a shot has 1-4 scenes.
- Reading time: Persian needs >= 0.32 s per word + 0.7 s entrance. Titles <= 7 words, list items <= 6 words, max 5 items per list.
- Persian typography: text is RTL; animate WORDS never letters; Persian digits; no ALL CAPS; no more than 2 title lines.
- The on-screen text is a piece of the narration (same words) - never add facts, numbers, names, prices or statistics that the narration does not contain.
- A number is only an EXAMPLE unless a verified source is named: never write a "source" yourself; leave it out.
- Prefer data components only when the narration gives numbers (bar_chart, line_chart, donut, counter, stat); prefer list / steps / checklist for enumerations and processes.
- Vary components: never repeat the same component 3 times in a row. Use a transition from the pack (wipe, push, zoom, ink, glitch, iris) sparingly, or leave it to the style.
- "narration" = the words a voice says over the scene (copy the narration piece); "emphasis" = 1-3 words drawn in the accent colour.
- Keep safe zones: nothing important in the platform's UI bars (Shorts: top 10 %, bottom 20 %, right 12 %)."""

EASES_DOC = "ease: " + "|".join(motionlib.EASES) + " ; spring: " + "|".join(motionlib.SPRINGS) + " ; camera.move: " + "|".join(m for m in motionlib.CAMERA_MOVES if m != "none")
TRANS_DOC = "transition (into the NEXT scene): cut|fade|" + "|".join(motionlib.TRANSITION_PACK)

# ───────────────────────────────────────────── few-shot examples (no invented claims)
EXAMPLES = [
    {"name": "explainer", "uses": ("kinetic_title", "list", "stat"), "plan": {
        "title": "Why the sky is blue", "scenes": [
            {"type": "kinetic_title", "duration": 3.5, "text": "Sunlight is every colour at once", "emphasis": ["every colour"], "narration": "Sunlight is every colour at once."},
            {"type": "list", "duration": 6, "title": "What the air does", "items": ["Blue light scatters most", "Red light travels straight", "Our eyes see the scattered blue"], "transition": "wipe",
             "narration": "Blue light scatters most, red light travels straight, and our eyes see the scattered blue."}]}},
    {"name": "whatif", "uses": ("title", "before_after", "quote"), "plan": {
        "title": "What if the Moon vanished", "scenes": [
            {"type": "title", "duration": 3, "title": "What if the Moon vanished?", "hook": "The tides would change first"},
            {"type": "before_after", "duration": 6, "title": "Tides", "before": "Two tides a day", "after": "Only the weak solar tide", "before_label": "Now", "after_label": "Without the Moon", "transition": "iris"}]}},
    {"name": "process", "uses": ("steps", "checklist"), "plan": {
        "title": "The scientific method", "scenes": [
            {"type": "steps", "duration": 7, "title": "Four steps", "steps": [{"title": "Ask"}, {"title": "Guess"}, {"title": "Test"}, {"title": "Conclude"}], "ease": "out-soft"},
            {"type": "checklist", "duration": 5, "title": "Recap", "items": ["A clear question", "A test that can fail", "An honest result"], "transition": "push"}]}},
]


def style_tokens(kit: dict) -> str:
    if not kit:
        return ""
    p = colors.palette_from_kit(kit)
    pers = motionlib.personality(kit)
    return (f"STYLE {kit.get('key', '')} «{kit.get('name', '')}» (animation {kit.get('animation', '')}, family {kit.get('family', '')}): palette bg {p['bg']} ink {p['ink']} "
            f"accent {p['accent']}/{p['accent2']}/{p['accent3']}; enter {pers['enter']}, spring {pers['spring']}, transition {pers['trans']['kind']} ({pers['trans']['frames']}f). {kit.get('mood', '')[:140]}")


def _tokens(text: str) -> set:
    t = (text or "").lower().replace("‌", " ")
    return set(w for w in re.findall(r"[\w؀-ۿ]{2,}", t))


def pick_components(idea: str, *, limit: int = MAX_COMPONENTS, must=("kinetic_title",)) -> list:
    """The components that fit the request (word overlap with each component's `use` keywords); always one headline; the rest for variety."""
    words = _tokens(idea)
    has_numbers = bool(re.search(r"[\d۰-۹]", idea or ""))
    scored = []
    for cid, c in components.COMPONENTS.items():
        use = _tokens(c["use"])
        score = len(words & use) * 2
        score += sum(1 for w in words if len(w) > 3 and any(u.startswith(w[:4]) for u in use if len(u) > 3)) * 0.5      # a prefix / root (e.g. نمودار)
        if cid in ("bar_chart", "line_chart", "donut", "counter", "stat") and has_numbers:
            score += 1.5
        scored.append((score, cid))
    scored.sort(key=lambda x: (-x[0], list(components.COMPONENTS).index(x[1])))
    out = list(must)
    core = [c for c in CORE if c not in out]
    for score, cid in scored:                                   # first the pieces the request asks for (keeping room for the core)
        if score > 0 and cid not in out and len(out) < limit - len(core):
            out.append(cid)
    for cid in core:                                            # then the general-purpose pieces every explainer needs
        if len(out) < limit:
            out.append(cid)
    for score, cid in scored:                                   # then whatever else fits, up to 6 pieces for variety
        if len(out) >= min(limit, 6):
            break
        if cid not in out:
            out.append(cid)
    return out[:limit]


def catalogue(ids: list) -> str:
    lines = []
    for cid in ids:
        c = components.COMPONENTS[cid]
        fields = "; ".join(f"{n}:{components.field_doc(f)}" for n, f in c["fields"].items() if n not in ("source", "example"))
        lines.append(f"- {cid} ({c['dur'][0]}-{c['dur'][2]}s, typ {c['dur'][1]}s): {c['about']}. fields: {fields}{' [overlay ok]' if c['overlay'] else ''}")
    return "\n".join(lines)


def _examples_for(ids: list, n: int = 2) -> list:
    ranked = sorted(EXAMPLES, key=lambda e: -len(set(e["uses"]) & set(ids)))
    out = []
    for e in ranked[:n]:
        ok = [s for s in e["plan"]["scenes"] if s["type"] in ids]
        out.append(e if len(ok) == len(e["plan"]["scenes"]) else {**e, "plan": {**e["plan"], "scenes": ok or e["plan"]["scenes"][:1]}})
    return out


# ───────────────────────────────────────────── the JSON schema (constrained output)

def _prop(spec: dict) -> dict:
    k = spec["kind"]
    if k == "str":
        return {"type": "string"}
    if k == "num":
        return {"type": "number"}
    if k == "int":
        return {"type": "integer"}
    if k == "bool":
        return {"type": "boolean"}
    if k == "enum":
        return {"type": "string", "enum": list(spec["choices"])} if len(spec["choices"]) <= 16 else {"type": "string"}
    if k == "ref":
        return {"type": "string"}
    if k == "strs":
        return {"type": "array", "items": {"type": "string"}, "maxItems": spec["max_items"]}
    if k == "objs":
        return {"type": "array", "maxItems": spec["max_items"], "items": {"type": "object", "properties": {n: _prop(f) for n, f in spec["fields"].items()}}}
    return {}


def json_schema(ids: list, *, max_scenes: int = 5) -> dict:
    """One schema for the model: the union of the fields of the chosen components (a field with two different types is left unconstrained)."""
    props: dict = {}
    for cid in ids:
        for n, f in components.COMPONENTS[cid]["fields"].items():
            if f["kind"] == "ref" or n in ("source", "example"):
                continue                         # a picture is given by the pipeline; a source is never written by the model
            p = _prop(f)
            if n in props and props[n] != p:
                props[n] = {}
            else:
                props[n] = p
    props.pop("size", None)
    scene = {"type": "object", "properties": {
        "type": {"type": "string", "enum": list(ids)}, "duration": {"type": "number"}, "narration": {"type": "string"},
        "emphasis": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "transition": {"type": "string", "enum": ["cut", "fade", *motionlib.TRANSITION_PACK]},
        "ease": {"type": "string", "enum": list(motionlib.EASES)},
        "camera": {"type": "object", "properties": {"move": {"type": "string", "enum": [m for m in motionlib.CAMERA_MOVES if m != "none"]}, "amount": {"type": "number"}}},
        **props}, "required": ["type", "duration"]}
    return {"type": "object", "properties": {"title": {"type": "string"}, "scenes": {"type": "array", "minItems": 1, "maxItems": max_scenes, "items": scene}}, "required": ["scenes"]}


def patch_max() -> int:
    from . import patch

    return patch.MAX_OPS


def patch_schema() -> dict:
    return {"type": "object", "properties": {
        "say": {"type": "string"},
        "ops": {"type": "array", "maxItems": patch_max(), "items": {"type": "object", "properties": {
            "op": {"type": "string", "enum": ["set", "remove", "scale", "shift", "add_scene", "remove_scene", "move_scene", "duplicate_scene", "split_scene"]},
            "path": {"type": "string"}, "value": {}, "factor": {"type": "number"}, "by": {"type": "number"}, "min": {"type": "number"}, "max": {"type": "number"},
            "index": {"type": "integer"}, "from": {"type": "integer"}, "to": {"type": "integer"}, "at": {"type": "integer"}, "scene": {"type": "object"}}, "required": ["op"]}}},
        "required": ["ops"]}


# ───────────────────────────────────────────── the prompt that makes a plan

def build_prompt(narration: str, *, kit: dict, size: str = "vertical", lang: str = "fa", seconds: float = 6.0, series: dict | None = None, platform: str = "",
                 ids: list | None = None) -> dict:
    """=> {system, user, schema, ids, chars}. ids = the components allowed (default: pick_components)."""
    narration = (narration or "").strip()[:MAX_IDEA_CHARS]
    ids = [i for i in (ids or pick_components(narration)) if i in components.COMPONENTS][:MAX_COMPONENTS]
    ex = _examples_for(ids)
    plat = platform or motionlib.DEFAULT_PLATFORM.get(size, "")
    safe = motionlib.platform_safe(plat)
    ser = series or {}
    system = "\n".join([
        GUIDE,
        f"Language of all on-screen text: {'Persian (Farsi)' if lang == 'fa' else 'English'}. Size {size}; platform {plat or 'none'}"
        + (f" (safe margins top {safe['top']:.0%}, bottom {safe['bottom']:.0%})" if plat else "") + f". The shot is {seconds:.0f} seconds long.",
        style_tokens(kit),
        "COMPONENTS you may use (type = id; set only the listed fields; every text field has a maximum length):", catalogue(ids),
        EASES_DOC, TRANS_DOC,
        "Reply with ONE JSON object {\"title\": str, \"scenes\": [...]} and nothing else.",
        "EXAMPLES of valid replies:", *[json.dumps(e["plan"], ensure_ascii=False, separators=(",", ":")) for e in ex],
    ])
    who = ", ".join(x for x in (f"series «{ser.get('title')}»" if ser.get("title") else "", f"episode {ser.get('episode')}" if ser.get("episode") else "",
                                f"title «{ser.get('episode_title')}»" if ser.get("episode_title") else "",
                                ("characters " + ", ".join(ser.get("characters") or [])) if ser.get("characters") else "") if x)
    user = (f"Episode: {who or '-'}.\nNarration of this shot (the on-screen text must come from it):\n{narration}")
    if len(system) + len(user) > MAX_PROMPT_CHARS:           # the bound: the examples and then the last components go first
        ex = ex[:1]
        ids = ids[:6]
        system = system[: system.index("COMPONENTS you may use")] + "COMPONENTS you may use:\n" + catalogue(ids) + "\n" + EASES_DOC + "\n" + TRANS_DOC + \
            "\nReply with ONE JSON object and nothing else.\nEXAMPLE:\n" + json.dumps(ex[0]["plan"], ensure_ascii=False, separators=(",", ":"))
    return {"system": system, "user": user, "schema": json_schema(ids), "ids": ids, "chars": len(system) + len(user)}


# ───────────────────────────────────────────── the prompt that edits a plan (chat)

PATCH_GUIDE = """You edit a video SCENE PLAN with a JSON PATCH. Change ONLY what the user asked; keep everything else.
Ops: {"op":"set","path":"scenes/1/tokens/font_scale","value":1.2} | {"op":"scale","path":"scenes/1/tokens/font_scale","factor":1.15,"min":0.6,"max":1.6,"default":1}
| {"op":"shift","path":"scenes/2/duration","by":1.5} | {"op":"remove","path":"scenes/1/camera"} | {"op":"add_scene","at":2,"scene":{...}} | {"op":"remove_scene","index":2}
| {"op":"move_scene","from":1,"to":3} | {"op":"duplicate_scene","index":1} | {"op":"split_scene","index":1}.
Paths use / and 0-based scene numbers (the user says "scene 2" = index 1). Scene fields: tokens{accent,text,bg: "#rrggbb", font_scale 0.6-1.6, align}, duration 1-30, enter, exit, ease, spring,
camera{move,amount}, transition, emphasis[], overlays[], narration, plus the component's own fields. Colours: warmer = orange/yellow accent, cooler = teal/blue accent.
"bigger title" = scale tokens/font_scale x1.15-1.25; "longer" = shift duration +1..2. Reply with ONE JSON object {"say": "<one short sentence about what you changed>", "ops": [...]}."""


def compact_plan(spec: dict) -> str:
    keep = {k: v for k, v in spec.items() if k not in ("total_s", "safe", "assets")}
    sc = []
    for i, s in enumerate(keep.get("scenes") or []):
        s = {k: v for k, v in s.items() if k != "cues"}
        sc.append({"i": i, **s})
    keep["scenes"] = sc
    return json.dumps(keep, ensure_ascii=False, separators=(",", ":"))[:6000]


def build_patch_prompt(spec: dict, request: str) -> dict:
    user = f"PLAN:\n{compact_plan(spec)}\n\nREQUEST: {(request or '').strip()[:500]}"
    return {"system": PATCH_GUIDE, "user": user, "schema": patch_schema(), "chars": len(PATCH_GUIDE) + len(user)}
