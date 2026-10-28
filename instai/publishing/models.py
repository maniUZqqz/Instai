from __future__ import annotations

from django.db import models


class PublishTarget(models.Model):
    """Where a page publishes. Release 1 only exports a package for manual upload; nothing is coupled to Instagram."""

    page = models.ForeignKey("pages.ContentPage", related_name="targets", on_delete=models.CASCADE)
    platform = models.CharField(max_length=24, default="instagram")
    handle = models.CharField(max_length=120, blank=True, default="")
    mode = models.CharField(max_length=12, default="manual")  # manual | api (later: official Graph API only)
    config = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Publication(models.Model):
    STATUS = [(s, s) for s in ("draft", "exported", "scheduled", "published", "failed")]
    episode = models.ForeignKey("story.Episode", related_name="publications", on_delete=models.CASCADE)
    target = models.ForeignKey(PublishTarget, null=True, blank=True, on_delete=models.SET_NULL, related_name="publications")
    caption = models.TextField(blank=True, default="")
    hashtags = models.JSONField(default=list, blank=True)
    cover = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    package = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    external_url = models.URLField(blank=True, default="")
    ai_label = models.BooleanField(default=True)  # label AI-generated content where platforms require it
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
