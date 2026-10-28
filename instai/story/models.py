from __future__ import annotations

from django.db import models

from . import states


class Series(models.Model):
    page = models.ForeignKey("pages.ContentPage", related_name="series", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    premise = models.TextField(blank=True, default="")
    branch_point = models.TextField(blank=True, default="")          # What-If: the event that goes differently
    alternative_timeline = models.TextField(blank=True, default="")  # What-If: what the changed world looks like
    content_rules = models.JSONField(default=list, blank=True)
    is_fan_content = models.BooleanField(default=False)               # explicit owner mark; default is original / inspired-by
    franchise = models.CharField(max_length=160, blank=True, default="")
    target_episodes = models.IntegerField(default=5)
    status = models.CharField(max_length=12, default="draft")        # draft | planned | running | done
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "series"


class StoryArc(models.Model):
    series = models.ForeignKey(Series, related_name="arcs", on_delete=models.CASCADE)
    index = models.IntegerField(default=1)
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, default="")
    goal = models.TextField(blank=True, default="")
    cliffhanger = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["series_id", "index"]
        unique_together = [("series", "index")]


class Episode(models.Model):
    series = models.ForeignKey(Series, related_name="episodes", on_delete=models.CASCADE)
    arc = models.ForeignKey(StoryArc, null=True, blank=True, on_delete=models.SET_NULL, related_name="episodes")
    number = models.IntegerField(default=1)
    title = models.CharField(max_length=200)
    logline = models.TextField(blank=True, default="")
    goal = models.TextField(blank=True, default="")
    cliffhanger = models.TextField(blank=True, default="")
    duration_sec = models.IntegerField(default=45)
    state = models.CharField(max_length=20, choices=states.CHOICES, default=states.DRAFT)
    failed_state = models.CharField(max_length=20, blank=True, default="")  # where it was when it failed (retry resumes there)
    error = models.TextField(blank=True, default="")
    script = models.JSONField(default=dict, blank=True)       # {title, hook, language, blocks:[{id,speaker,text,emotion}], cta}
    script_checks = models.JSONField(default=dict, blank=True)
    estimate = models.JSONField(default=dict, blank=True)     # cached cost estimate
    qc = models.JSONField(default=dict, blank=True)           # last quality-check report
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["series_id", "number"]
        unique_together = [("series", "number")]


class EpisodeEvent(models.Model):
    """Audit trail of state transitions (episode history)."""

    episode = models.ForeignKey(Episode, related_name="events", on_delete=models.CASCADE)
    from_state = models.CharField(max_length=20)
    to_state = models.CharField(max_length=20)
    reason = models.CharField(max_length=300, blank=True, default="")
    actor = models.CharField(max_length=40, default="user")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class EpisodeVersion(models.Model):
    """Snapshot of script or storyboard before it is replaced (version history)."""

    episode = models.ForeignKey(Episode, related_name="versions", on_delete=models.CASCADE)
    kind = models.CharField(max_length=12)  # script | storyboard
    data = models.JSONField(default=dict)
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class Scene(models.Model):
    episode = models.ForeignKey(Episode, related_name="scenes", on_delete=models.CASCADE)
    index = models.IntegerField(default=1)
    title = models.CharField(max_length=200, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    location = models.CharField(max_length=200, blank=True, default="")
    characters = models.ManyToManyField("pages.Character", blank=True, related_name="scenes")
    approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["episode_id", "index"]
        unique_together = [("episode", "index")]


class Shot(models.Model):
    TECHNIQUES = [(t, t) for t in ["still_kenburns", "parallax_25d", "puppet_2d", "motion_graphics", "wan_i2v", "wan_flf",
                                   "talking_video", "three_d"]]
    scene = models.ForeignKey(Scene, related_name="shots", on_delete=models.CASCADE)
    index = models.IntegerField(default=1)
    description = models.TextField(blank=True, default="")
    image_prompt = models.TextField(blank=True, default="")
    negative_prompt = models.TextField(blank=True, default="")
    technique = models.CharField(max_length=20, choices=TECHNIQUES, default="still_kenburns")
    camera = models.JSONField(default=dict, blank=True)  # {move, intensity}
    duration_sec = models.FloatField(default=4.0)
    narration = models.TextField(blank=True, default="")
    speaker = models.CharField(max_length=120, blank=True, default="")
    sfx = models.CharField(max_length=300, blank=True, default="")
    transition = models.CharField(max_length=20, blank=True, default="cut")
    seed = models.BigIntegerField(null=True, blank=True)
    est_gpu_seconds = models.FloatField(default=0)
    approved = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default="draft")  # draft | ready | generating | done | failed
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["scene_id", "index"]
        unique_together = [("scene", "index")]


class StoryMemory(models.Model):
    """One per series. Continuity never relies on chat history: everything established lives in typed entries."""

    series = models.OneToOneField(Series, related_name="memory", on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)


class StoryMemoryEntry(models.Model):
    KINDS = [("fact", "fact"), ("character_state", "character_state"), ("relationship", "relationship"),
             ("timeline", "timeline"), ("open_thread", "open_thread"), ("episode_summary", "episode_summary"),
             ("future_goal", "future_goal")]
    memory = models.ForeignKey(StoryMemory, related_name="entries", on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, choices=KINDS)
    subject = models.CharField(max_length=200, blank=True, default="")  # character name / pair / when
    text = models.TextField()
    status = models.CharField(max_length=10, default="active")  # active | resolved (open threads) | superseded
    episode = models.ForeignKey(Episode, null=True, blank=True, on_delete=models.SET_NULL, related_name="memory_entries")
    key = models.CharField(max_length=64, blank=True, default="")  # hash for de-duplication
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["memory", "kind", "status"])]


class Source(models.Model):
    """Research reference. `verified` is True only when the system itself fetched the text (never for model-proposed links)."""

    STANCES = [("established", "established"), ("contested", "contested"), ("speculative", "speculative"),
               ("unsupported", "unsupported")]
    page = models.ForeignKey("pages.ContentPage", related_name="sources", on_delete=models.CASCADE)
    series = models.ForeignKey(Series, null=True, blank=True, on_delete=models.SET_NULL, related_name="sources")
    episode = models.ForeignKey(Episode, null=True, blank=True, on_delete=models.SET_NULL, related_name="sources")
    title = models.CharField(max_length=300)
    url = models.URLField(max_length=600, blank=True, default="")
    publisher = models.CharField(max_length=200, blank=True, default="")
    extract = models.TextField(blank=True, default="")
    claim = models.TextField(blank=True, default="")
    stance = models.CharField(max_length=12, choices=STANCES, default="established")
    verified = models.BooleanField(default=False)
    added_by = models.CharField(max_length=10, default="user")  # user | system | model
    notes = models.TextField(blank=True, default="")
    retrieved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
