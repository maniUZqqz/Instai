"""System endpoints: hardware, benchmark, settings, providers, models/downloads, formats, dashboard."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.envfile import write_env_value

from . import benchmark, hardware, licences, runtime, settings_store
from .errors import DomainError
from .models import BenchmarkRun

ROOT = Path(__file__).resolve().parents[2]


@api_view(["GET"])
def formats_view(request):
    from instai.pages import formats, profiles

    return Response({**formats.public_registry(), "profile_defaults": {k: profiles.default_data(k) for k in profiles.KINDS},
                     "techniques": __import__("instai.agents.schemas", fromlist=["TECHNIQUES"]).TECHNIQUES})


# ------------------------------------------------------------------ benchmark

@api_view(["GET", "POST"])
def benchmark_view(request):
    if request.method == "POST":
        from instai.jobs.api import JobSerializer
        from instai.jobs.models import Job

        if Job.objects.filter(kind="bench.run", status__in=["queued", "running"]).exists():
            raise DomainError("conflict", "یک بنچمارک در حال اجراست.")
        run = benchmark.enqueue_run({"skip_video": bool(request.data.get("skip_video"))})
        job = Job.objects.filter(kind="bench.run", idempotency_key=f"bench:{run.pk}").first()
        return Response({"run": benchmark.report_dict(run), "job": JobSerializer(job).data}, status=202)
    runs = list(BenchmarkRun.objects.all()[:10])
    return Response({"latest": benchmark.report_dict(runs[0]) if runs else None,
                     "runs": [{"id": r.pk, "status": r.status, "created_at": r.created_at} for r in runs]})


@api_view(["GET"])
def benchmark_report(request, pk):
    run = get_object_or_404(BenchmarkRun, pk=pk)
    resp = HttpResponse(benchmark.report_markdown(run), content_type="text/markdown; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="instai-benchmark-{pk}.md"'
    return resp


# ------------------------------------------------------------------ settings

DEMO = {"llm_provider": "fake", "tts_engine": "fake", "image_engine": "placeholder", "research_fetch": "fake"}
LIVE = {"llm_provider": "ollama", "tts_engine": "auto", "image_engine": "auto", "research_fetch": "off"}
ENUMS = {"llm_provider": ["fake", "ollama", "openai"], "openai_json_mode": ["json_schema", "json_object", "none"],
         "tts_engine": ["auto", "moss", "piper", "pocket", "edge", "fake"], "image_engine": ["auto", "comfyui", "placeholder"],
         "research_fetch": ["off", "wikipedia", "fake"]}


def is_demo_mode() -> bool:
    vals = settings_store.all_effective()
    return all(vals.get(k) == v for k, v in DEMO.items())


def settings_payload() -> dict:
    from instai.providers import registry

    vals = settings_store.all_effective()
    return {"values": vals, "api_key": registry.api_key_state(), "providers": registry.describe_text_providers(),
            "demo_mode": is_demo_mode(), "enums": ENUMS,
            "paths": {"data": str(runtime.project_root() / "data"), "media": str(runtime.media_root()), "models": str(runtime.models_root()),
                      "tools": str(runtime.tools_root()), "env_file": str(ROOT / ".env")}}


@api_view(["GET", "PUT"])
def settings_view(request):
    if request.method == "PUT":
        d = request.data
        for k in settings_store.PUBLIC_KEYS:
            if k in d:
                v = d[k]
                if k in ENUMS and v not in ENUMS[k]:
                    raise DomainError("validation_error", f"مقدار {k} نامعتبر است.", http_status=400, details={k: ["invalid"]})
                if isinstance(v, str):
                    v = v.strip()
                settings_store.set_setting(k, v)
        key = d.get("openai_api_key")
        if isinstance(key, str) and key.strip():
            if "\n" in key or len(key) > 400:
                raise DomainError("validation_error", "کلید نامعتبر است.", http_status=400)
            write_env_value("INSTAI_OPENAI_API_KEY", key.strip())  # secrets live only in .env; never returned by the API
        elif d.get("clear_openai_api_key"):
            write_env_value("INSTAI_OPENAI_API_KEY", "")
    return Response(settings_payload())


@api_view(["POST"])
def demo_mode(request):
    for k, v in (DEMO if request.data.get("enabled") else LIVE).items():
        settings_store.set_setting(k, v)
    return Response(settings_payload())


@api_view(["POST"])
def test_llm(request):
    """Try the chosen provider with a tiny request; returns what happened in plain facts."""
    from instai.providers import registry

    name = request.data.get("provider") or registry.active_provider_name()
    prov = registry.build_provider(name)
    h = prov.health()
    out = {"provider": name, "ok": h["ok"], "detail": h["detail"], "models": h["models"], "model": prov.model}
    if h["ok"] and name != "fake":
        try:
            r = prov.generate([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=16, temperature=0)
            out.update(sample=r.text[:80], seconds=round(r.seconds, 2), model=r.model)
        except Exception as e:  # noqa: BLE001
            out.update(ok=False, detail=str(e)[:200])
    return Response(out)


# ------------------------------------------------------------------ models and downloads

def _package_status() -> dict:
    try:
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "download_models.py"), "--status"], capture_output=True, text=True, timeout=30,
                           cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(p.stdout or "{}")
    except Exception:  # noqa: BLE001
        return {}


@api_view(["GET"])
def models_view(request):
    pk = _package_status()
    from instai.providers.comfy.workflows import WORKFLOWS, workflow_availability

    info = hardware.comfy_object_info() if request.query_params.get("comfy") != "0" else None
    avail = {w["id"]: w for w in workflow_availability(info)} if info is not None else {}
    rows = []
    for m in licences.table():
        row = dict(m)
        row["installed"] = pk.get(m["package"], {}).get("complete") if m.get("package") else None
        rows.append(row)
    return Response({"models": rows, "packages": pk,
                     "workflows": [{**w.describe(), "available": (avail.get(w.id) or {}).get("available"),
                                    "missing": ((avail.get(w.id) or {}).get("missing_nodes", []) + (avail.get(w.id) or {}).get("missing_models", []))}
                                   for w in WORKFLOWS.values()],
                     "checked_on": "2026-10-28"})


@api_view(["POST"])
def downloads_view(request):
    from instai.jobs import queue
    from instai.jobs.api import job_response

    pkgs = request.data.get("packages") or []
    known = _package_status()
    bad = [p for p in pkgs if p not in known]
    if not pkgs or bad:
        raise DomainError("validation_error", "بسته‌ی نامعتبر: " + ", ".join(bad or ["(خالی)"]), http_status=400)
    return job_response(queue.enqueue("downloads.run", {"packages": pkgs}, title="دانلود: " + "، ".join(pkgs), idempotency_key="dl:" + ",".join(sorted(pkgs)) + f":{int(timezone.now().timestamp() // 60)}"))


# ------------------------------------------------------------------ dashboard

@api_view(["GET"])
def dashboard(request):
    from instai.jobs.api import JobSerializer
    from instai.jobs.models import Job, Worker
    from instai.pages.api import page_dict
    from instai.pages.models import ContentPage
    from instai.publishing.models import Publication
    from instai.story import states
    from instai.story.api import episode_brief
    from instai.story.models import Episode

    now = timezone.now()
    day = now - timedelta(hours=24)
    failed_eps = Episode.objects.filter(state=states.FAILED).select_related("series__page")
    failed_jobs = Job.objects.filter(status=Job.FAILED, finished_at__gte=day)
    gpu = hardware.gpu_status()
    running_gpu = Job.objects.filter(status=Job.RUNNING, resource="gpu").first()
    return Response({
        "pages": [page_dict(p, detail=False) for p in ContentPage.objects.filter(status="active")],
        "active_jobs": JobSerializer(Job.objects.filter(status__in=[Job.QUEUED, Job.RUNNING]).order_by("status", "-priority", "id")[:20], many=True).data,
        "recent_episodes": [{**episode_brief(e), "page": e.series.page_id, "page_name": e.series.page.name, "series_title": e.series.title}
                            for e in Episode.objects.select_related("series__page", "arc").order_by("-updated_at")[:8]],
        "upcoming_publications": [{"id": p.pk, "episode": p.episode_id, "episode_title": p.episode.title, "scheduled_at": p.scheduled_at, "status": p.status}
                                  for p in Publication.objects.filter(status="scheduled", scheduled_at__gte=now).order_by("scheduled_at")[:5]],
        "needs_action": [{"type": "episode_failed", "episode": e.pk, "title": f"{e.series.page.name} - قسمت {e.number}", "error": e.error[:200]} for e in failed_eps[:10]] +
                        [{"type": "job_failed", "job": j.pk, "title": j.title, "error": j.error[:200]} for j in failed_jobs[:10]] +
                        [{"type": "ready_for_approval", "episode": e.pk, "title": f"{e.series.page.name} - قسمت {e.number}"}
                         for e in Episode.objects.filter(state=states.READY_FOR_APPROVAL).select_related("series__page")[:10]],
        "gpu": {"present": gpu is not None, "name": gpu["name"] if gpu else None, "total_mb": gpu["total_mb"] if gpu else None,
                "used_mb": gpu["used_mb"] if gpu else None, "utilization": gpu["utilization"] if gpu else None,
                "busy_job": running_gpu.pk if running_gpu else None, "busy_reason": running_gpu.waiting_reason if running_gpu else ""},
        "worker_alive": Worker.objects.filter(last_seen__gte=now - timedelta(seconds=30)).exists(),
        "demo_mode": is_demo_mode(),
        "provider": settings_store.effective("llm_provider"),
    })


urlpatterns = [
    path("formats", formats_view),
    path("system/benchmark", benchmark_view),
    path("system/benchmark/<int:pk>/report.md", benchmark_report),
    path("settings", settings_view),
    path("settings/demo-mode", demo_mode),
    path("settings/test-llm", test_llm),
    path("models", models_view),
    path("downloads", downloads_view),
    path("dashboard", dashboard),
]
