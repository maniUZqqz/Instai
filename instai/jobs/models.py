from __future__ import annotations

from django.db import models


class Job(models.Model):
    """Durable DB-backed queue entry. Claimed atomically, leased with heartbeat, retried with backoff, cancellable."""

    QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = "queued", "running", "succeeded", "failed", "cancelled"
    STATUS = [(s, s) for s in (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)]
    RESOURCES = [("cpu", "cpu"), ("gpu", "gpu"), ("net", "net")]

    kind = models.CharField(max_length=60)               # e.g. story.script, prod.keyframes, prod.assemble, bench.run
    resource = models.CharField(max_length=4, choices=RESOURCES, default="cpu")
    title = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS, default=QUEUED, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    progress = models.FloatField(default=0.0)
    progress_text = models.CharField(max_length=300, blank=True, default="")
    priority = models.IntegerField(default=0)            # higher first
    idempotency_key = models.CharField(max_length=160, null=True, blank=True, unique=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    run_after = models.DateTimeField(auto_now_add=True, db_index=True)
    timeout_sec = models.IntegerField(default=3600)
    lease_owner = models.CharField(max_length=80, blank=True, default="")
    lease_expires = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    cancel_requested = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    error_code = models.CharField(max_length=40, blank=True, default="")
    waiting_reason = models.CharField(max_length=200, blank=True, default="")  # e.g. "GPU busy: another program uses 8.1 GB"
    # accounting
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_sec = models.FloatField(null=True, blank=True)
    gpu_seconds = models.FloatField(default=0.0)
    estimated_sec = models.FloatField(null=True, blank=True)
    # links
    page = models.ForeignKey("pages.ContentPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    episode = models.ForeignKey("story.Episode", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "resource", "priority", "run_after"])]

    @property
    def active(self) -> bool:
        return self.status in (self.QUEUED, self.RUNNING)


class JobLog(models.Model):
    job = models.ForeignKey(Job, related_name="logs", on_delete=models.CASCADE)
    at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=8, default="info")
    message = models.TextField()

    class Meta:
        ordering = ["id"]


class Worker(models.Model):
    """Heartbeat row per worker process (the UI shows whether a worker is alive)."""

    name = models.CharField(max_length=80, unique=True)
    pid = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    current_jobs = models.JSONField(default=list, blank=True)
    info = models.JSONField(default=dict, blank=True)
