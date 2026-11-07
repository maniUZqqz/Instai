"""History of the processing computers for the report: when each was online (sessions), how loaded it was (samples) and what happened
to it (events: came online, went offline, a job was left waiting, lines from the worker PC's own log).

"Computer" is the string `local` (this PC, A) or the paired worker's name (PC B). Rows are bounded: `report.maintain` thins and deletes
old ones (the owner chooses how many days to keep, default 30).
"""
from __future__ import annotations

from django.db import models


class NodeSession(models.Model):
    """One continuous stretch of 'online'. A gap longer than the heartbeat grace ends it; the next heartbeat opens a new one."""

    node = models.CharField(max_length=80, db_index=True)
    started_at = models.DateTimeField()
    last_seen = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    version = models.CharField(max_length=20, blank=True, default="")      # InstAI version of the program that reported it
    info = models.JSONField(default=dict, blank=True)                      # gpu name, os, host ...

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["node", "-started_at"])]


class NodeSample(models.Model):
    """A resource reading (at most one a minute per computer)."""

    node = models.CharField(max_length=80)
    at = models.DateTimeField()
    gpu_util = models.FloatField(null=True, blank=True)       # %
    gpu_temp = models.FloatField(null=True, blank=True)       # degrees C
    vram_used_mb = models.IntegerField(null=True, blank=True)
    vram_total_mb = models.IntegerField(null=True, blank=True)
    ram_used_mb = models.IntegerField(null=True, blank=True)
    ram_total_mb = models.IntegerField(null=True, blank=True)
    disk_free_gb = models.FloatField(null=True, blank=True)
    disk_total_gb = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["node", "-at"])]


class NodeEvent(models.Model):
    """Something that happened to / on a computer: online, offline, a job waiting for it, a line of the worker PC's own log."""

    node = models.CharField(max_length=80, db_index=True)
    at = models.DateTimeField(db_index=True)
    level = models.CharField(max_length=8, default="info")
    kind = models.CharField(max_length=20, default="log")      # online | offline | wait | log | error
    message = models.TextField(blank=True, default="")       # raw line (a worker PC's own log); the other kinds are worded from `data` at read time
    data = models.JSONField(default=dict, blank=True)         # {"version": ..., "code": ..., "job": ...}: what the Persian/English line is built from
    job_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
