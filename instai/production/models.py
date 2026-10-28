"""Phase 3/4 production models. They live in this app and point at the story/pages models with foreign keys:
nothing here changes a model of the pages/story apps."""
from __future__ import annotations

from django.db import models


class CharacterRig(models.Model):
    """A 2D puppet rig of one character: layered parts (body, head, eyes, mouths, arms ...) with pivots and a z-order.
    `spec` is the JSON understood by `instai.render.puppet.rig.Rig` (image paths are relative to the media folder)."""

    SOURCES = [("demo", "demo"), ("flux_cutout", "flux_cutout"), ("upload", "upload"), ("psd", "psd")]
    character = models.ForeignKey("pages.Character", related_name="rigs", on_delete=models.CASCADE)
    version = models.IntegerField(default=1)
    name = models.CharField(max_length=120, blank=True, default="")
    source = models.CharField(max_length=12, choices=SOURCES, default="upload")
    spec = models.JSONField(default=dict, blank=True)
    sheet_asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["character_id", "-version"]
        unique_together = [("character", "version")]


class VoiceReference(models.Model):
    """A recording of a person's voice that may be cloned (MOSS-TTS speaks in the voice of a reference clip).
    Consent is stored verbatim with the recording; without it the reference is never used."""

    character = models.ForeignKey("pages.Character", related_name="voice_refs", on_delete=models.CASCADE)
    language = models.CharField(max_length=5, default="fa")
    label = models.CharField(max_length=120, blank=True, default="")
    person_name = models.CharField(max_length=160, blank=True, default="")
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    consent_given = models.BooleanField(default=False)
    consent_text = models.TextField(blank=True, default="")
    consented_at = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class VoiceCast(models.Model):
    """Which voice speaks for a character in a language (fa / en). Resolution order in the pipeline:
    VoiceCast(character, language) -> Character.voice -> the page's narration voice."""

    character = models.ForeignKey("pages.Character", related_name="voice_casts", on_delete=models.CASCADE)
    language = models.CharField(max_length=5, default="fa")
    engine = models.CharField(max_length=12, default="auto")      # auto | moss | piper | pocket | edge | fake
    voice_id = models.CharField(max_length=160, blank=True, default="")
    reference = models.ForeignKey(VoiceReference, null=True, blank=True, on_delete=models.SET_NULL, related_name="casts")
    speed = models.FloatField(default=1.0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("character", "language")]
        ordering = ["character_id", "language"]


class PageProductionConfig(models.Model):
    """Per-page production settings of Phase 3/4 (kept apart from the pages app profiles)."""

    page = models.OneToOneField("pages.ContentPage", related_name="production_config", on_delete=models.CASCADE)
    anime_model = models.CharField(max_length=20, default="wan22")        # wan22 | anisora | animegen (set by the comparison vote)
    default_technique = models.CharField(max_length=20, blank=True, default="")
    gpu_minutes_per_week = models.IntegerField(default=600)                # automation budget (GPU time)
    api_usd_per_week = models.FloatField(default=0.0)                      # automation budget (paid API calls)
    render_windows = models.JSONField(default=list, blank=True)            # [{"days": ["sat"], "start": "22:00", "end": "07:00"}]; [] = any time
    utc_offset_minutes = models.IntegerField(default=210)                  # local time for windows/schedule (Tehran = +03:30)
    auto_publish_enabled = models.BooleanField(default=False)              # NEVER true by default
    auto_publish_confirmed_at = models.DateTimeField(null=True, blank=True)
    music_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ShotRender(models.Model):
    """What happened when one shot was rendered by a non-trivial technique (puppet, Wan hero, first/last-frame, extension):
    where it ran, how long it took and the quality check against the character sheet."""

    STATUS = [(s, s) for s in ("queued", "running", "done", "failed")]
    shot = models.ForeignKey("story.Shot", related_name="renders", on_delete=models.CASCADE)
    technique = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=STATUS, default="queued")
    params = models.JSONField(default=dict, blank=True)
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    device = models.CharField(max_length=80, blank=True, default="")      # "local" or a worker name
    seconds = models.FloatField(null=True, blank=True)
    qc = models.JSONField(default=dict, blank=True)                       # {similarity, threshold, colour_delta, ok, notes[]}
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class CharacterLora(models.Model):
    """Optional per-character LoRA trained with ComfyUI's TrainLoraNode, with a measured before/after."""

    STATUS = [(s, s) for s in ("queued", "training", "trained", "failed")]
    character = models.ForeignKey("pages.Character", related_name="loras", on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS, default="queued")
    lora_file = models.CharField(max_length=300, blank=True, default="")  # file name inside ComfyUI models/loras
    params = models.JSONField(default=dict, blank=True)
    before = models.JSONField(default=dict, blank=True)                   # {similarity: mean over test prompts, per_prompt: []}
    after = models.JSONField(default=dict, blank=True)
    seconds = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class AnimeComparison(models.Model):
    """Same stills + same seeds through several anime-capable video models; the owner votes and the winner becomes the page default."""

    page = models.ForeignKey("pages.ContentPage", null=True, blank=True, related_name="anime_comparisons", on_delete=models.CASCADE)
    name = models.CharField(max_length=160, blank=True, default="")
    prompt = models.TextField(blank=True, default="")
    seeds = models.JSONField(default=list, blank=True)
    stills = models.JSONField(default=list, blank=True)                   # asset ids
    candidates = models.JSONField(default=list, blank=True)               # ["wan22", "anisora", "animegen"]
    status = models.CharField(max_length=10, default="draft")             # draft | running | done
    winner = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class ComparisonClip(models.Model):
    comparison = models.ForeignKey(AnimeComparison, related_name="clips", on_delete=models.CASCADE)
    still_index = models.IntegerField(default=0)
    seed = models.BigIntegerField(default=1)
    candidate = models.CharField(max_length=20)
    status = models.CharField(max_length=10, default="queued")            # queued | done | failed | skipped
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    seconds = models.FloatField(null=True, blank=True)
    device = models.CharField(max_length=80, blank=True, default="")
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["still_index", "candidate", "seed"]


class ComparisonVote(models.Model):
    comparison = models.ForeignKey(AnimeComparison, related_name="votes", on_delete=models.CASCADE)
    still_index = models.IntegerField(null=True, blank=True)
    candidate = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)


class MixTrack(models.Model):
    """One music / SFX / ambience track on an episode timeline (generated by ACE-Step / MOSS-SoundEffect or imported)."""

    KINDS = [("music", "music"), ("sfx", "sfx"), ("ambience", "ambience")]
    episode = models.ForeignKey("story.Episode", related_name="mix_tracks", on_delete=models.CASCADE)
    shot = models.ForeignKey("story.Shot", null=True, blank=True, on_delete=models.SET_NULL, related_name="mix_tracks")
    kind = models.CharField(max_length=10, choices=KINDS)
    label = models.CharField(max_length=160, blank=True, default="")
    prompt = models.TextField(blank=True, default="")                     # English description for the generator
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    start_sec = models.FloatField(default=0.0)
    end_sec = models.FloatField(null=True, blank=True)                    # None = until the end of the episode / the clip's own length
    gain_db = models.FloatField(default=-18.0)
    duck = models.BooleanField(default=True)                              # lower under dialogue (side-chain)
    fade_in = models.FloatField(default=0.5)
    fade_out = models.FloatField(default=1.0)
    status = models.CharField(max_length=12, default="planned")           # planned | generating | ready | failed
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["episode_id", "start_sec", "id"]


class Retake(models.Model):
    """Regenerate a time range of a rendered episode (first/last-frame Wan + seamless stitch + audio replace/mute/cut)."""

    AUDIO = [("keep", "keep"), ("replace", "replace"), ("mute", "mute"), ("cut", "cut")]
    episode = models.ForeignKey("story.Episode", related_name="video_retakes", on_delete=models.CASCADE)
    source_asset = models.ForeignKey("assets.Asset", related_name="+", on_delete=models.CASCADE)
    start_sec = models.FloatField()
    end_sec = models.FloatField()
    prompt = models.TextField(blank=True, default="")
    audio_mode = models.CharField(max_length=8, choices=AUDIO, default="keep")
    status = models.CharField(max_length=10, default="queued")            # queued | running | done | failed
    result_asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    seam = models.JSONField(default=dict, blank=True)                     # {colour_gain, blend_frames, duration_error}
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
