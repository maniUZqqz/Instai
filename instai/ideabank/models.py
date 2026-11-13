from __future__ import annotations

from django.db import models


class UserIdea(models.Model):
    """An idea the owner wrote, duplicated from a built-in one, got from the idea generator, or imported. Built-in ideas live in code (seeds_*.py)."""

    key = models.CharField(max_length=64, unique=True)
    data = models.JSONField(default=dict)
    based_on = models.CharField(max_length=64, blank=True, default="")
    origin = models.CharField(max_length=12, default="user")          # user | duplicate | generated | imported
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]


class IdeaMark(models.Model):
    """The owner's own marks on an idea (built-in or his): favourite, hidden from the lists."""

    key = models.CharField(max_length=64, unique=True)
    favorite = models.BooleanField(default=False)
    hidden = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class IdeaUse(models.Model):
    """A project (series) that was started from an idea: the idea shows how many times it was used and where."""

    key = models.CharField(max_length=64, db_index=True)
    series = models.ForeignKey("story.Series", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    page_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
