"""Platform API (0.6.0): version, the processing queue, the computers' report (+ CSV), scheduled downloads and their settings.

  GET  /api/version                      {name, version, commit}               (the badge in the corner of every screen)
  GET  /api/version/changelog            {current, entries: [{version, date, title, items}]}
  GET  /api/queue                        summary + computers + active jobs + recent jobs (the "Processing queue" page)
  GET  /api/queue/summary                the numbers of the header counter (cheap)
  GET  /api/reports/compute              the report: computers, uptime, jobs per kind, durations, queue wait, errors explained, downloads
  GET  /api/reports/logs                 search in job logs and computer events
  GET  /api/reports/export.csv           ?section=jobs|nodes|samples|sessions|logs|errors|downloads
  GET  /api/downloads/queue              the downloads (waiting for their time / their computer, running, finished)
  GET  /api/downloads/catalog            what can be downloaded, where to, the defaults
  POST /api/downloads/ollama             {model, when}
  POST /api/jobs/<id>/schedule           {when}      change the time of a download that has not started
  POST /api/jobs/<id>/run-now            start a waiting / scheduled download now
  GET/PUT /api/ops/config                download defaults (now | night window), the window, maximum wait, how many days of report to keep
"""
from __future__ import annotations

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai import version as ver
from instai.core import settings_store
from instai.core.errors import DomainError
from instai.jobs import schedule
from instai.jobs.api import JobSerializer, job_response
from instai.jobs.models import Job

from . import downloads, queue_view, report


@api_view(["GET"])
def version_view(request):
    return Response(ver.build_info())


@api_view(["GET"])
def changelog_view(request):
    return Response({"name": ver.NAME, "current": ver.read_version(), "entries": ver.changelog()})


# ------------------------------------------------------------------ the queue page

@api_view(["GET"])
def queue_summary(request):
    return Response(queue_view.summary())


@api_view(["GET"])
def queue_page(request):
    """Active jobs (running + waiting, with the reason and the place in line) and the last finished ones."""
    from instai.jobs.describe import activity

    now = timezone.now()
    rel = ("page", "episode__series__page")
    active = list(Job.objects.filter(status__in=[Job.QUEUED, Job.RUNNING]).select_related(*rel).order_by("status", "-priority", "id")[:300])
    pos = queue_view.positions([j for j in active if j.status == Job.QUEUED], now)
    cache: dict = {}
    try:
        limit = min(200, max(5, int(request.query_params.get("recent") or 40)))
    except ValueError:
        limit = 40
    recent = list(Job.objects.filter(status__in=[Job.SUCCEEDED, Job.FAILED, Job.CANCELLED]).select_related(*rel).order_by("-finished_at", "-id")[:limit])
    rows = [queue_view.job_row(j, now, pos.get(j.pk), activity(j, cache)) for j in active]
    order = {"running": 0, "waiting_gpu": 1, "waiting_node": 2, "waiting_service": 3, "retry": 4, "waiting_turn": 5, "window": 6, "scheduled": 7}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["position"] or 0, r["id"]))
    return Response({"summary": queue_view.summary(now), "nodes": queue_view.node_status(now), "active": rows,
                     "recent": [queue_view.job_row(j, now, None, activity(j, cache)) for j in recent]})


# ------------------------------------------------------------------ the report

@api_view(["GET"])
def compute_report(request):
    start, end = report.parse_range(request.query_params)
    return Response(report.build_report(start, end))


@api_view(["GET"])
def logs_view(request):
    start, end = report.parse_range(request.query_params)
    rows = report.search_logs(request.query_params, start, end)
    return Response({"range": {"from": start.isoformat(), "to": end.isoformat()}, "rows": rows, "count": len(rows)})


@api_view(["GET"])
def export_csv(request):
    section = request.query_params.get("section") or "jobs"
    if section not in report.CSV_SECTIONS:
        raise DomainError("validation_error", "بخش نامعتبر برای خروجی.", http_status=400, details={"section": ["invalid"]}, message_en="Invalid export section.")
    start, end = report.parse_range(request.query_params)
    body = report.csv_section(section, start, end, request.query_params)
    resp = HttpResponse(body, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="instai-{section}-{timezone.now():%Y%m%d}.csv"'
    return resp


# ------------------------------------------------------------------ downloads and their schedule

@api_view(["GET"])
def downloads_queue(request):
    now = timezone.now()
    jobs = list(Job.objects.filter(kind__startswith="downloads.").order_by("-id")[:80])
    pos = queue_view.positions([j for j in jobs if j.status == Job.QUEUED], now)
    rows = [queue_view.job_row(j, now, pos.get(j.pk)) for j in jobs]
    for r, j in zip(rows, jobs):
        r["title"] = r["title_fa"]
        r["target"] = (j.payload or {}).get("target_name") or "local"
        r["packages"] = (j.payload or {}).get("packages") or ([(j.payload or {}).get("model")] if (j.payload or {}).get("model") else [])
    return Response({"jobs": rows, "config": schedule.config(), "now": now.isoformat()})


@api_view(["GET"])
def downloads_catalog(request):
    return Response(downloads.catalog())


@api_view(["POST"])
def ollama_download(request):
    return job_response(downloads.start_ollama(str(request.data.get("model") or ""), when=request.data.get("when")))


@api_view(["POST"])
def job_schedule(request, pk):
    job = get_object_or_404(Job, pk=pk)
    return Response(JobSerializer(downloads.reschedule(job, request.data.get("when"))).data)


@api_view(["POST"])
def job_run_now(request, pk):
    job = get_object_or_404(Job, pk=pk)
    return Response(JobSerializer(downloads.run_now(job)).data)


@api_view(["GET", "PUT"])
def ops_config(request):
    if request.method == "PUT":
        d = request.data
        cur = schedule.config()
        new = dict(cur)
        if "download_mode" in d:
            if d["download_mode"] not in ("now", "window"):
                raise DomainError("validation_error", "حالت دانلود باید «الان» یا «بازهٔ شبانه» باشد.", http_status=400, message_en="The download mode must be now or night window.")
            new["download_mode"] = d["download_mode"]
        if "download_window" in d:
            win = schedule.norm_window(str(d["download_window"]))
            if not win:
                raise DomainError("validation_error", "بازه را مثل ۰۲:۰۰-۰۷:۰۰ بنویسید (ساعت شروع و پایان فرق داشته باشد).", http_status=400,
                                  message_en="Write the window like 02:00-07:00 (start and end must differ).")
            new["download_window"] = win
        if "max_wait_hours" in d:
            try:
                v = float(d["max_wait_hours"] or 0)
            except (TypeError, ValueError):
                v = -1
            if not 0 <= v <= 8760:
                raise DomainError("validation_error", "سقف انتظار را به ساعت و بین ۰ تا ۸۷۶۰ بنویسید (۰ یعنی هرگز).", http_status=400,
                                  message_en="Write the wait limit in hours, 0 to 8760 (0 means never).")
            new["max_wait_hours"] = v
        if "retention_days" in d:
            try:
                v = int(d["retention_days"])
            except (TypeError, ValueError):
                v = 0
            if not 1 <= v <= 365:
                raise DomainError("validation_error", "تعداد روزِ نگهداریِ گزارش باید بین ۱ تا ۳۶۵ باشد.", http_status=400, message_en="Days to keep the report: 1 to 365.")
            new["retention_days"] = v
        settings_store.set_setting("ops_config", new)
    return Response(schedule.config())


urlpatterns = [
    path("version", version_view),
    path("version/changelog", changelog_view),
    path("queue", queue_page),
    path("queue/summary", queue_summary),
    path("reports/compute", compute_report),
    path("reports/logs", logs_view),
    path("reports/export.csv", export_csv),
    path("downloads/queue", downloads_queue),
    path("downloads/catalog", downloads_catalog),
    path("downloads/ollama", ollama_download),
    path("jobs/<int:pk>/schedule", job_schedule),
    path("jobs/<int:pk>/run-now", job_run_now),
    path("ops/config", ops_config),
]
