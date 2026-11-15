"""The cover maker's API (everything under /api/covers). The engine is pure; the writes are jobs (``covers.make``) so a long render or a waiting AI background never blocks the page."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from PIL import Image
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from instai.assets import storage as asset_storage
from instai.assets.models import Asset
from instai.jobs import queue
from instai.jobs.api import JobSerializer

from . import background, ideation, service, subjects
from .engine import archetypes, palette, typo
from .engine import formats as F
from .engine import render as R
from .engine.styles import STYLES
from .models import Cover

log = logging.getLogger("instai.covers")
UPLOAD_KINDS = ("logo", "subject", "background")
MAX_UPLOAD = 12 * 1024 * 1024


def _clean(spec) -> dict:
    try:
        return R.clean_spec(spec if isinstance(spec, dict) else {}, STYLES)
    except R.SpecError as exc:
        raise service.err("validation_error", exc.fa, exc.en) from exc


def _int(v, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _job(job) -> dict:
    return JobSerializer(job).data


@api_view(["GET"])
def meta(request):
    """Everything the screen needs to build its menus: formats, layouts (with fields in both languages), moods, fonts, the mood board and the AI state."""
    return Response({
        "formats": [f.public() for f in F.FORMATS.values()], "default_format": F.DEFAULT_FORMAT,
        "styles": [s.public() for s in STYLES.values()],
        "moods": [{"key": k, "fa": palette.MOOD_FA[k], "en": palette.MOOD_EN[k]} for k in palette.MOODS],
        "fonts": [{"key": k, "label_fa": v["label"][0], "label_en": v["label"][1]} for k, v in typo.FONTS.items()],
        "textures": [t for t in R.TEXTURES if t], "bg_kinds": list(R.BG_KINDS), "logo_positions": list(R.LOGO_POSITIONS), "limits": R.CONTENT_LIMITS,
        "max_variants": service.MAX_VARIANTS, "archetypes": archetypes.public(STYLES), "ai": background.engine_state(), "shaping": {"raqm": bool(typo.use_raqm())},
    })


@api_view(["GET"])
def context(request):
    """The facts of a target and a ready spec for it (the screen starts from this)."""
    q = request.query_params
    page, series, episode, kind = service.resolve_target({"episode": q.get("episode"), "series": q.get("series"), "page": q.get("page"), "kind": q.get("kind")})
    lang = q.get("lang") if q.get("lang") in ("fa", "en") else None
    ctx = service.build_context(page, series, episode, kind, lang)
    spec = service.default_spec(page, series, episode, kind, fmt=q.get("fmt") or F.DEFAULT_FORMAT, style=q.get("style") or None, lang=lang, ctx=ctx)
    look = service.look_of(page, series)
    return Response({"target": {"page": page.pk, "page_name": page.name, "series": series.pk if series else None, "episode": episode.pk if episode else None, "kind": kind},
                     "context": ctx, "spec": spec, "subjects": subjects.list_subjects(page, episode), "look": {k: look[k] for k in ("style_key", "theme_key", "own", "palette", "font")},
                     "latest": [service.cover_dict(c) for c in _history(page, series, episode)[:1]]})


@api_view(["POST"])
def ideas(request):
    d = request.data
    page, series, episode, kind = service.resolve_target(d)
    lang = d.get("lang") if d.get("lang") in ("fa", "en") else None
    ctx = service.build_context(page, series, episode, kind, lang)
    fmt = d.get("format") if d.get("format") in F.FORMATS else F.DEFAULT_FORMAT
    try:
        res = ideation.ideate(ctx, fmt=fmt, count=_int(d.get("count"), 6, 2, 8), use_ai=bool(d.get("use_ai", True)), variation=_int(d.get("variation"), 0, 0, 99), page=page)
    except ValueError as exc:
        raise service.err("validation_error", "از این اطلاعات ایده‌ای ساخته نشد؛ عنوانِ قسمت یا سریال را پر کنید.",
                          "No idea could be made from this; fill in the episode or series title.") from exc
    return Response(res)


@api_view(["POST"])
def preview(request):
    d = request.data
    page, series, episode, _ = service.resolve_target(d)
    return Response(service.preview(_clean(d.get("spec")), page, series, episode, side=_int(d.get("side"), service.PREVIEW_SIDE, 240, 1200)))


def _history(page, series, episode) -> list[Cover]:
    qs = Cover.objects.filter(page=page).select_related("episode", "series", "asset", "bg_asset")
    if episode is not None:
        qs = qs.filter(episode=episode)
    elif series is not None:
        qs = qs.filter(series=series, episode__isnull=True)
    else:
        qs = qs.filter(series__isnull=True, episode__isnull=True)
    return list(qs.order_by("-id")[:60])


@api_view(["GET", "POST"])
def covers(request):
    if request.method == "GET":
        q = request.query_params
        page, series, episode, _ = service.resolve_target({"episode": q.get("episode"), "series": q.get("series"), "page": q.get("page")})
        return Response([service.cover_dict(c) for c in _history(page, series, episode)])
    d = request.data
    page, series, episode, kind = service.resolve_target(d)
    spec = _clean(d.get("spec"))
    n = _int(d.get("variants"), 3, 1, service.MAX_VARIANTS)
    parent = Cover.objects.filter(pk=d.get("parent")).first() if d.get("parent") else None
    cover = Cover.objects.create(page=page, series=series, episode=episode, kind=kind, parent=parent, format=spec["format"], style=spec["style"], spec=spec,
                                 options={"variants": n, "use": bool(d.get("use", True))}, status="draft", note=str(d.get("note") or "")[:300])
    fa = service.language_of(page) == "fa"
    title = (f"کاور قسمت {episode.number}" if fa else f"Cover of episode {episode.number}") if episode is not None else ("کاور" if fa else "Cover")
    job = queue.enqueue("covers.make", {"cover_id": cover.pk, "ai_background": service.ai_wanted(spec)}, episode=episode, page=page.pk, title=title, idempotency_key=f"cover:{cover.pk}:make")
    return Response({"job": _job(job), "cover": service.cover_dict(cover, full=True)}, status=202)


@api_view(["GET", "PATCH", "DELETE"])
def cover_detail(request, pk):
    c = get_object_or_404(Cover.objects.select_related("episode", "series", "asset", "bg_asset", "page"), pk=pk)
    if request.method == "DELETE":
        c.delete()
        return Response(status=204)
    if request.method == "PATCH" and "note" in request.data:
        c.note = str(request.data["note"] or "")[:300]
        c.save(update_fields=["note", "updated_at"])
    return Response(service.cover_dict(c, full=True))


@api_view(["POST"])
def cover_use(request, pk):
    """Make one version the episode's cover (and the cover of its publications that are not published yet)."""
    c = get_object_or_404(Cover.objects.select_related("episode", "page"), pk=pk)
    if c.status not in ("ready", "waiting_bg") or not c.variants:
        raise service.err("not_ready", "این کاور هنوز آماده نیست.", "This cover is not ready yet.", 409)
    service.use_cover(c, request.data.get("variant", c.chosen))
    return Response(service.cover_dict(c, full=True))


@api_view(["POST"])
def cover_more(request, pk):
    """More A/B versions of the same design (up to six)."""
    c = get_object_or_404(Cover.objects.select_related("page", "episode"), pk=pk)
    if len(c.variants) >= service.MAX_VARIANTS:
        raise service.err("conflict", "هر طرح حداکثر ۶ نسخه دارد.", "A design has at most 6 versions.", 409)
    fa = service.language_of(c.page) == "fa"
    job = queue.enqueue("covers.make", {"cover_id": c.pk, "more": _int(request.data.get("count"), 2, 1, service.MAX_VARIANTS)}, episode=c.episode, page=c.page_id,
                        title="نسخه‌های بیشتر از کاور" if fa else "More versions of a cover", idempotency_key=f"cover:{c.pk}:more:{len(c.variants)}")
    return Response({"job": _job(job)}, status=202)


@api_view(["GET"])
def cover_download(request, pk):
    c = get_object_or_404(Cover, pk=pk)
    letter = str(request.query_params.get("variant") or "").upper()
    idx = c.chosen if not letter else (service.LETTERS.index(letter) if letter in service.LETTERS else -1)
    row = next((v for v in c.variants if v["index"] == idx), None)
    if row is None:
        raise service.err("not_found", "این نسخه وجود ندارد.", "That version does not exist.", 404)
    a = get_object_or_404(Asset, pk=row["asset"])
    name = f"cover-{c.pk}-{row['letter']}"
    if (request.query_params.get("fmt") or "png").lower() in ("jpg", "jpeg"):
        data = service.jpeg_of_asset(a)
        if data is None:
            raise service.err("not_found", "فایلِ تصویر پیدا نشد.", "The picture file was not found.", 404)
        resp = HttpResponse(data, content_type="image/jpeg")
        resp["Content-Disposition"] = f'attachment; filename="{name}.jpg"'
        return resp
    resp = HttpResponse(asset_storage.storage.path_for(a.path).read_bytes(), content_type="image/png")
    resp["Content-Disposition"] = f'attachment; filename="{name}.png"'
    return resp


@api_view(["GET"])
def cover_zip(request, pk):
    c = get_object_or_404(Cover, pk=pk)
    if not c.variants:
        raise service.err("not_ready", "این کاور هنوز نسخه‌ای ندارد.", "This cover has no versions yet.", 409)
    resp = HttpResponse(service.zip_of(c), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="cover-{c.pk}.zip"'
    return resp


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload(request):
    """A logo, a character picture or a background of the owner's own: stored as an Asset the spec can name (``logo.asset``, ``subject.asset``, ``background.asset``)."""
    page, _, _, _ = service.resolve_target({"page": request.data.get("page")})
    kind = str(request.data.get("kind") or "subject")
    f = request.FILES.get("file")
    if kind not in UPLOAD_KINDS or f is None:
        raise service.err("validation_error", "نوعِ فایل یا خودِ فایل نامعتبر است.", "The kind or the file is invalid.")
    if f.size > MAX_UPLOAD:
        raise service.err("validation_error", "فایل بزرگ‌تر از ۱۲ مگابایت است.", "The file is larger than 12 MB.")
    tmp = Path(tempfile.mkdtemp(prefix="coverup-", dir=settings.MEDIA_ROOT)) / "upload.png"
    try:
        try:
            with Image.open(f) as im:
                im.thumbnail((2400, 2400))
                im.convert("RGB" if kind == "background" else "RGBA").save(tmp, "PNG")
        except Exception as exc:  # noqa: BLE001 - not a picture
            raise service.err("validation_error", "این فایل تصویرِ قابل‌خواندن نیست.", "This file is not a readable picture.") from exc
        a = asset_storage.register(tmp, f"pages/{page.pk}/covers/upload-{kind}-{tmp.parent.name}.png", kind="image", role="reference", page=page,
                                   provenance={"cover_upload": kind, "name": str(f.name)[:120]})
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return Response({"asset": service.asset_dict(a), "kind": kind}, status=201)


urlpatterns = [
    path("covers/meta", meta),
    path("covers/context", context),
    path("covers/ideas", ideas),
    path("covers/preview", preview),
    path("covers/upload", upload),
    path("covers", covers),
    path("covers/<int:pk>", cover_detail),
    path("covers/<int:pk>/use", cover_use),
    path("covers/<int:pk>/more", cover_more),
    path("covers/<int:pk>/download", cover_download),
    path("covers/<int:pk>/zip", cover_zip),
]
