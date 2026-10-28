"""Core views: health, hardware detection, media serving (with Range for video seeking) and the SPA shell."""
from __future__ import annotations

import mimetypes
import os
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotModified
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import hardware, runtime


@api_view(["GET"])
def health(request):
    """Cheap liveness + readiness: database, worker heartbeat, ffmpeg, free disk."""
    db_ok = True
    try:
        with connection.cursor() as c:
            c.execute("select 1")
    except Exception:  # noqa: BLE001
        db_ok = False
    from instai.jobs.models import Worker

    cutoff = timezone.now() - timedelta(seconds=30)
    workers = Worker.objects.filter(last_seen__gte=cutoff).count() if db_ok else 0
    ff = runtime.ffmpeg_info()
    d = hardware.disk_info(runtime.media_root())
    return Response({"ok": db_ok, "version": settings.VERSION, "db": db_ok, "workers": workers,
                     "ffmpeg": bool(ff["ffmpeg"]), "disk_free_gb": d["free_gb"], "time": timezone.now().isoformat()})


@api_view(["GET"])
def hardware_view(request):
    return Response(hardware.detect_all(refresh=request.query_params.get("refresh") in ("1", "true")))


# ------------------------------------------------------------------ media (Range support: Chrome needs it to seek in <video>)

_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def serve_media(request, path: str):
    root = Path(settings.MEDIA_ROOT).resolve()
    full = (root / path).resolve()
    if root not in full.parents or not full.is_file():
        raise Http404()
    ctype = mimetypes.guess_type(str(full))[0] or "application/octet-stream"
    size = full.stat().st_size
    rng = _RANGE.match(request.headers.get("Range", ""))
    if rng and (rng.group(1) or rng.group(2)):
        start = int(rng.group(1)) if rng.group(1) else max(0, size - int(rng.group(2)))
        end = int(rng.group(2)) if rng.group(1) and rng.group(2) else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            resp = HttpResponse(status=416)
            resp["Content-Range"] = f"bytes */{size}"
            return resp
        f = open(full, "rb")
        f.seek(start)
        length = end - start + 1

        def chunks(fh=f, remaining=length):
            try:
                while remaining > 0:
                    data = fh.read(min(1 << 20, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
            finally:
                fh.close()

        resp = FileResponse(chunks(), status=206, content_type=ctype)
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(length)
    else:
        resp = FileResponse(open(full, "rb"), content_type=ctype)
        resp["Content-Length"] = str(size)
    resp["Accept-Ranges"] = "bytes"
    resp["Cache-Control"] = "no-cache"
    return resp


def spa(request):
    """Single-page app shell. Unknown non-API paths return index.html so client-side routes survive a reload."""
    index = Path(settings.UI_DIR) / "index.html"
    if not index.is_file():
        return HttpResponse("<h1>InstAI</h1><p>The UI is not built yet (instai/static/app/index.html is missing). "
                            "The API is available under /api/.</p>", content_type="text/html; charset=utf-8", status=503)
    resp = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    resp["Cache-Control"] = "no-cache"
    return resp
