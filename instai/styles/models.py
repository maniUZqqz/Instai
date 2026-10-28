from __future__ import annotations

from django.db import models


class UserPreset(models.Model):
    """A style preset or theme created, duplicated or imported by the owner. Built-ins live in code and are never stored here."""

    KINDS = [("style", "style"), ("theme", "theme")]
    kind = models.CharField(max_length=8, choices=KINDS)
    key = models.CharField(max_length=64)
    data = models.JSONField(default=dict)
    based_on = models.CharField(max_length=64, blank=True, default="")
    origin = models.CharField(max_length=10, default="user")  # user | duplicate | imported
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "id"]
        unique_together = [("kind", "key")]
