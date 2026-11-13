"""Character identity API: the lock of a character (identity words, colour key, seed, references, strategy), stick-figure characters, model-sheet jobs and the
consistency report of an episode."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.assets import storage as asset_storage
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import Character, CharacterReference
from instai.render.stick import compose, parts, poses, scenes
from instai.render.stick import spec as stick_spec
from instai.story.models import Episode

from . import check, service, strategies
from .models import CharacterLock


def _char(pk) -> Character:
    return get_object_or_404(Character.objects.select_related("page"), pk=pk)


def lock_dict(l: CharacterLock) -> dict:
    return {"id": l.pk, "character": l.character_id, "status": l.status, "version": l.version, "strategy": l.strategy, "anchor": l.anchor, "avoid": l.avoid, "seed": l.seed, "palette": l.palette,
            "style_key": l.style_key, "refs": l.refs, "stick": l.stick, "has_signature": bool(l.signature), "source": l.source, "notes": l.notes, "locked_at": l.locked_at, "updated_at": l.updated_at}


def identity_payload(c: Character) -> dict:
    from instai.production.models import CharacterRig

    lock = service.get_lock(c)
    refs = [{"id": r.pk, "kind": r.kind, "label": r.label, "approved": r.approved, "url": r.asset.url if r.asset_id else None}
            for r in CharacterReference.objects.filter(character=c).select_related("asset") if r.kind in ("sheet", "expression", "image", "pose")]
    have_refs = bool(lock and service.reference_paths(lock))
    avail = strategies.availability(has_stick=bool(lock and lock.stick), has_refs=have_refs, has_lora=bool(service._approved_lora(c)))
    chosen, why = strategies.pick(lock.strategy if lock else "auto", avail)
    rig = CharacterRig.objects.filter(character=c, source="stick").order_by("-version").first()
    recent = [check.check_dict(x) for x in c.consistency_checks.select_related("character")[:12]]
    return {"character": {"id": c.pk, "name": c.name, "appearance": c.appearance, "page": c.page_id}, "lock": lock_dict(lock) if lock else None, "references": refs, "strategies": avail,
            "resolved": {"strategy": chosen, "why": why}, "rig": {"id": rig.pk, "version": rig.version, "approved": rig.approved} if rig else None, "recent_checks": recent,
            "not_used": strategies.NOT_USED}


@api_view(["GET", "PATCH"])
def character_identity(request, pk):
    c = _char(pk)
    if request.method == "PATCH":
        service.edit_lock(c, request.data if isinstance(request.data, dict) else {})
    return Response(identity_payload(c))


@api_view(["POST"])
def identity_lock(request, pk):
    c = _char(pk)
    service.lock_identity(c)
    return Response(identity_payload(c))


@api_view(["POST"])
def identity_unlock(request, pk):
    c = _char(pk)
    service.unlock_identity(c)
    return Response(identity_payload(c))


@api_view(["POST"])
def identity_stick(request, pk):
    c = _char(pk)
    service.build_stick(c, request.data.get("spec") if isinstance(request.data, dict) else None)
    return Response(identity_payload(c))


@api_view(["POST"])
def identity_refs(request, pk):
    """Choose which of the character's pictures are its model sheet / expression sheet (they must belong to the character)."""
    c = _char(pk)
    lock = service.ensure_lock(c)
    if lock.status == "locked":
        raise DomainError("conflict", "هویت قفل است؛ ابتدا قفل را باز کنید.", http_status=409, message_en="The identity is locked; unlock it first.")
    refs = dict(lock.refs or {})
    for k in ("sheet", "expressions"):
        v = request.data.get(k)
        if v in ("", None, 0):
            refs.pop(k, None) if k in request.data else None
        elif CharacterReference.objects.filter(pk=v, character=c).exists():
            refs[k] = int(v)
        else:
            raise DomainError("validation_error", "این تصویر مرجع به این شخصیت تعلق ندارد.", http_status=400, message_en="That reference does not belong to this character.")
    lock.refs = refs
    lock.save(update_fields=["refs", "updated_at"])
    return Response(identity_payload(c))


@api_view(["POST"])
def identity_palette(request, pk):
    """Suggest the colour key from the chosen model sheet; `apply: true` saves it to the (unlocked) identity."""
    c = _char(pk)
    lock = service.ensure_lock(c)
    paths_ = service.reference_paths(lock)
    if not paths_:
        raise DomainError("not_ready", "ابتدا یک برگهٔ مدل انتخاب کنید.", http_status=409, message_en="Choose a model sheet first.")
    pal = service.suggest_palette(paths_[0])
    if request.data.get("apply"):
        service.edit_lock(c, {"palette": pal})
    return Response({"palette": pal, **identity_payload(c)})


@api_view(["POST"])
def identity_anchor_job(request, pk):
    c = _char(pk)
    return job_response(queue.enqueue("identity.anchor", {"character_id": c.pk, "language": str(request.data.get("language") or "")[:2]}, page=c.page_id, title=f"هویت «{c.name}»"))


@api_view(["POST"])
def identity_sheets_job(request, pk):
    c = _char(pk)
    lock = service.ensure_lock(c)
    if not lock.anchor.strip():
        raise DomainError("not_ready", "ابتدا توصیف هویت را بنویسید.", http_status=409, message_en="Write the identity words first.")
    return job_response(queue.enqueue("identity.sheets", {"character_id": c.pk}, page=c.page_id, title=f"برگهٔ مدل «{c.name}»"))


@api_view(["GET"])
def identity_options(request):
    return Response({"stick": {"choices": {k: list(v) for k, v in stick_spec.CHOICES.items()}, "limb_colours": stick_spec.LIMB_COLOURS, "defaults": stick_spec.DEFAULTS,
                               "expressions": list(stick_spec.EXPRESSIONS), "poses": [{"key": k, "fa": v[0], "en": v[1]} for k, v in poses.POSE_LABELS.items()],
                               "backgrounds": [{"key": k, "fa": v["fa"], "en": v["en"]} for k, v in scenes.BACKGROUNDS.items()]},
                     "strategies": [{"key": k, **{f: v for f, v in strategies.CATALOGUE[k].items() if f != "workflows"}} for k in strategies.ORDER], "not_used": strategies.NOT_USED})


@api_view(["POST"])
def stick_preview(request):
    """A picture of a stick spec in a pose and expression (not saved to any character): the live preview of the character editor."""
    d = request.data if isinstance(request.data, dict) else {}
    spec = stick_spec.normalize(d.get("spec") or {}, name=str((d.get("spec") or {}).get("name") or d.get("name") or "x"))
    pose = d.get("pose") if d.get("pose") in poses.POSES else "stand"
    expr = d.get("expression") if d.get("expression") in parts._EXPR else "neutral"
    bg = d.get("background") if d.get("background") in scenes.BACKGROUNDS else "plain"
    key = stick_spec.spec_hash(spec) + f"-{pose}-{expr}-{bg}"
    rel = f"previews/stick-{key}.png"
    out = Path(settings.MEDIA_ROOT) / rel
    if not out.exists():
        compose.compose_still({"width": 540, "height": 675, "background": bg, "actors": [{"spec": spec, "x": 0.5, "y": 0.93, "height": 0.8, "pose": pose, "expression": expr}]},
                              out, Path(settings.MEDIA_ROOT) / "stickwork" / "preview")
    return Response({"url": "/media/" + rel, "anchor": stick_spec.anchor_text(spec), "palette": stick_spec.palette(spec), "spec": spec})


def _ep(pk) -> Episode:
    return get_object_or_404(Episode.objects.select_related("series__page"), pk=pk)


@api_view(["GET"])
def episode_consistency(request, pk):
    return Response(check.episode_report(_ep(pk)))


@api_view(["POST"])
def episode_consistency_run(request, pk):
    return Response(check.run_episode(_ep(pk), deep=bool(request.data.get("deep"))))


@api_view(["POST"])
def episode_consistency_retakes(request, pk):
    e = _ep(pk)
    made = check.open_retakes(e, [int(x) for x in (request.data.get("shots") or [])] or None)
    return Response({"opened": len(made), "report": check.episode_report(e)})


urlpatterns = [
    path("characters/<int:pk>/identity", character_identity),
    path("characters/<int:pk>/identity/lock", identity_lock),
    path("characters/<int:pk>/identity/unlock", identity_unlock),
    path("characters/<int:pk>/identity/stick", identity_stick),
    path("characters/<int:pk>/identity/refs", identity_refs),
    path("characters/<int:pk>/identity/palette", identity_palette),
    path("characters/<int:pk>/identity/anchor", identity_anchor_job),
    path("characters/<int:pk>/identity/sheets", identity_sheets_job),
    path("identity/options", identity_options),
    path("stick/preview", stick_preview),
    path("episodes/<int:pk>/consistency", episode_consistency),
    path("episodes/<int:pk>/consistency/run", episode_consistency_run),
    path("episodes/<int:pk>/consistency/retakes", episode_consistency_retakes),
]
