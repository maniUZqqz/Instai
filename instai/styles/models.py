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


class StylePreview(models.Model):
    """A real sample image of a style, made by the GPU (job `styles.preview`). It replaces the built-in swatch in the gallery.

    Built-in styles live in code and cannot carry an asset themselves, so the picture is linked here by the style key.
    `prompt_hash` says what it was made from: when the style's prompt changes the sample is out of date and is made again.
    """

    style_key = models.CharField(max_length=64, unique=True)
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    prompt_hash = models.CharField(max_length=40, blank=True, default="")
    device = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["style_key"]
