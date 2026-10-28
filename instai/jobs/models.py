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


class WorkerNode(models.Model):
    """A second computer (PC B) paired over the LAN. It pulls RemoteTasks over HTTP with a token (never the other way round).
    Only the SHA-256 of the token is stored."""

    name = models.CharField(max_length=80, unique=True)
    token_hash = models.CharField(max_length=64, db_index=True)
    enabled = models.BooleanField(default=True)
    address = models.CharField(max_length=80, blank=True, default="")      # last seen client address
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    gpu_name = models.CharField(max_length=120, blank=True, default="")
    vram_total_mb = models.IntegerField(default=0)
    vram_free_mb = models.IntegerField(default=0)
    capabilities = models.JSONField(default=list, blank=True)             # ["comfy:wan22_i2v_a14b_fp8", "voice:moss", ...]
    models_info = models.JSONField(default=dict, blank=True)              # what the worker reported it has
    measured = models.JSONField(default=dict, blank=True)                 # measured speeds from the per-worker benchmark
    info = models.JSONField(default=dict, blank=True)                     # agent version, os, python
    current_task = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]


class PairingCode(models.Model):
    """A short-lived one-time code shown on PC A and typed once on PC B. Only a hash is stored."""

    code_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RemoteTask(models.Model):
    """Pure compute work (a ComfyUI graph, a voice call, a benchmark) with explicit input and output FILES, claimed atomically by a
    worker with a lease and a heartbeat. The user-facing unit stays the local Job; its handler waits for the task."""

    QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = "queued", "running", "succeeded", "failed", "cancelled"
    STATUS = [(s, s) for s in (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)]
    kind = models.CharField(max_length=40)                                 # comfy.graph | voice.tts | voice.sfx | voice.music | bench.node
    status = models.CharField(max_length=10, choices=STATUS, default=QUEUED, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    needs = models.JSONField(default=list, blank=True)                     # capabilities the worker must have
    vram_mb = models.IntegerField(default=0)                               # free VRAM the task needs on that PC
    priority = models.IntegerField(default=0)
    target_worker = models.ForeignKey(WorkerNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="pinned_tasks")
    job = models.ForeignKey(Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="remote_tasks")
    worker = models.ForeignKey(WorkerNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    lease_expires = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=2)
    cancel_requested = models.BooleanField(default=False)
    progress = models.FloatField(default=0.0)
    progress_text = models.CharField(max_length=300, blank=True, default="")
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    retryable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-priority", "id"]
        indexes = [models.Index(fields=["status", "priority", "id"])]
