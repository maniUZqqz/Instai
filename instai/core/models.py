from __future__ import annotations

from django.db import models


class AppSetting(models.Model):
    """Non-secret settings edited in the UI (provider choice, URLs, model names). Secrets stay in .env."""

    key = models.CharField(max_length=80, primary_key=True)
    value = models.JSONField(default=None, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class BenchmarkRun(models.Model):
    """One run of the Phase 0 benchmark on a real machine. Nothing here is ever invented."""

    STATUS = [("queued", "queued"), ("running", "running"), ("done", "done"), ("failed", "failed"), ("cancelled", "cancelled")]
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="queued")
    machine = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-id"]


class BenchmarkResult(models.Model):
    STEPS = [("image", "image"), ("video", "video"), ("tts", "tts"), ("llm", "llm")]
    STATUS = [("ok", "ok"), ("skipped", "skipped"), ("failed", "failed")]
    run = models.ForeignKey(BenchmarkRun, related_name="results", on_delete=models.CASCADE)
    step = models.CharField(max_length=12, choices=STEPS)
    candidate = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS)
    seconds = models.FloatField(null=True, blank=True)
    vram_peak_mb = models.IntegerField(null=True, blank=True)
    message = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
