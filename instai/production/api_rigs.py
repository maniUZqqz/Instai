"""Character rigs (2D puppets): create from the demo drawing, a ZIP/PSD of layers or (job) a character sheet; edit pivots/z; approve; preview."""
from __future__ import annotations

import base64
import binascii
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.assets import storage as asset_storage
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.pages.models import Character
from instai.render.puppet import builder, demo, motions
from instai.render.puppet.rig import Rig, RigError

from .models import CharacterRig


def rig_dict(r: CharacterRig) -> dict:
    spec = r.spec or {}
    parts = {n: {**p, "url": "/media/" + p["image"] if p.get("image") and not str(p["image"]).startswith("/") else p.get("image")}
             for n, p in (spec.get("parts") or {}).items()}
    return {"id": r.pk, "character": r.character_id, "version": r.version, "name": r.name, "source": r.source, "approved": r.approved, "notes": r.notes,
            "created_at": r.created_at, "sheet_asset": r.sheet_asset_id, "size": spec.get("size"), "anchor": spec.get("anchor"), "parts": parts,
            "completeness": builder.completeness(spec) if spec.get("parts") else None}


def _next_version(ch: Character) -> int:
    last = CharacterRig.objects.filter(character=ch).order_by("-version").first()
    return (last.version + 1) if last else 1


def _b64(d: dict, key: str) -> bytes:
    try:
        return base64.b64decode(d.get(key) or "", validate=False)
    except (binascii.Error, ValueError):
        return b""


def create_rig(ch: Character, source: str, d: dict) -> CharacterRig:
    version = _next_version(ch)
    root = Path(settings.MEDIA_ROOT)
    folder = root / "characters" / str(ch.pk) / f"rig{version}"
    try:
        if source == "demo":
            spec = demo.make_rig_spec(ch.name, folder, root)
        elif source in ("upload", "psd"):
            raw = _b64(d, "zip_base64" if source == "upload" else "psd_base64")
            if len(raw) < 200:
                raise RigError("the file is empty")
            if source == "upload":
                layers, extra = builder.layers_from_zip(raw)
            else:
                layers, extra = builder.layers_from_psd(raw), {}
            spec = builder.rig_from_layers(layers, folder, root, extra=extra)
        else:
            raise DomainError("validation_error", "منبع نامعتبر است.", http_status=400, details={"source": ["invalid"]})
        Rig.from_spec(spec, root)        # every image readable, parents consistent
    except RigError as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise DomainError("validation_error", f"رِیگ ساخته نشد: {e}", http_status=400, details={"rig": [str(e)]}) from e
    return CharacterRig.objects.create(character=ch, version=version, name=str(d.get("name") or f"{ch.name} v{version}"), source="demo" if source == "demo" else source,
                                       spec=spec)


@api_view(["GET", "POST"])
def character_rigs(request, pk):
    ch = get_object_or_404(Character, pk=pk)
    if request.method == "POST":
        source = str(request.data.get("source") or "demo")
        if source == "sheet":
            return job_response(queue.enqueue("rig.from_sheet", {"character_id": ch.pk, "name": str(request.data.get("name") or ""),
                                                                 "sheet_asset": request.data.get("sheet_asset")},
                                              title=f"ساخت رِیگ از شیت «{ch.name}»", page=ch.page_id))
        with transaction.atomic():
            rig = create_rig(ch, source, request.data)
        return Response(rig_dict(rig), status=201)
    return Response([rig_dict(r) for r in CharacterRig.objects.filter(character=ch)])


@api_view(["GET", "PATCH", "DELETE"])
def rig_detail(request, pk):
    rig = get_object_or_404(CharacterRig, pk=pk)
    if request.method == "DELETE":
        rig.delete()
        return Response(status=204)
    if request.method == "PATCH":
        d = request.data
        spec = rig.spec
        for field in ("name", "notes"):
            if field in d:
                setattr(rig, field, str(d[field])[:300])
        for name, edit in (d.get("parts") or {}).items():          # pivot / pos / z / parent edits from the rig editor
            p = (spec.get("parts") or {}).get(name)
            if p is None or not isinstance(edit, dict):
                continue
            for k in ("pivot", "pos"):
                if k in edit and isinstance(edit[k], list) and len(edit[k]) == 2:
                    p[k] = [float(edit[k][0]), float(edit[k][1])]
            if "z" in edit:
                p["z"] = int(edit["z"])
            if "parent" in edit:
                p["parent"] = edit["parent"] or None
        if "anchor" in d and isinstance(d["anchor"], list) and len(d["anchor"]) == 2:
            spec["anchor"] = [float(d["anchor"][0]), float(d["anchor"][1])]
        try:
            Rig.from_spec(spec, Path(settings.MEDIA_ROOT))
        except RigError as e:
            raise DomainError("validation_error", f"رِیگ نامعتبر است: {e}", http_status=400) from e
        if "approved" in d:
            if d["approved"]:
                CharacterRig.objects.filter(character=rig.character, approved=True).exclude(pk=rig.pk).update(approved=False)
            rig.approved = bool(d["approved"])
        rig.spec = spec
        rig.save()
    return Response(rig_dict(rig))


@api_view(["POST"])
def rig_preview(request, pk):
    rig = get_object_or_404(CharacterRig, pk=pk)
    return job_response(queue.enqueue("rig.preview", {"rig_id": rig.pk, "motion": str(request.data.get("motion") or "")},
                                      title=f"پیش‌نمایش رِیگ «{rig.name}»", page=rig.character.page_id, priority=5))


@api_view(["GET"])
def puppet_motions(request):
    return Response([{"name": n, "duration": m["duration"], "loop": bool(m.get("loop")), "base": n in motions.BASE_MOTIONS,
                      "parts": sorted(m["tracks"])} for n, m in motions.MOTIONS.items()])


urlpatterns = [
    path("characters/<int:pk>/rigs", character_rigs),
    path("rigs/<int:pk>", rig_detail),
    path("rigs/<int:pk>/preview", rig_preview),
    path("puppet/motions", puppet_motions),
]
