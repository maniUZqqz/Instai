from __future__ import annotations

from django.db import models


class FormatTemplate(models.Model):
    """A user-made development template (built-ins live in code: studio/templates.py). `data` is normalised on read."""

    key = models.CharField(max_length=64, unique=True)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]


class DevStep(models.Model):
    """One development step of one series (instantiated from the series' template). `data` is step-specific."""

    STATUS = [("todo", "todo"), ("active", "active"), ("review", "review"), ("done", "done"), ("skipped", "skipped")]
    series = models.ForeignKey("story.Series", related_name="dev_steps", on_delete=models.CASCADE)
    key = models.CharField(max_length=64)
    kind = models.CharField(max_length=16)
    index = models.IntegerField(default=0)
    status = models.CharField(max_length=10, choices=STATUS, default="todo")
    data = models.JSONField(default=dict, blank=True)
    auto_approved = models.BooleanField(default=False)  # the page's automation level let this step pass without a human click
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["series_id", "index"]
        unique_together = [("series", "key")]


class Idea(models.Model):
    """A card on a brainstorm board. AI and humans both add cards; every card can be edited, merged, rated, rejected, approved."""

    AUTHORS = [("ai", "ai"), ("human", "human"), ("merged", "merged"), ("refined", "refined")]
    STATUS = [("proposed", "proposed"), ("liked", "liked"), ("approved", "approved"), ("rejected", "rejected"), ("merged", "merged")]
    series = models.ForeignKey("story.Series", related_name="ideas", on_delete=models.CASCADE)
    board = models.CharField(max_length=64)
    title = models.CharField(max_length=200)
    logline = models.TextField(blank=True, default="")
    why = models.TextField(blank=True, default="")             # "why it works"
    details = models.JSONField(default=dict, blank=True)       # lens-specific extra fields (all strings)
    tags = models.JSONField(default=list, blank=True)
    author = models.CharField(max_length=8, choices=AUTHORS, default="human")
    status = models.CharField(max_length=10, choices=STATUS, default="proposed")
    rating = models.IntegerField(default=0)                    # 0 = unrated, 1..5
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    notes = models.TextField(blank=True, default="")
    language = models.CharField(max_length=4, blank=True, default="")
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["series_id", "board", "position", "id"]
        indexes = [models.Index(fields=["series", "board", "status"])]


class ResearchDoc(models.Model):
    """Research of a series: `canon` (a real series), `topic` (an explainer topic). Content is structured; items cite Source ids."""

    KINDS = [("canon", "canon"), ("topic", "topic")]
    series = models.ForeignKey("story.Series", related_name="research_docs", on_delete=models.CASCADE)
    kind = models.CharField(max_length=8, choices=KINDS)
    title = models.CharField(max_length=300, blank=True, default="")
    content = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, default="draft")  # draft | reviewed
    language = models.CharField(max_length=4, blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)          # provider/model, fetch notes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["series_id", "kind"]
        unique_together = [("series", "kind")]


class SeriesBible(models.Model):
    """The series bible: one structured document per series; approval is a gate."""

    series = models.OneToOneField("story.Series", related_name="bible", on_delete=models.CASCADE)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, default="draft")  # draft | approved
    version = models.IntegerField(default=1)
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class DesignSheet(models.Model):
    """Pre-production design material: model sheets, expressions, backgrounds, props and the colour script.
    The image is optional (it is rendered by the production side); the PROMPT is what the director approves."""

    KINDS = [("character", "character"), ("expression", "expression"), ("background", "background"), ("prop", "prop"), ("colour_script", "colour_script")]
    page = models.ForeignKey("pages.ContentPage", related_name="design_sheets", on_delete=models.CASCADE)
    series = models.ForeignKey("story.Series", null=True, blank=True, related_name="design_sheets", on_delete=models.CASCADE)
    episode = models.ForeignKey("story.Episode", null=True, blank=True, related_name="design_sheets", on_delete=models.CASCADE)
    character = models.ForeignKey("pages.Character", null=True, blank=True, related_name="design_sheets", on_delete=models.SET_NULL)
    kind = models.CharField(max_length=14, choices=KINDS, default="character")
    subject = models.CharField(max_length=200)
    prompt = models.TextField(blank=True, default="")
    negative = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    palette = models.JSONField(default=list, blank=True)
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved = models.BooleanField(default=False)
    status = models.CharField(max_length=10, default="draft")  # draft | generating | done | failed
    last_error = models.TextField(blank=True, default="")
    author = models.CharField(max_length=8, default="human")   # ai | human
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["episode_id", "kind", "id"]


class RetakeRequest(models.Model):
    """A director's note that sends ONE shot back (the rest of the episode is untouched)."""

    SCOPES = [("keyframe", "keyframe"), ("narration", "narration"), ("clip", "clip"), ("all", "all")]
    episode = models.ForeignKey("story.Episode", related_name="retakes", on_delete=models.CASCADE)
    shot = models.ForeignKey("story.Shot", null=True, related_name="retakes", on_delete=models.SET_NULL)
    scope = models.CharField(max_length=10, choices=SCOPES, default="keyframe")
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, default="open")  # open | done | cancelled
    requested_by = models.CharField(max_length=10, default="user")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
