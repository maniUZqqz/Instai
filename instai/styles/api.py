"""Style & theme library API: list, create, edit, duplicate, delete, export/import, prompt preview, thumbnail upload."""
from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError

from . import library, schema


def _kind_ok(kind: str) -> str:
    if kind not in ("style", "theme"):
        raise DomainError("not_found", http_status=404)
    return kind


def vocabulary() -> dict:
    return {"realism": [{"key": k, **v} for k, v in sorted(schema.REALISM.items(), key=lambda kv: kv[1]["order"])],
            "families": [{"key": k, **v} for k, v in schema.FAMILIES.items()],
            "animations": [{"key": k, **v} for k, v in schema.ANIMATIONS.items()],
            "techniques": schema.TECHNIQUES, "palette_roles": schema.PALETTE_ROLES,
            "typography": {"title_weights": schema.TITLE_WEIGHTS, "title_cases": schema.TITLE_CASES,
                           "title_animations": schema.TITLE_ANIMATIONS, "subtitle_positions": schema.SUB_POSITIONS}}


@api_view(["GET"])
def library_view(request):
    return Response({"styles": library.list_presets("style"), "themes": library.list_presets("theme"), **vocabulary()})


@api_view(["GET", "POST"])
def presets(request, kind):
    _kind_ok(kind)
    if request.method == "POST":
        return Response(library.create_preset(kind, request.data, key=request.data.get("key") or None), status=201)
    return Response(library.list_presets(kind))


@api_view(["GET", "PATCH", "DELETE"])
def preset_detail(request, kind, key):
    _kind_ok(kind)
    if request.method == "DELETE":
        library.delete_preset(kind, key)
        return Response(status=204)
    if request.method == "PATCH":
        return Response(library.update_preset(kind, key, request.data))
    p = library.get_preset(kind, key)
    if not p:
        raise DomainError("not_found", http_status=404)
    return Response(p)


@api_view(["POST"])
def preset_duplicate(request, kind, key):
    _kind_ok(kind)
    return Response(library.duplicate_preset(kind, key, request.data if isinstance(request.data, dict) else {}), status=201)


@api_view(["GET"])
def export_view(request):
    sk = [k for k in request.query_params.get("styles", "").split(",") if k] or None
    tk = [k for k in request.query_params.get("themes", "").split(",") if k] or None
    body = json.dumps(library.export_bundle(sk, tk), ensure_ascii=False, indent=1)
    resp = HttpResponse(body, content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="instai-styles.json"'
    return resp


@api_view(["POST"])
def import_view(request):
    return Response(library.import_bundle(request.data), status=201)


@api_view(["POST", "GET"])
def compose_view(request):
    d = request.data if request.method == "POST" else request.query_params
    return Response(library.compose(d.get("style", ""), d.get("theme", ""), d.get("notes", ""), d.get("extra_negative", "")))


@api_view(["POST"])
def thumbnail_upload(request, key):
    """Preview image for a user style (base64 JSON {data}); stored as an Asset and linked in `thumbnail_asset`."""
    from PIL import Image, UnidentifiedImageError

    from instai.assets import storage as asset_storage

    st = library.get_style(key)
    if not st:
        raise DomainError("not_found", http_status=404)
    if st["builtin"]:
        raise DomainError("conflict", "برای پیش‌تنظیم پیش‌فرض ابتدا کپی بگیرید.")
    raw = request.data.get("data") or ""
    if "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
        if not blob or len(blob) > 8 * 1024 * 1024:
            raise ValueError("size")
        im = Image.open(io.BytesIO(blob))
        im.load()
    except (ValueError, UnidentifiedImageError, OSError):
        raise DomainError("validation_error", "تصویر نامعتبر است (png/jpg/webp و حداکثر ۸ مگابایت).", http_status=400)
    im.thumbnail((640, 640))
    tmpdir = Path(tempfile.mkdtemp(prefix="thumb-", dir=settings.MEDIA_ROOT))
    tmp = tmpdir / "t.png"
    im.convert("RGB").save(tmp)
    asset = asset_storage.register(tmp, f"styles/{key}/{uuid.uuid4().hex[:8]}.png", kind="image", role="reference",
                                   provenance={"source": "uploaded by the owner", "style": key})
    shutil.rmtree(tmpdir, ignore_errors=True)
    return Response(library.update_preset("style", key, {"thumbnail_asset": asset.pk}))


urlpatterns = [
    path("library", library_view),
    path("library/export", export_view),
    path("library/import", import_view),
    path("library/compose", compose_view),
    path("library/<str:kind>", presets),
    path("library/<str:kind>/<str:key>", preset_detail),
    path("library/<str:kind>/<str:key>/duplicate", preset_duplicate),
    path("library/style/<str:key>/thumbnail", thumbnail_upload),
]
