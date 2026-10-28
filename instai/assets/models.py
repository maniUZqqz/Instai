from __future__ import annotations

from django.db import models


class Asset(models.Model):
    """A file with explicit metadata and provenance (which workflow, model, seed and prompt made it).

    Versions: regenerating creates a new row whose `parent` is the previous one; `is_current` marks the latest.
    """

    KINDS = [("image", "image"), ("audio", "audio"), ("video", "video"), ("subtitle", "subtitle"), ("text", "text"),
             ("package", "package"), ("other", "other")]
    ROLES = [("keyframe", "keyframe"), ("layer", "layer"), ("narration", "narration"), ("music", "music"), ("sfx", "sfx"),
             ("shot_clip", "shot_clip"), ("render_clip", "render_clip"), ("preview", "preview"), ("final", "final"), ("cover", "cover"), ("subtitles", "subtitles"),
             ("reference", "reference"), ("export", "export"), ("other", "other")]

    kind = models.CharField(max_length=10, choices=KINDS)
    role = models.CharField(max_length=14, choices=ROLES, default="other")
    path = models.CharField(max_length=500)  # relative to MEDIA_ROOT, forward slashes
    mime = models.CharField(max_length=80, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    # explicit media metadata
    duration_sec = models.FloatField(null=True, blank=True)
    fps = models.FloatField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    codec = models.CharField(max_length=40, blank=True, default="")
    loudness_lufs = models.FloatField(null=True, blank=True)
    # links (all optional)
    page = models.ForeignKey("pages.ContentPage", null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    episode = models.ForeignKey("story.Episode", null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    shot = models.ForeignKey("story.Shot", null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    # versions and provenance
    version = models.IntegerField(default=1)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    is_current = models.BooleanField(default=True)
    approved = models.BooleanField(default=False)
    input_hash = models.CharField(max_length=64, blank=True, default="")  # hash of the inputs that produced it (staleness check)
    provenance = models.JSONField(default=dict, blank=True)  # {workflow, workflow_version, model, seed, prompt, provider, job_id, ...}
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["shot", "role", "is_current"]), models.Index(fields=["episode", "role", "is_current"])]

    @property
    def url(self) -> str:
        return "/media/" + self.path
