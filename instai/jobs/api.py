"""Jobs and queue monitor."""
from __future__ import annotations

from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import queue
from .models import Job, JobLog, Worker


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "kind", "resource", "title", "status", "payload", "result", "progress", "progress_text", "priority", "attempts",
                  "max_attempts", "run_after", "timeout_sec", "cancel_requested", "error", "error_code", "waiting_reason", "created_at",
                  "started_at", "finished_at", "duration_sec", "gpu_seconds", "estimated_sec", "page", "episode", "parent", "idempotency_key"]


def job_response(job: Job, status: int = 202) -> Response:
    return Response({"job": JobSerializer(job).data}, status=status)


@api_view(["GET"])
def jobs(request):
    qs = Job.objects.all()
    q = request.query_params
    if q.get("status"):
        qs = qs.filter(status__in=q["status"].split(","))
    if q.get("episode"):
        qs = qs.filter(episode_id=q["episode"])
    if q.get("page"):
        qs = qs.filter(page_id=q["page"])
    if q.get("kind"):
        qs = qs.filter(kind__startswith=q["kind"])
    return Response(JobSerializer(qs[: int(q.get("limit", 100))], many=True).data)


@api_view(["GET"])
def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk)
    return Response(JobSerializer(job).data)


@api_view(["GET"])
def job_logs(request, pk):
    after = int(request.query_params.get("after", 0))
    logs = JobLog.objects.filter(job_id=pk, id__gt=after).order_by("id")[:500]
    return Response([{"id": l.id, "at": l.at, "level": l.level, "message": l.message} for l in logs])


@api_view(["POST"])
def job_cancel(request, pk):
    job = get_object_or_404(Job, pk=pk)
    return Response(JobSerializer(queue.request_cancel(job)).data)


@api_view(["POST"])
def job_retry(request, pk):
    job = get_object_or_404(Job, pk=pk)
    if job.status in (Job.QUEUED, Job.RUNNING):
        return Response(JobSerializer(job).data)
    return Response(JobSerializer(queue.requeue(job, reset_attempts=True)).data)


@api_view(["GET"])
def monitor(request):
    """Queue + workers + GPU in one call for the production monitor."""
    from instai.core import hardware
    now = timezone.now()
    active = Job.objects.filter(status__in=[Job.QUEUED, Job.RUNNING]).order_by("status", "-priority", "id")[:100]
    recent = Job.objects.filter(status__in=[Job.SUCCEEDED, Job.FAILED, Job.CANCELLED]).order_by("-finished_at", "-id")[:30]
    workers = [{"name": w.name, "pid": w.pid, "alive": bool(w.last_seen and now - w.last_seen < timedelta(seconds=30)), "last_seen": w.last_seen,
                "current_jobs": w.current_jobs, "info": w.info} for w in Worker.objects.all()]
    gpu = hardware.gpu_status()
    holder = Job.objects.filter(status=Job.RUNNING, resource="gpu").first()
    return Response({"active": JobSerializer(active, many=True).data, "recent": JobSerializer(recent, many=True).data, "workers": workers,
                     "gpu": gpu, "gpu_holder": holder.pk if holder else None,
                     "gpu_busy_reason": holder.waiting_reason if holder else "",
                     "worker_alive": any(w["alive"] for w in workers)})


from . import api_workers, worker_api  # noqa: E402  (worker PCs: pairing, tasks, devices)

urlpatterns = [
    *api_workers.urlpatterns,
    *worker_api.urlpatterns,
    path("jobs", jobs),
    path("jobs/<int:pk>", job_detail),
    path("jobs/<int:pk>/logs", job_logs),
    path("jobs/<int:pk>/cancel", job_cancel),
    path("jobs/<int:pk>/retry", job_retry),
    path("monitor", monitor),
]
