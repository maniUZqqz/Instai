from __future__ import annotations

from django.db import models

from . import formats, profiles


class SettingsProfile(models.Model):
    """A reusable settings bundle of one kind. `is_template` profiles (page=None) are copied onto pages, never shared live."""

    KIND_CHOICES = [(k, k) for k in profiles.KINDS]
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    name = models.CharField(max_length=120, blank=True, default="")
    data = models.JSONField(default=dict)
    is_template = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "name", "id"]

    def save(self, *args, **kwargs):
        self.data = profiles.normalize(self.kind, self.data)
        super().save(*args, **kwargs)


class ContentPage(models.Model):
    """A content page (e.g. an Instagram page). Detailed settings live in six SettingsProfile rows."""

    AUTOMATION = [("manual", "manual"), ("assisted", "assisted"), ("automatic", "automatic")]
    STATUS = [("active", "active"), ("archived", "archived")]

    name = models.CharField(max_length=160)
    handle = models.CharField(max_length=120, blank=True, default="")
    format = models.CharField(max_length=24, choices=formats.choices(), default=formats.ANIME)
    languages = models.JSONField(default=list)  # content languages, e.g. ["fa"], ["en"], ["fa", "en"]; the first one is the primary
    template_key = models.CharField(max_length=64, blank=True, default="")  # development template; empty = the format's own template
    idea = models.TextField(blank=True, default="")
    automation_level = models.CharField(max_length=12, choices=AUTOMATION, default="manual")
    status = models.CharField(max_length=10, choices=STATUS, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    identity_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    strategy_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    visual_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    audio_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    production_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    publishing_profile = models.ForeignKey(SettingsProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return self.name

    @property
    def language(self) -> str:
        return (self.languages or ["fa"])[0]

    def profile(self, kind: str) -> dict:
        p = getattr(self, f"{kind}_profile")
        return profiles.normalize(kind, p.data if p else None)

    def set_profile(self, kind: str, data: dict | None, name: str = "") -> SettingsProfile:
        """Create or update this page's own profile row of `kind` (never edits a profile another page uses)."""
        p = getattr(self, f"{kind}_profile")
        if p is None or p.is_template:
            p = SettingsProfile(kind=kind, name=name or f"{self.name} - {kind}")
        merged = {**(p.data or {}), **(data or {})}
        p.data = merged
        p.save()
        setattr(self, f"{kind}_profile", p)
        self.save(update_fields=[f"{kind}_profile", "updated_at"])
        return p

    def ensure_profiles(self) -> None:
        for kind in profiles.KINDS:
            if getattr(self, f"{kind}_profile") is None:
                self.set_profile(kind, {})


class Character(models.Model):
    page = models.ForeignKey(ContentPage, related_name="characters", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, blank=True, default="")
    profile = models.TextField(blank=True, default="")
    personality = models.TextField(blank=True, default="")
    appearance = models.TextField(blank=True, default="")
    abilities = models.TextField(blank=True, default="")
    motivations = models.TextField(blank=True, default="")
    voice = models.JSONField(default=dict, blank=True)  # {engine, voice_id, reference_asset, language}
    is_original = models.BooleanField(default=True)
    franchise = models.CharField(max_length=160, blank=True, default="")  # only for fan content
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name


class CharacterReference(models.Model):
    KINDS = [("sheet", "sheet"), ("image", "image"), ("lora", "lora"), ("pose", "pose"), ("expression", "expression"),
             ("voice", "voice")]
    character = models.ForeignKey(Character, related_name="references", on_delete=models.CASCADE)
    kind = models.CharField(max_length=12, choices=KINDS, default="image")
    label = models.CharField(max_length=120, blank=True, default="")
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
