from __future__ import annotations

from django.db import models


class ChoiceStory(models.Model):
    """An interactive choice story for social posts: a numbered, branching graph of posts (see graph.py for the rules)."""

    STATUS = [("draft", "draft"), ("planned", "planned"), ("approved", "approved")]
    RENDERERS = [("stick", "stick"), ("image", "image")]
    page = models.ForeignKey("pages.ContentPage", related_name="choice_stories", on_delete=models.CASCADE)
    series = models.ForeignKey("story.Series", null=True, blank=True, related_name="choice_stories", on_delete=models.SET_NULL)
    title = models.CharField(max_length=200)
    premise = models.TextField(blank=True, default="")
    genre = models.CharField(max_length=60, blank=True, default="")
    language = models.CharField(max_length=2, default="fa")
    aspect = models.CharField(max_length=5, default="4:5")
    renderer = models.CharField(max_length=8, choices=RENDERERS, default="stick")
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    graph = models.JSONField(default=dict, blank=True)          # {"nodes": [...], "meta": {}}
    settings = models.JSONField(default=dict, blank=True)       # {"post_count": 14, "allow_loops": false, "start": "2026-11-20", "per_day": 1, "hour": "20:00"}
    version = models.IntegerField(default=1)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "choice stories"


class ChoiceVersion(models.Model):
    """A snapshot of the graph before it was replaced (undo and compare)."""

    story = models.ForeignKey(ChoiceStory, related_name="versions", on_delete=models.CASCADE)
    number = models.IntegerField()
    graph = models.JSONField(default=dict)
    author = models.CharField(max_length=8, default="human")   # ai | human | system
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        unique_together = [("story", "number")]
