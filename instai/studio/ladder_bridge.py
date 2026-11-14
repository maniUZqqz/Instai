"""What the ladder reads from the rest of InstAI: live snapshots for the bridge stages (bible, character models, script, storyboard, animatic, design, key art,
animation, compositing), derived stages (narration plan, edit plan, delivery, plus fallbacks) and the context handed to the writing roles."""
from __future__ import annotations

import hashlib
import json

from instai.assets.models import Asset
from instai.story import services as story_services
from instai.story import states

from . import preprod


def h(data) -> str:
    return hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def json_safe(data):
    """A copy of `data` that a JSONField can store: datetimes become ISO strings, anything else unknown becomes its text.

    The live snapshots reuse the dicts of the older screens (design sheets, the animatic asset) and those carry datetimes; one of them
    in a version crashed the whole ladder with a 500 ("Object of type datetime is not JSON serializable")."""
    from django.core.serializers.json import DjangoJSONEncoder

    class _Encoder(DjangoJSONEncoder):
        def default(self, o):
            try:
                return super().default(o)
            except TypeError:
                return str(o)

    return json.loads(json.dumps(data, cls=_Encoder, ensure_ascii=False))


def _state_idx(ep) -> int:
    return states.idx(ep.state) if ep.state in states.ORDER else -1


def _asset_row(a: Asset | None) -> dict | None:
    return {"id": a.pk, "url": a.url, "sha": a.sha256[:12], "approved": a.approved} if a else None


def _current(shot, role: str) -> Asset | None:
    return Asset.objects.filter(shot=shot, role=role, is_current=True).order_by("-version").first()


# ------------------------------------------------------------------ live snapshots of bridged stages

def live_bible(series, ep):
    from . import services
    from .models import SeriesBible

    b = SeriesBible.objects.filter(series=series).first()
    data = services.normalize_bible(b.data) if b else {}
    return {"hash": h([data, b.version if b else 0]), "data": data, "ready": bool(data.get("premise")), "approved_elsewhere": bool(b and b.status == "approved")}


def live_character_models(series, ep):
    from instai.identity.models import CharacterLock

    chars = list(series.page.characters.all())
    locks = {l.character_id: l for l in CharacterLock.objects.filter(character__in=chars)}
    rows = []
    for c in chars:
        l = locks.get(c.pk)
        rows.append({"id": c.pk, "name": c.name, "status": l.status if l else "none", "version": l.version if l else 0, "source": l.source if l else "", "anchor": (l.anchor if l else "")[:300],
                     "palette": l.palette if l else [], "strategy": l.strategy if l else ""})
    data = {"characters": rows}
    return {"hash": h([[r["id"], r["status"], r["version"]] for r in rows]), "data": data, "ready": any(r["status"] != "none" for r in rows),
            "approved_elsewhere": bool(rows) and all(r["status"] == "locked" for r in rows)}


def live_script(series, ep):
    sc = ep.script or {}
    return {"hash": h(sc), "data": sc, "ready": len(sc.get("blocks", [])) >= 3, "approved_elsewhere": _state_idx(ep) >= states.idx(states.STORYBOARDING)}


def live_storyboard(series, ep):
    sb = story_services.storyboard_dict(ep)
    return {"hash": h(sb), "data": sb, "ready": bool(sb), "approved_elsewhere": _state_idx(ep) >= states.idx(states.ASSET_GENERATION)}


def live_animatic(series, ep):
    info = preprod.animatic_info(ep)
    return {"hash": preprod.animatic_hash(ep) if info["status"] != "missing" else "", "data": {"status": info["status"], "asset": info.get("asset")},
            "ready": info["status"] == "fresh", "approved_elsewhere": "animatic" in preprod.approvals(ep)}


def live_design(series, ep):
    rows = [[s.kind, s.subject, s.prompt, s.approved, s.asset_id] for s in ep.design_sheets.all()]
    data = {"sheets": [preprod.sheet_dict(s) for s in ep.design_sheets.select_related("asset")]}
    return {"hash": h(rows), "data": data, "ready": bool(rows), "approved_elsewhere": "design" in preprod.approvals(ep)}


def live_key_art(series, ep):
    from instai.identity import check

    shots = story_services.all_shots(ep)
    rows, sig = [], []
    for s in shots:
        a = _current(s, "keyframe")
        rows.append({"shot": s.pk, "label": f"{s.scene.index}.{s.index}", "technique": s.technique, "asset": _asset_row(a)})
        sig.append(a.sha256 if a else "")
    rep = check.episode_report(ep)
    data = {"shots": rows, "consistency": {"checked": rep["checked"], "ok": rep["ok"], "flagged": rep["flagged"]}}
    return {"hash": h(sig), "data": data, "ready": bool(shots) and all(sig), "approved_elsewhere": False}


def live_animation(series, ep):
    shots = story_services.all_shots(ep)
    rows, sig = [], []
    need = 0
    for s in shots:
        clip = _current(s, "shot_clip")
        needs_clip = s.technique in ("wan_i2v", "wan_flf")
        need += 1 if needs_clip else 0
        rows.append({"shot": s.pk, "label": f"{s.scene.index}.{s.index}", "technique": s.technique, "clip": _asset_row(clip), "needs_clip": needs_clip})
        sig.append([s.technique, clip.sha256 if clip else ""])
    ready = bool(shots) and all((not r["needs_clip"]) or r["clip"] for r in rows)
    return {"hash": h(sig), "data": {"shots": rows, "video_shots": need}, "ready": ready, "approved_elsewhere": False}


def live_compositing(series, ep):
    a = (Asset.objects.filter(episode=ep, shot__isnull=True, role__in=("final", "preview"), is_current=True).order_by("-created_at").first())
    return {"hash": a.sha256 if a else "", "data": {"asset": _asset_row(a), "role": a.role if a else "", "duration_sec": a.duration_sec if a else None}, "ready": a is not None,
            "approved_elsewhere": False}


def live_look(series, ep):
    look = dict(series.look or {})
    return {"hash": h(look), "data": look, "ready": bool(look.get("style_key")), "approved_elsewhere": False}


LIVE = {"bible": live_bible, "character_models": live_character_models, "script": live_script, "storyboard": live_storyboard, "animatic": live_animatic, "design": live_design,
        "key_art": live_key_art, "animation": live_animation, "compositing": live_compositing, "look": live_look}


def live(key: str, series, ep) -> dict | None:
    fn = LIVE.get(key)
    if not fn:
        return None
    out = fn(series, ep)
    out["data"] = json_safe(out["data"])                 # snapshots are stored as versions: nothing in them may be a datetime or a model object
    return out


# ------------------------------------------------------------------ derived stages

def derive_narration(series, ep) -> dict:
    shots = story_services.all_shots(ep)
    cast = {r["name"]: r for r in preprod.casting_rows(ep)}
    lines = []
    for i, s in enumerate(shots, 1):
        if not s.narration.strip():
            continue
        c = cast.get(s.speaker.strip())
        voice = f"{c['engine']}:{c['voice_id']}" if c and c.get("has_voice") else "auto"
        lines.append({"shot": i, "speaker": s.speaker or "narrator", "text": s.narration, "voice": voice, "pace": "normal", "pause_after": 0.3, "pronunciation": ""})
    return {"lines": lines}


def derive_edit(series, ep) -> dict:
    shots = story_services.all_shots(ep)
    cuts = [{"shot": i, "seconds": round(float(s.duration_sec), 2), "transition": s.transition or "cut",
             "note": "" if 0.8 <= float(s.duration_sec) <= 6 else "very short or very long shot"} for i, s in enumerate(shots, 1)]
    secs = [c["seconds"] for c in cuts]
    total = round(sum(secs), 2)
    avg = round(total / len(secs), 2) if secs else 0
    notes = f"shots={len(secs)}; total={total}s; average={avg}s; fastest={min(secs) if secs else 0}s; slowest={max(secs) if secs else 0}s; cuts per 10 s={round(len(secs) * 10 / total, 1) if total else 0}"
    return {"cuts": cuts, "notes": notes}


def derive_delivery(series, ep) -> dict:
    page = series.page
    aspect = page.profile("visual").get("aspect_ratio") or "9:16"
    pub = page.profile("publishing")
    sc = ep.script or {}
    caption = "\n".join(x for x in (sc.get("hook"), sc.get("cta")) if x)
    renditions = [{"name": "master", "aspect": aspect, "use": "main post / reel"}]
    for a, use in (("1:1", "feed square"), ("4:5", "feed portrait")):
        if a != aspect:
            renditions.append({"name": a, "aspect": a, "use": use})
    checklist = [{"item": t, "done": False} for t in ("Subtitles checked (Persian shaping, no overlap)", "Loudness about -16 LUFS", "Cover chosen", "Caption and hashtags reviewed",
                                                      "Posting time set (never posted automatically)", "AI-generated label added where the platform requires it")]
    return {"renditions": renditions, "caption": caption, "hashtags": list(pub.get("hashtags") or page.profile("strategy").get("hashtags") or [])[:12],
            "cover": "a frame from the hook, with the episode number", "checklist": checklist}


def derive_shot_list(series, ep) -> dict:
    shots = story_services.all_shots(ep)
    return {"shots": [{"scene": s.scene.index, "size": "MS", "angle": "eye-level", "movement": (s.camera or {}).get("move", "static"), "characters": [], "action": s.description or s.narration,
                       "seconds": float(s.duration_sec), "transition": s.transition or "cut", "notes": ""} for s in shots]}


def derive_layout(series, ep) -> dict:
    shots = story_services.all_shots(ep)
    return {"layouts": [{"shot": i, "background": s.scene.location, "staging": s.description, "camera": (s.camera or {}).get("move", "static"), "lighting": "", "props": []}
                        for i, s in enumerate(shots, 1)]}


DERIVE = {"narration": derive_narration, "edit": derive_edit, "delivery": derive_delivery, "shot_list": derive_shot_list, "layout": derive_layout}


def derive(key: str, series, ep) -> dict:
    return DERIVE[key](series, ep)


# ------------------------------------------------------------------ context for the roles

def _latest_data(series, ep, key: str) -> dict:
    from . import ladder

    d = ladder.doc(series, ep, key)
    v = ladder.latest(d) if d else None
    return dict(v.data) if v else {}


def context(key: str, series, ep, language: str, instruction: str = "") -> dict:
    from instai.jobs.handlers.story import series_meta
    from instai.styles import library

    page = series.page
    meta = {"language": language, "format": page.format, "series_title": series.title, "title": series.title, "premise": series.premise, "page_name": page.name,
            "instruction": instruction, "characters": [{"name": c.name, "role": c.role, "appearance": c.appearance, "personality": c.personality} for c in page.characters.all()][:8]}
    try:
        meta.update({k: v for k, v in series_meta(series).items() if k in ("audience", "tone", "memory", "idea", "content_rules")})
    except Exception:  # noqa: BLE001 - context is best-effort
        pass
    lk = library.look_of(page, series)
    st = library.get_style(lk["style_key"]) or {}
    meta["look"] = {"style": st.get("name_en", lk["style_key"]), "realism": lk.get("realism") or st.get("realism", ""), "animation": st.get("animation", "")}
    meta["logline"] = (_latest_data(series, None, "logline") or {}).get("logline", "")
    meta["treatment"] = _latest_data(series, None, "treatment")
    from instai.channel.services import script_context

    meta["channel"] = script_context(series, ep.number if ep else None)
    meta["existing"] = _latest_data(series, ep if ep is not None else None, key)
    if ep is not None:
        meta.update({"episode": {"number": ep.number, "title": ep.title, "logline": ep.logline, "goal": ep.goal, "cliffhanger": ep.cliffhanger}, "duration_sec": ep.duration_sec,
                     "script": ep.script or {}, "beats": _latest_data(series, ep, "beat_sheet").get("beats", []), "dialogue": _latest_data(series, ep, "dialogue"),
                     "shots": [{"index": i, "scene": s.scene.index, "location": s.scene.location, "description": s.description, "narration": s.narration, "duration_sec": s.duration_sec}
                               for i, s in enumerate(story_services.all_shots(ep), 1)],
                     "scenes": [{"index": sc.index, "title": sc.title, "location": sc.location} for sc in ep.scenes.all()],
                     "design_sheets": [{"kind": d.kind, "subject": d.subject, "palette": d.palette} for d in ep.design_sheets.all()][:20],
                     "colour_script": [{"subject": d.subject, "palette": d.palette, "notes": d.notes} for d in ep.design_sheets.filter(kind="colour_script")][:12]})
        try:
            meta["previous_summaries"] = story_services.memory_digest(series, before_episode=ep.number).get("previous_summaries", [])
        except Exception:  # noqa: BLE001
            pass
    meta["episodes_count"] = series.target_episodes
    return meta
