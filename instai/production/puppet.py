"""Puppet-2D shots in the episode pipeline: which rig plays which character, the motion plan of a shot, lip-sync cues and the
scene description handed to the renderer (instai.render.puppet). Default technique for recurring characters and presenters."""
from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.render import assemble as asm
from instai.render.puppet import demo, lipsync, motions, renderer

# words in a shot description that choose a gesture or a base motion (English + Persian); first match wins per motion
GESTURES = {
    "wave": ("wave", "waves", "waving", "hello", "greets", "سلام", "دست تکان"),
    "point": ("point", "points", "pointing", "اشاره"),
    "react": ("surprised", "shocked", "gasp", "startled", "شگفت", "متعجب", "ترس"),
    "jump": ("jump", "jumps", "leaps", "می‌پرد", "میپرد", "پرش"),
    "nod": ("nod", "nods", "agrees", "تأیید", "سر تکان"),
    "shake": ("shakes head", "disagree", "refuses", "نه گفت", "رد می"),
}
BASE_WORDS = {"walk": ("walk", "walks", "walking", "strolls", "راه می", "راه‌رفتن", "قدم"), "sit": ("sit", "sits", "sitting", "seated", "می‌نشیند", "نشسته")}


def rig_for_shot(shot, ep):
    """The approved rig of the speaking character, else of any character of the page (latest approved wins), else the newest draft."""
    from instai.production.models import CharacterRig

    page = ep.series.page
    chars = list(page.characters.all())
    speaker = next((c for c in chars if shot.speaker and c.name == shot.speaker), None)
    for pool in ([speaker] if speaker else []) + chars:
        rig = CharacterRig.objects.filter(character=pool, approved=True).order_by("-version").first()
        if rig:
            return rig, False
    for pool in ([speaker] if speaker else []) + chars:
        rig = CharacterRig.objects.filter(character=pool).order_by("-version").first()
        if rig:
            return rig, True
    return None, False


def plan_motion(shot, duration: float, speaking: tuple[float, float] | None) -> list[dict]:
    text = f"{shot.description} {shot.image_prompt}".lower()
    base = next((m for m, words in BASE_WORDS.items() if any(w in text for w in words)), "idle")
    gestures: list[tuple[str, float]] = []
    t = 0.3
    for motion, words in GESTURES.items():
        if any(w in text for w in words):
            gestures.append((motion, min(max(0.1, duration - motions.MOTIONS[motion]["duration"]), t)))
            t += 1.2
    speak = [speaking] if speaking else []
    return motions.talk_timeline(duration, speak, base=base, gestures=gestures)


def cues_for(narration: Asset | None, language: str, text: str, engine: str = "auto") -> tuple[list, dict]:
    """Mouth cues for the narration audio (cached by audio hash): ([(start, end, shape)], {engine, note})."""
    if narration is None:
        return [], {"engine": "none", "note": "silent shot"}
    path = asset_storage.storage.path_for(narration.path)
    cache = Path(settings.MEDIA_ROOT) / "_cache" / "lipsync"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / (lipsync.cache_key(path, language, engine) + ".json")
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return [tuple(c) for c in d["cues"]], {"engine": d["engine"], "note": d.get("note", ""), "cached": True}
    r = lipsync.visemes(path, language=language, text=text, engine=engine)
    f.write_text(json.dumps({"cues": r["cues"], "engine": r["engine"], "note": r["note"]}), encoding="utf-8")
    return r["cues"], {"engine": r["engine"], "note": r["note"]}


def build_scene(shot, ep, *, narration: Asset | None, keyframe: Asset | None, duration: float, language: str, demo_mode: bool = False) -> tuple[dict | None, list[str]]:
    """The puppet part of a ShotSpec (everything except size/fps/duration, which the render options add). None = no rig, use Ken Burns."""
    notes: list[str] = []
    rig, draft = rig_for_shot(shot, ep)
    if rig is None:
        return None, [f"shot {shot.scene.index}.{shot.index}: no character rig yet (Characters > Rigs), Ken Burns used instead of the puppet"]
    if draft:
        notes.append(f"shot {shot.scene.index}.{shot.index}: the rig is not approved yet (draft rig used)")
    root = Path(settings.MEDIA_ROOT)
    from instai.render.puppet.rig import Rig

    Rig.from_spec(rig.spec, root)  # validates the spec and the image files before any frame is drawn
    spec = json.loads(json.dumps(rig.spec))
    for p in spec["parts"].values():
        if p.get("image") and not Path(p["image"]).is_absolute():
            p["image"] = str(root / p["image"])
    cues, info = cues_for(narration, language, shot.narration)
    if info["engine"] == "amplitude" and info.get("note"):
        notes.append(f"shot {shot.scene.index}.{shot.index}: {info['note']}")
    layers = [{"image": str(asset_storage.storage.path_for(a.path)), "parallax": float(a.provenance.get("parallax", 0.5)),
               "front": bool(a.provenance.get("front"))} for a in Asset.objects.filter(shot=shot, role="layer", is_current=True).order_by("id")]
    if keyframe is not None and not layers:
        layers = [{"image": str(asset_storage.storage.path_for(keyframe.path)), "parallax": 0.25}]
    elif keyframe is not None:
        layers.insert(0, {"image": str(asset_storage.storage.path_for(keyframe.path)), "parallax": 0.12})
    if not layers and demo_mode:
        layers = demo.make_background(root / "_cache" / "demo-bg", 1080, 1920)
    speaking = (asm.LEAD_IN, asm.LEAD_IN + (narration.duration_sec or 0.0)) if narration is not None and narration.duration_sec else None
    mv = shot.camera.get("move", "static") if isinstance(shot.camera, dict) else "static"
    inten = float(shot.camera.get("intensity", 0.4)) if isinstance(shot.camera, dict) else 0.4
    actor = {"id": rig.character.name, "rig": spec, "x": 0.5, "y": 0.94, "height": 0.5, "seed": int(shot.seed or shot.pk or 1),
             "timeline": plan_motion(shot, duration, speaking), "mouth": [list(c) for c in cues]}
    return {"background": {"layers": layers}, "actors": [actor], "camera": renderer.camera_from_move(mv, inten, duration),
            "color": "#23232b", "lipsync": info["engine"], "rig": rig.pk}, notes


def spec_hash_parts(puppet: dict | None) -> str:
    if not puppet:
        return ""
    return re.sub(r"\s+", "", json.dumps(puppet, sort_keys=True, ensure_ascii=False, default=str))
