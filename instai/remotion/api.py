"""Remotion page API (code-to-video).

  GET  /api/remotion/status         the toolchain (Node.js, packages, browser), the setup in progress, the project's size
  GET  /api/remotion/code           the code of every composition and of the shared parts (read from remotion/, what is really installed)
  GET  /api/remotion/kits           the style kit (palette, motion, typography) of every style of the library, for the picker and the preview
  GET  /api/remotion/kit?style=&theme=   one kit
  POST /api/remotion/setup          start the installation (Node.js, packages, browser) as a job; it is also started by START.bat by itself
  POST /api/remotion/render         {composition, props, style, theme, size, still?} -> a render job (mp4, or a png of one frame with `still`)
  GET  /api/remotion/renders        the renders made so far (newest first) with their files
"""
from __future__ import annotations

import re
import time

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import job_response
from instai.jobs.models import Job

from . import kit as kitmod
from . import toolchain

MAX_TEXT = 400
MAX_LINES = 40
MAX_STEPS = 12
_STYLE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _bad(field: str, fa: str, en: str) -> DomainError:
    return DomainError("validation_error", fa, http_status=400, details={field: ["invalid"]}, message_en=en)


def _text(v, field: str, *, required: bool = False) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise _bad(field, "متن باید رشته باشد.", f"{field} must be text")
    v = v.strip()
    if required and not v:
        raise _bad(field, "این بخش خالی است.", f"{field} is empty")
    if len(v) > MAX_TEXT:
        raise _bad(field, f"متن بیش از {MAX_TEXT} نویسه است.", f"{field} is longer than {MAX_TEXT} characters")
    return v


def clean_props(composition: str, raw: dict) -> dict:
    """Only the fields a composition knows, each checked: texts are limited, lists are bounded (a render's length grows with the text)."""
    raw = raw if isinstance(raw, dict) else {}
    if composition == "TitleCard":
        anim = raw.get("animation") or "auto"
        if anim not in ("auto", "none", "fade", "pop", "slide", "typewriter"):
            raise _bad("animation", "حرکت تیتر معتبر نیست.", "unknown title motion")
        return {"title": _text(raw.get("title"), "title", required=True), "subtitle": _text(raw.get("subtitle"), "subtitle"), "kicker": _text(raw.get("kicker"), "kicker"), "animation": anim}
    if composition == "KineticText":
        lines = raw.get("lines")
        if isinstance(lines, str):
            lines = [x for x in lines.splitlines()]
        if not isinstance(lines, list):
            raise _bad("lines", "متن باید فهرستی از خط‌ها باشد.", "lines must be a list")
        lines = [_text(x, "lines") for x in lines if isinstance(x, str) and x.strip()]
        if not lines:
            raise _bad("lines", "دست‌کم یک خط متن بنویسید.", "write at least one line")
        if len(lines) > MAX_LINES:
            raise _bad("lines", f"حداکثر {MAX_LINES} خط.", f"at most {MAX_LINES} lines")
        return {"lines": lines}
    if composition == "Explainer":
        steps = raw.get("steps")
        if not isinstance(steps, list) or not steps:
            raise _bad("steps", "دست‌کم یک مرحله لازم است.", "at least one step is needed")
        if len(steps) > MAX_STEPS:
            raise _bad("steps", f"حداکثر {MAX_STEPS} مرحله.", f"at most {MAX_STEPS} steps")
        out = []
        for s in steps:
            if not isinstance(s, dict):
                raise _bad("steps", "هر مرحله باید عنوان داشته باشد.", "each step needs a title")
            out.append({"title": _text(s.get("title"), "steps", required=True), "body": _text(s.get("body"), "steps")})
        return {"title": _text(raw.get("title"), "title", required=True), "steps": out, "outro": _text(raw.get("outro"), "outro")}
    if composition == "LowerThird":
        return {"name": _text(raw.get("name"), "name", required=True), "role": _text(raw.get("role"), "role"), "backdrop": raw.get("backdrop") is not False}
    raise DomainError("not_found", "این قالب وجود ندارد.", http_status=404, message_en="Unknown composition")


@api_view(["GET"])
def status_view(request):
    return Response(toolchain.status())


@api_view(["GET"])
def code_view(request):
    return Response(toolchain.code_files())


@api_view(["GET"])
def kits_view(request):
    return Response({"kits": kitmod.all_kits(), "default": kitmod.DEFAULT_KEY})


@api_view(["GET"])
def kit_view(request):
    style, theme = request.query_params.get("style", ""), request.query_params.get("theme", "")
    for v in (style, theme):
        if v and not _STYLE.match(v):
            raise _bad("style", "نام سبک معتبر نیست.", "invalid style key")
    return Response(kitmod.style_kit(style or None, theme or None))


@api_view(["POST"])
def setup_view(request):
    job = queue.enqueue("remotion.setup", {}, title="Remotion setup", idempotency_key=f"remotion-setup:{int(time.time() // 60)}")
    return job_response(job)


@api_view(["POST"])
def render_view(request):
    d = request.data if isinstance(request.data, dict) else {}
    comp = d.get("composition")
    if comp not in toolchain.COMPOSITIONS:
        raise DomainError("not_found", "این قالب وجود ندارد.", http_status=404, message_en="Unknown composition")
    size = d.get("size") or "landscape"
    if size not in toolchain.SIZES:
        raise _bad("size", "اندازهٔ خروجی معتبر نیست.", "unknown output size")
    for k in ("style", "theme"):
        if d.get(k) and not _STYLE.match(str(d[k])):
            raise _bad(k, "نام سبک یا تم معتبر نیست.", "invalid style or theme key")
    still = d.get("still")
    if still is not None and (not isinstance(still, int) or isinstance(still, bool) or still < 0 or still > 100000):
        raise _bad("still", "شمارهٔ فریم معتبر نیست.", "invalid frame number")
    props = clean_props(comp, d.get("props") or {})
    payload = {"composition": comp, "props": props, "style": d.get("style") or "", "theme": d.get("theme") or "", "size": size}
    if still is not None:
        payload["still"] = still
    title = f"Remotion: {comp}" + (" (frame)" if still is not None else "")
    job = queue.enqueue("remotion.render", payload, title=title, max_attempts=1)
    return job_response(job)


@api_view(["GET"])
def renders_view(request):
    rows = []
    for j in Job.objects.filter(kind="remotion.render").order_by("-id")[:30]:
        r = j.result or {}
        rows.append({"job_id": j.pk, "status": j.status, "composition": (j.payload or {}).get("composition"), "style": (j.payload or {}).get("style"),
                     "size": (j.payload or {}).get("size"), "url": r.get("url", ""), "kind": r.get("kind", ""), "seconds": r.get("seconds"),
                     "width": r.get("width"), "height": r.get("height"), "frames": r.get("frames"), "bytes": r.get("bytes"),
                     "created_at": j.created_at.isoformat(), "error": j.error[:300] if j.status == Job.FAILED else ""})
    return Response({"renders": rows})


urlpatterns = [
    path("remotion/status", status_view),
    path("remotion/code", code_view),
    path("remotion/kits", kits_view),
    path("remotion/kit", kit_view),
    path("remotion/setup", setup_view),
    path("remotion/render", render_view),
    path("remotion/renders", renders_view),
]
