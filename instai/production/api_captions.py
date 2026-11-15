"""Captions API: the catalogue of the presets, real preview pictures made by the engine, and an episode's own caption setting.

The page's default lives in its visual profile (`visual.caption_style`, saved through the normal profile API); an episode overrides it key by key
(`PUT /api/episodes/<id>/captions`, `{}` clears the override).
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core import runtime
from instai.core.errors import DomainError
from instai.pages.models import ContentPage
from instai.render import caption_previews, captions, safezones, titles_ass
from instai.story.models import Episode

from . import captions as ep_captions

PREVIEW_URL = "/media/captions/previews"


def preview_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / "captions" / "previews"


def fonts_info() -> list[dict]:
    return [{"key": k, "fa": v["fa"], "en": v["en"], "family": v["family"], "licence": "SIL OFL 1.1"} for k, v in titles_ass.FONTS.items()]


@api_view(["GET"])
def captions_catalogue(request):
    return Response({**captions.catalogue(), "default": captions.DEFAULT_CONFIG, "fonts": fonts_info(), "samples": caption_previews.SAMPLES,
                     "shapes": list(caption_previews.SHAPES), "libass": bool((runtime.ffmpeg_info().get("features") or {}).get("ass"))})


@api_view(["GET"])
def captions_previews(request):
    """Pictures of every preset for a page (or an episode: its series look): `?page=<id>` or `?episode=<id>`, `&shape=vertical|landscape`, `&zone=<key>`."""
    q = request.query_params
    shape = q.get("shape") if q.get("shape") in caption_previews.SHAPES else "vertical"
    zone = q.get("zone") if q.get("zone") in safezones.KEYS else safezones.AUTO
    ep = get_object_or_404(Episode, pk=q["episode"]) if q.get("episode") else None
    page = ep.series.page if ep else (get_object_or_404(ContentPage, pk=q["page"]) if q.get("page") else None)
    if page is None:
        raise DomainError("validation_error", "صفحه یا قسمت مشخص نشده است.", message_en="Give a page or an episode.", http_status=400, details={"page": ["required"]})
    if ep is not None:
        look = ep_captions.look_for(ep)
    else:
        from instai.remotion import kit
        from instai.styles import library

        lk = library.look_of(page)
        k = kit.style_kit(lk.get("style_key") or None, lk.get("theme_key") or None)
        look = {"palette": k["palette"], "typography": k["typography"], "style_key": k["key"], "theme_key": k["theme_key"]}
    rows = caption_previews.previews(look, preview_dir(), PREVIEW_URL, language=page.language, shape=shape, zone=zone, platform=ep_captions.platform_of(page),
                                     position=ep_captions.position_of(page), subtitle_style=page.profile("visual").get("subtitle"))
    w, h = caption_previews.SHAPES[shape]
    resolved = safezones.zone_for(w, h, ep_captions.platform_of(page), zone)
    return Response({"previews": rows, "shape": shape, "zone": resolved, "margins": safezones.margins(resolved), "language": page.language,
                     "platform": ep_captions.platform_of(page), "look": {"style_key": look["style_key"], "theme_key": look["theme_key"], "palette": look["palette"]},
                     "ok": all(not r.get("error") for r in rows)})


@api_view(["GET", "PUT", "DELETE"])
def episode_captions(request, pk):
    ep = get_object_or_404(Episode, pk=pk)
    if request.method == "DELETE":
        return Response(ep_captions.set_override(ep, {}))
    if request.method == "PUT":
        data = request.data if isinstance(request.data, dict) else {}
        for k, allowed in (("preset", captions.PRESETS), ("mode", captions.MODES), ("zone", safezones.KEYS)):
            v = data.get(k)
            if v not in (None, "") and v not in allowed:
                raise DomainError("validation_error", "مقدار زیرنویس نامعتبر است.", message_en=f"Unknown caption {k}: {v}", http_status=400, details={k: ["invalid"]})
        return Response(ep_captions.set_override(ep, data))
    return Response(ep_captions.summary(ep))


urlpatterns = [
    path("captions", captions_catalogue),
    path("captions/previews", captions_previews),
    path("episodes/<int:pk>/captions", episode_captions),
]
