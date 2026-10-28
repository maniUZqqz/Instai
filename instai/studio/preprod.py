"""Pre-production of one episode, the studio way: script -> storyboard -> animatic -> design sheets -> voice casting -> approval gate.

Production (keyframes, narration, clips, assembly) starts only after the gate when the page has `production.studio_mode` on; the owner can
still send ONE shot back later with a retake request. Stage state is derived from real content (script, shots, an animatic asset, design
sheets, character voices); only the human approvals are stored (`Episode.studio["approvals"]`).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from django.utils import timezone

from instai.assets.models import Asset
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.pages.models import Character
from instai.story import services as story_services
from instai.story import states
from instai.story.models import Episode, Shot

from . import gates
from .models import DesignSheet, RetakeRequest

NARRATORS = {"narrator", "راوی", "راوي", ""}


# ------------------------------------------------------------------ small helpers

def _studio(ep: Episode) -> dict:
    return dict(ep.studio or {})


def approvals(ep: Episode) -> dict:
    return dict(_studio(ep).get("approvals") or {})


def _save(ep: Episode, **changes: Any) -> None:
    st = _studio(ep)
    for k, v in changes.items():
        if v is None:
            st.pop(k, None)
        else:
            st[k] = v
    ep.studio = st
    ep.save(update_fields=["studio", "updated_at"])


def clear_approval(ep: Episode, *stages: str) -> None:
    ap = approvals(ep)
    changed = False
    for s in stages + ("gate",):
        changed = ap.pop(s, None) is not None or changed
    if changed:
        _save(ep, approvals=ap)


def studio_mode(ep: Episode) -> bool:
    return bool(ep.series.page.profile("production").get("studio_mode"))


# ------------------------------------------------------------------ animatic

def keyframe_for(shot: Shot) -> Asset | None:
    return Asset.objects.filter(shot=shot, role="keyframe", is_current=True).order_by("-version").first()


def animatic_hash(ep: Episode) -> str:
    rows = []
    for s in story_services.all_shots(ep):
        kf = keyframe_for(s)
        rows.append([s.pk, s.description, s.narration, s.duration_sec, s.technique, kf.pk if kf else None])
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()[:20]


def animatic_asset(ep: Episode) -> Asset | None:
    return Asset.objects.filter(episode=ep, shot__isnull=True, role="animatic", is_current=True).order_by("-version").first()


def animatic_info(ep: Episode) -> dict:
    a = animatic_asset(ep)
    if not a:
        return {"status": "missing", "asset": None}
    fresh = a.input_hash == animatic_hash(ep)
    return {"status": "fresh" if fresh else "stale", "built_with": (a.provenance or {}).get("notes", []),
            "asset": {"id": a.pk, "url": a.url, "duration_sec": a.duration_sec, "width": a.width, "height": a.height, "created_at": a.created_at,
                      "scratch_audio": (a.provenance or {}).get("scratch_audio", "none"), "stills": (a.provenance or {}).get("stills", {})}}


# ------------------------------------------------------------------ characters and voices

def episode_characters(ep: Episode) -> list[Character]:
    """Characters that appear in the episode: named in a scene or speaking a shot (page characters only)."""
    page = ep.series.page
    names: set[str] = set()
    for sc in ep.scenes.prefetch_related("characters"):
        names.update(c.name for c in sc.characters.all())
    for s in story_services.all_shots(ep):
        if s.speaker.strip().lower() not in NARRATORS:
            names.add(s.speaker.strip())
    for b in (ep.script or {}).get("blocks", []):
        if str(b.get("speaker", "")).strip().lower() not in NARRATORS:
            names.add(str(b["speaker"]).strip())
    return [c for c in page.characters.all() if c.name in names]


def voice_options(language: str = "") -> list[dict]:
    """Voices this machine can speak with right now, from the voice stack (instai.production.voices): one entry per engine voice, with
    the engine's availability and licence (non-commercial engines are listed but flagged; the AI casting never picks them)."""
    from instai.production import voices as voice_stack

    lang = (language or "fa")[:2]
    out: list[dict] = []
    for e in voice_stack.engines_payload(lang):
        voices = e["voices"] or ([{"id": e["default_voice"] or e["id"], "label": e["label"], "language": lang}] if (e["available"] and not e["needs_reference"]) else [])
        for v in voices:
            vid = str(v.get("id") or "")
            out.append({"id": f"{e['id']}:{vid}", "engine": e["id"], "voice": vid, "label": f"{e['id']} · {v.get('label') or vid}", "voice_label": str(v.get("label") or vid), "language": str(v.get("language") or lang),
                        "installed": bool(e["available"]), "commercial": e["commercial"], "commercial_ok": e["commercial"] != "no", "online": bool(e["online"]),
                        "tags": [t for t in ("online" if e["online"] else "offline", e["resource"], "non-commercial" if e["commercial"] == "no" else "") if t]})
    return out


def _language(character: Character, language: str = "") -> str:
    return (language or character.page.language or "fa")[:2]


def _cast(character: Character, language: str):
    from instai.production.models import VoiceCast

    return VoiceCast.objects.filter(character=character, language=language).first()


def casting_rows(ep: Episode) -> list[dict]:
    from instai.production.models import VoiceCast

    rows = []
    for c in episode_characters(ep):
        lang = _language(c)
        cast = _cast(c, lang)
        old = c.voice or {}
        engine = cast.engine if cast else old.get("engine", "")
        voice_id = cast.voice_id if cast else old.get("voice_id", "")
        rows.append({"character": c.pk, "name": c.name, "role": c.role, "personality": c.personality, "engine": engine, "voice_id": voice_id,
                     "has_voice": bool(cast or (old.get("engine") and old.get("voice_id"))), "language": lang,
                     "by_language": {v.language: {"engine": v.engine, "voice_id": v.voice_id} for v in VoiceCast.objects.filter(character=c)}})
    return rows


def set_voice(character: Character, option_id: str, language: str = "") -> Character:
    """option_id from voice_options(); '' removes the cast. Written as a VoiceCast (character, language), which production resolves first."""
    from instai.production.models import VoiceCast

    lang = _language(character, language)
    if not option_id:
        VoiceCast.objects.filter(character=character, language=lang).delete()
        return character
    opt = next((v for v in voice_options(lang) if v["id"] == option_id), None)
    if not opt:
        raise DomainError("validation_error", "این صدا در این رایانه در دسترس نیست.", http_status=400, details={"voice_id": ["unknown"]},
                          message_en="This voice is not available on this computer.")
    VoiceCast.objects.update_or_create(character=character, language=lang, defaults={"engine": opt["engine"], "voice_id": opt["voice"]})
    return character


# ------------------------------------------------------------------ design sheets

def sheet_dict(s: DesignSheet) -> dict:
    return {"id": s.pk, "episode": s.episode_id, "series": s.series_id, "character": s.character_id, "kind": s.kind, "subject": s.subject, "prompt": s.prompt,
            "negative": s.negative, "notes": s.notes, "palette": s.palette, "approved": s.approved, "status": s.status, "last_error": s.last_error, "author": s.author,
            "image_url": s.asset.url if s.asset_id else None, "updated_at": s.updated_at}


def add_sheet(ep: Episode, data: dict, *, author: str = "human") -> DesignSheet:
    kind = data.get("kind") if data.get("kind") in dict(DesignSheet.KINDS) else "character"
    subject = str(data.get("subject") or "").strip()
    if not subject:
        raise DomainError("validation_error", "موضوع برگهٔ طراحی لازم است.", message_en="The design sheet needs a subject.", http_status=400, details={"subject": ["required"]})
    chars = {c.name: c for c in ep.series.page.characters.all()}
    sheet = DesignSheet.objects.create(page=ep.series.page, series=ep.series, episode=ep, character=chars.get(subject) if kind in ("character", "expression") else None,
                                       kind=kind, subject=subject[:200], prompt=str(data.get("prompt") or "").strip(), negative=str(data.get("negative") or "").strip(),
                                       notes=str(data.get("notes") or "").strip(), palette=[c for c in (data.get("palette") or []) if isinstance(c, str)][:8], author=author)
    clear_approval(ep, "design")
    return sheet


def update_sheet(sheet: DesignSheet, data: dict) -> DesignSheet:
    for f in ("subject", "prompt", "negative", "notes"):
        if f in data:
            setattr(sheet, f, str(data[f] or "").strip())
    if "palette" in data:
        sheet.palette = [c for c in (data["palette"] or []) if isinstance(c, str)][:8]
    if "kind" in data and data["kind"] in dict(DesignSheet.KINDS):
        sheet.kind = data["kind"]
    if "approved" in data:
        sheet.approved = bool(data["approved"])
    elif any(k in data for k in ("prompt", "subject", "negative")):
        sheet.approved = False
    sheet.save()
    if sheet.episode_id and not sheet.approved:
        clear_approval(sheet.episode, "design")
    return sheet


def save_ai_sheets(ep: Episode, sheets: list[dict]) -> list[DesignSheet]:
    """Replace the previous AI sheets that nobody approved; hand-made and approved sheets stay."""
    ep.design_sheets.filter(author="ai", approved=False, asset__isnull=True).delete()
    made = [add_sheet(ep, s, author="ai") for s in sheets]
    clear_approval(ep, "design")
    return made


# ------------------------------------------------------------------ retakes

def retake_dict(r: RetakeRequest) -> dict:
    return {"id": r.pk, "episode": r.episode_id, "shot": r.shot_id, "scope": r.scope, "reason": r.reason, "status": effective_retake_status(r),
            "requested_by": r.requested_by, "created_at": r.created_at, "resolved_at": r.resolved_at,
            "shot_label": f"{r.shot.scene.index}.{r.shot.index}" if r.shot_id else ""}


def effective_retake_status(r: RetakeRequest) -> str:
    """An open retake counts as done once a newer asset of the requested kind exists for that shot."""
    if r.status != "open" or not r.shot_id:
        return r.status
    roles = {"keyframe": ["keyframe"], "narration": ["narration"], "clip": ["shot_clip", "render_clip"], "all": ["keyframe", "narration", "shot_clip"]}[r.scope]
    if Asset.objects.filter(shot_id=r.shot_id, role__in=roles, is_current=True, created_at__gt=r.created_at).exists():
        return "done"
    return "open"


def request_retake(shot: Shot, scope: str, reason: str, *, mode: str = "preview", actor: str = "user") -> tuple[RetakeRequest, list]:
    ep = shot.scene.episode
    scope = scope if scope in dict(RetakeRequest.SCOPES) else "keyframe"
    r = RetakeRequest.objects.create(episode=ep, shot=shot, scope=scope, reason=str(reason or "").strip()[:2000], requested_by=actor)
    jobs = story_services.regenerate_shot(shot, {"keyframe": "keyframe", "narration": "narration", "clip": "keyframe", "all": "all"}[scope], mode)
    clear_approval(ep, "animatic")
    return r, jobs


# ------------------------------------------------------------------ stage report and gate

def _content_ready(ep: Episode, stage: str, shots: list[Shot]) -> bool:
    if stage == "script":
        return len((ep.script or {}).get("blocks", [])) >= 3
    if stage == "storyboard":
        return bool(shots)
    if stage == "animatic":
        return animatic_info(ep)["status"] == "fresh"
    if stage == "design":
        return ep.design_sheets.exists()
    if stage == "casting":
        rows = casting_rows(ep)
        return bool(shots) and all(r["has_voice"] for r in rows)
    return True


def stage_report(ep: Episode) -> dict:
    page = ep.series.page
    shots = story_services.all_shots(ep)
    ap = approvals(ep)
    past = states.idx(ep.state) if ep.state in states.ORDER else -1
    rows = []
    for key in gates.PREPROD_STAGES[:-1]:
        required = gates.preprod_stage_needs_human(page, key)
        ready = _content_ready(ep, key, shots)
        explicit = bool(ap.get(key)) or (key == "script" and past >= states.idx(states.STORYBOARDING)) or (key == "storyboard" and past >= states.idx(states.ASSET_GENERATION))
        if key == "animatic" and animatic_info(ep)["status"] == "stale":
            status = "stale"
        elif explicit and (ready or key in ("script", "storyboard")):
            status = "approved"
        elif ready and not required:
            status = "auto"
        elif ready:
            status = "ready"
        else:
            status = "todo"
        rows.append({"key": key, "status": status, "required": required, "approved_at": ap.get(key)})
    blocking = [r["key"] for r in rows if r["status"] not in ("approved", "auto")]
    gate_ready = not blocking
    gate_status = "approved" if ap.get("gate") and gate_ready else ("ready" if gate_ready else "todo")
    rows.append({"key": "gate", "status": gate_status, "required": True, "approved_at": ap.get("gate"), "blocking": blocking})
    return {"stages": rows, "studio_mode": studio_mode(ep), "gate_approved": gate_status == "approved", "blocking": blocking}


def approve_stage(ep: Episode, key: str) -> dict:
    if key not in gates.PREPROD_STAGES:
        raise DomainError("not_found", http_status=404)
    rep = stage_report(ep)
    row = next(r for r in rep["stages"] if r["key"] == key)
    if key == "gate":
        if rep["blocking"]:
            raise DomainError("not_ready", "مرحله‌های زیر هنوز آماده یا تأیید نشده‌اند: " + "، ".join(rep["blocking"]),
                              message_en="These stages are not ready or approved yet: " + ", ".join(rep["blocking"]))
    elif row["status"] in ("todo", "stale"):
        raise DomainError("not_ready", "این مرحله هنوز آماده نیست." if row["status"] == "todo" else "انیماتیک کهنه است؛ دوباره بسازید.",
                          message_en="This stage is not ready yet." if row["status"] == "todo" else "The animatic is stale; build it again.")
    ap = approvals(ep)
    ap[key] = timezone.now().isoformat()
    _save(ep, approvals=ap)
    if key == "design":
        ep.design_sheets.update(approved=True)
    return stage_report(ep)


def revoke_stage(ep: Episode, key: str) -> dict:
    clear_approval(ep, key) if key != "gate" else clear_approval(ep)
    return stage_report(ep)


def assert_gate(ep: Episode) -> None:
    """Called by the episode state machine before storyboarding -> asset_generation: with studio mode on, the gate must be approved."""
    if not studio_mode(ep):
        return
    if not stage_report(ep)["gate_approved"]:
        raise DomainError("not_ready", "پیش‌تولید هنوز تأیید نشده است (انیماتیک، طراحی، انتخاب صدا و تأیید نهایی).", message_en="Pre-production is not approved yet (animatic, design, casting and the final approval).")


def studio_payload(ep: Episode) -> dict:
    return {"report": stage_report(ep), "animatic": animatic_info(ep), "design_sheets": [sheet_dict(s) for s in ep.design_sheets.select_related("asset")],
            "casting": casting_rows(ep), "voices": voice_options(ep.series.page.language), "retakes": [retake_dict(r) for r in ep.retake_requests.select_related("shot__scene")[:50]],
            "translations": {k: {"at": v.get("at"), "provider": v.get("provider"), "model": v.get("model"), "shots": len(v.get("shots") or {})}
                             for k, v in (ep.translations or {}).items()},
            "languages": (ep.series.languages or ep.series.page.languages or ["fa"])}
