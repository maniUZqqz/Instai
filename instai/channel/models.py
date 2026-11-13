from __future__ import annotations

from django.db import models


class Channel(models.Model):
    """The channel settings and season slate of one series (episodes, recurring original characters, hooks and cliffhangers, posting schedule)."""

    STATUS = [("draft", "draft"), ("planned", "planned"), ("approved", "approved")]
    series = models.OneToOneField("story.Series", related_name="channel", on_delete=models.CASCADE)
    genre = models.CharField(max_length=32, default="stick_survival")
    runtime_sec = models.IntegerField(default=30)
    episodes_per_season = models.IntegerField(default=8)
    season = models.IntegerField(default=1)
    cadence = models.JSONField(default=dict, blank=True)     # {"days": ["sat","mon","wed"], "time": "20:00", "utc_offset": 210, "start": "2026-11-21"}
    cast = models.JSONField(default=list, blank=True)        # [{"character": id, "name": str, "role": str, "marker": str, "catchphrase": str}]
    rules = models.JSONField(default=dict, blank=True)       # {"max_open_threads": 4, "max_thread_span": 4}
    slate = models.JSONField(default=list, blank=True)       # the season plan rows (see planner.skeleton_season)
    season_title = models.CharField(max_length=200, blank=True, default="")
    season_arc = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    applied = models.BooleanField(default=False)             # the slate was written into the series' episodes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
