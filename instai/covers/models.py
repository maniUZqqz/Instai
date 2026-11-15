from __future__ import annotations

from django.db import models


class Cover(models.Model):
    """One cover DESIGN of an episode, a series, a season or the channel: the spec (layout, format, texts, colours ...) and up to six A/B versions made from it.

    The versions are pictures (``Asset`` rows) in ``variants``; ``asset`` is the chosen one, registered as the episode's cover (role "cover") so the publishing package
    already ships it. A design is never edited in place: "edit again" makes a NEW design from the old spec (``parent``), so the history keeps every earlier cover."""

    KINDS = [(k, k) for k in ("episode", "series", "season", "banner")]
    STATUS = [(k, k) for k in ("draft", "rendering", "waiting_bg", "ready", "failed")]
    BG_STATES = [(k, k) for k in ("procedural", "ai", "waiting", "demo", "off")]

    page = models.ForeignKey("pages.ContentPage", related_name="covers", on_delete=models.CASCADE)
    series = models.ForeignKey("story.Series", null=True, blank=True, related_name="covers", on_delete=models.SET_NULL)
    episode = models.ForeignKey("story.Episode", null=True, blank=True, related_name="covers", on_delete=models.SET_NULL)
    kind = models.CharField(max_length=10, choices=KINDS, default="episode")
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL)
    format = models.CharField(max_length=24, default="youtube")
    style = models.CharField(max_length=32, default="episode_card")
    spec = models.JSONField(default=dict, blank=True)               # the clean engine spec
    options = models.JSONField(default=dict, blank=True)            # {variants, use}
    status = models.CharField(max_length=12, choices=STATUS, default="draft")
    bg_state = models.CharField(max_length=12, choices=BG_STATES, default="procedural")
    bg_asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")        # the chosen version = the episode's cover
    chosen = models.IntegerField(default=0)
    variants = models.JSONField(default=list, blank=True)           # [{index, letter, asset, variation}]
    warnings = models.JSONField(default=list, blank=True)           # [{code, fa, en}]
    report = models.JSONField(default=dict, blank=True)             # {size, palette, texts, background}
    error = models.TextField(blank=True, default="")
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["episode", "-id"]), models.Index(fields=["series", "-id"])]
