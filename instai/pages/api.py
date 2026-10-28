"""Pages, profiles, characters: serializers, views and urls."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response

from . import formats, profiles
from .models import Character, CharacterReference, ContentPage, SettingsProfile


class ReferenceSerializer(serializers.ModelSerializer):
    asset_url = serializers.SerializerMethodField()

    class Meta:
        model = CharacterReference
        fields = ["id", "character", "kind", "label", "asset", "asset_url", "approved", "notes", "created_at"]
        read_only_fields = ["character"]

    def get_asset_url(self, obj):
        return obj.asset.url if obj.asset_id else None


class CharacterSerializer(serializers.ModelSerializer):
    references = ReferenceSerializer(many=True, read_only=True)

    class Meta:
        model = Character
        fields = ["id", "page", "name", "role", "profile", "personality", "appearance", "abilities", "motivations", "voice",
                  "is_original", "franchise", "approved", "references", "created_at"]
        read_only_fields = ["page"]


def page_dict(page: ContentPage, detail: bool = True) -> dict:
    from instai.story.models import Episode, Series

    d = {"id": page.pk, "name": page.name, "handle": page.handle, "format": page.format, "languages": page.languages, "idea": page.idea,
         "automation_level": page.automation_level, "status": page.status, "created_at": page.created_at, "updated_at": page.updated_at,
         "format_label": formats.get_format(page.format)["label_fa"], "series_count": Series.objects.filter(page=page).count(),
         "episode_count": Episode.objects.filter(series__page=page).count(),
         "episodes_approved": Episode.objects.filter(series__page=page, state__in=["approved", "scheduled", "published"]).count()}
    if detail:
        d["profiles"] = {k: page.profile(k) for k in profiles.KINDS}
        d["characters"] = CharacterSerializer(page.characters.all(), many=True).data
        d["notices"] = notices_for(page)
    return d


def notices_for(page: ContentPage) -> list[dict]:
    n = []
    pol = formats.get_format(page.format)["policy"]
    if pol["fan_notice"]:
        n.append({"key": "fan", "text": formats.FAN_NOTICE_FA})
    if pol["sourced"]:
        n.append({"key": "sourced", "text": formats.EXPLAINER_NOTICE_FA})
    if pol["synthetic_presenter_only"]:
        n.append({"key": "presenter", "text": formats.PRESENTER_NOTICE_FA})
    return n


@api_view(["GET", "POST"])
def pages(request):
    if request.method == "GET":
        qs = ContentPage.objects.filter(status=request.query_params.get("status", "active")) if request.query_params.get("status") else ContentPage.objects.all()
        return Response([page_dict(p, detail=False) for p in qs])
    from instai.story import services

    data = request.data
    name = (data.get("name") or "").strip()
    if not name:
        raise DomainError("validation_error", "نام صفحه لازم است.", http_status=400, details={"name": ["required"]})
    if data.get("format", formats.ANIME) not in formats.FORMATS:
        raise DomainError("validation_error", "قالب نامعتبر است.", http_status=400, details={"format": ["invalid"]})
    page = services.create_page(data)
    return Response(page_dict(page), status=201)


@api_view(["GET", "PATCH", "DELETE"])
def page_detail(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "DELETE":
        page.delete()
        return Response(status=204)
    if request.method == "PATCH":
        for f in ("name", "handle", "idea", "automation_level", "status", "languages"):
            if f in request.data:
                setattr(page, f, request.data[f])
        if page.automation_level not in ("manual", "assisted", "automatic"):
            raise DomainError("validation_error", "سطح خودکارسازی نامعتبر است.", http_status=400)
        page.save()
    return Response(page_dict(page))


@api_view(["PUT"])
def page_profile(request, pk, kind):
    page = get_object_or_404(ContentPage, pk=pk)
    if kind not in profiles.KINDS:
        raise DomainError("not_found", http_status=404)
    bad = profiles.validate_techniques(request.data) if kind == "production" else []
    if bad:
        raise DomainError("validation_error", "تکنیک نامعتبر: " + ", ".join(bad), http_status=400)
    page.set_profile(kind, request.data.get("data", request.data) if isinstance(request.data.get("data", None), dict) else request.data)
    return Response(page_dict(page))


@api_view(["GET", "POST"])
def templates(request):
    if request.method == "POST":
        kind = request.data.get("kind")
        if kind not in profiles.KINDS:
            raise DomainError("validation_error", "نوع پروفایل نامعتبر است.", http_status=400)
        t = SettingsProfile.objects.create(kind=kind, name=request.data.get("name", ""), data=request.data.get("data") or {}, is_template=True)
        return Response({"id": t.pk, "kind": t.kind, "name": t.name, "data": t.data}, status=201)
    qs = SettingsProfile.objects.filter(is_template=True)
    if request.query_params.get("kind"):
        qs = qs.filter(kind=request.query_params["kind"])
    return Response([{"id": t.pk, "kind": t.kind, "name": t.name, "data": t.data} for t in qs])


@api_view(["POST"])
def apply_template(request, pk):
    page = get_object_or_404(ContentPage, pk=pk)
    t = get_object_or_404(SettingsProfile, pk=request.data.get("template_id"), is_template=True)
    page.set_profile(t.kind, t.data)  # copied, never shared live
    return Response(page_dict(page))


@api_view(["POST"])
def strategy_proposal(request):
    """Wizard step 'idea -> strategy' (page does not exist yet). Returns a job; the proposal is in job.result.strategy."""
    meta = {k: request.data.get(k) for k in ("page_name", "format", "language", "idea", "niche", "audience", "tone", "episodes_count",
                                             "episode_length_sec") if request.data.get(k) not in (None, "")}
    meta.setdefault("format", formats.ANIME)
    meta.setdefault("language", "fa")
    if not meta.get("idea") and not meta.get("page_name"):
        raise DomainError("validation_error", "ایده یا نام صفحه را بنویسید.", http_status=400)
    job = queue.enqueue("story.strategy", meta, title="پیشنهاد استراتژی")
    return job_response(job)


@api_view(["POST"])
def page_strategy(request, pk):
    from instai.jobs.handlers.story import page_meta

    page = get_object_or_404(ContentPage, pk=pk)
    job = queue.enqueue("story.strategy", {**page_meta(page), **{k: v for k, v in request.data.items() if v not in (None, "")}}, page=page,
                        title="پیشنهاد استراتژی")
    return job_response(job)


@api_view(["POST"])
def page_apply_strategy(request, pk):
    from instai.story import services

    page = get_object_or_404(ContentPage, pk=pk)
    if not isinstance(request.data.get("strategy"), dict):
        raise DomainError("validation_error", "strategy لازم است.", http_status=400)
    services.apply_strategy(page, request.data["strategy"])
    return Response(page_dict(page))


@api_view(["GET", "POST"])
def page_characters(request, pk):
    from instai.story import services

    page = get_object_or_404(ContentPage, pk=pk)
    if request.method == "POST":
        if not (request.data.get("name") or "").strip():
            raise DomainError("validation_error", "نام شخصیت لازم است.", http_status=400)
        c = services.add_character(page, request.data)
        return Response(CharacterSerializer(c).data, status=201)
    return Response(CharacterSerializer(page.characters.all(), many=True).data)


@api_view(["GET", "PATCH", "DELETE"])
def character_detail(request, pk):
    c = get_object_or_404(Character, pk=pk)
    if request.method == "DELETE":
        c.delete()
        return Response(status=204)
    if request.method == "PATCH":
        ser = CharacterSerializer(c, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(CharacterSerializer(c).data)


@api_view(["POST"])
def character_references(request, pk):
    c = get_object_or_404(Character, pk=pk)
    ser = ReferenceSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    ser.save(character=c)
    return Response(CharacterSerializer(c).data, status=201)


@api_view(["POST"])
def character_reference_upload(request, pk):
    """Upload a reference image (character sheet, pose, expression) as base64 JSON: {data, kind, label}. Stored as an Asset."""
    import base64
    import io
    import tempfile
    import uuid
    from pathlib import Path

    from django.conf import settings
    from PIL import Image, UnidentifiedImageError

    from instai.assets import storage as asset_storage

    c = get_object_or_404(Character, pk=pk)
    raw = request.data.get("data") or ""
    if "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
        if not blob or len(blob) > 10 * 1024 * 1024:
            raise ValueError("size")
        im = Image.open(io.BytesIO(blob))
        im.load()
    except (ValueError, UnidentifiedImageError, OSError):
        raise DomainError("validation_error", "تصویر نامعتبر است (فرمت png/jpg/webp و حداکثر ۱۰ مگابایت).", http_status=400)
    tmpdir = Path(tempfile.mkdtemp(prefix="ref-", dir=settings.MEDIA_ROOT))
    tmp = tmpdir / "ref.png"
    im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(tmp)
    kind = request.data.get("kind", "image")
    kind = kind if kind in dict(CharacterReference.KINDS) else "image"
    asset = asset_storage.register(tmp, f"characters/{c.pk}/{uuid.uuid4().hex[:10]}.png", kind="image", role="reference", page=c.page,
                                   provenance={"source": "uploaded by the owner", "character": c.pk})
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)
    CharacterReference.objects.create(character=c, kind=kind, label=request.data.get("label", ""), asset=asset)
    return Response(CharacterSerializer(c).data, status=201)


@api_view(["PATCH", "DELETE"])
def reference_detail(request, pk):
    r = get_object_or_404(CharacterReference, pk=pk)
    char = r.character
    if request.method == "DELETE":
        r.delete()
    else:
        ser = ReferenceSerializer(r, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
    return Response(CharacterSerializer(char).data)


urlpatterns = [
    path("pages", pages),
    path("pages/<int:pk>", page_detail),
    path("pages/<int:pk>/profiles/<str:kind>", page_profile),
    path("pages/<int:pk>/apply-template", apply_template),
    path("pages/<int:pk>/strategy", page_strategy),
    path("pages/<int:pk>/apply-strategy", page_apply_strategy),
    path("pages/<int:pk>/characters", page_characters),
    path("profile-templates", templates),
    path("strategy", strategy_proposal),
    path("characters/<int:pk>", character_detail),
    path("characters/<int:pk>/references", character_references),
    path("characters/<int:pk>/references/upload", character_reference_upload),
    path("references/<int:pk>", reference_detail),
]
