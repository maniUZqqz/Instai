from __future__ import annotations

from django.db import models


class CharacterLock(models.Model):
    """The identity of one character, fixed once and reused in every shot, picture and clip.

    `status = locked` means the owner approved the reference set. Everything that makes a picture of the character reads this row:
    the English identity `anchor`, the `palette` (colour key), the identity `seed`, the approved sheets (CharacterReference ids in `refs`),
    an approved LoRA, and - for characters drawn by code - the stick spec. `version` grows each time the locked data changes, and
    the keyframe hash includes it, so a changed lock regenerates only the pictures that show that character.
    """

    STATUS = [("draft", "draft"), ("locked", "locked")]
    STRATEGIES = [("auto", "auto"), ("stick_rig", "stick_rig"), ("multiref_edit", "multiref_edit"), ("sheet_edit", "sheet_edit"), ("lora", "lora"),
                  ("anchor_seed", "anchor_seed")]
    character = models.OneToOneField("pages.Character", related_name="lock", on_delete=models.CASCADE)
    status = models.CharField(max_length=8, choices=STATUS, default="draft")
    version = models.IntegerField(default=1)
    strategy = models.CharField(max_length=14, choices=STRATEGIES, default="auto")
    anchor = models.TextField(blank=True, default="")
    avoid = models.TextField(blank=True, default="")
    seed = models.BigIntegerField(default=0)
    palette = models.JSONField(default=list, blank=True)              # [{role, hex, name}]
    style_key = models.CharField(max_length=64, blank=True, default="")
    refs = models.JSONField(default=dict, blank=True)                 # {"sheet": reference id, "expressions": reference id}
    signature = models.JSONField(default=dict, blank=True)            # {"hist": [floats], "reference": id} embedding of the approved sheet
    stick = models.JSONField(default=dict, blank=True)                # stick-figure spec (instai.render.stick.spec) when drawn by code
    source = models.CharField(max_length=10, default="manual")        # manual | stick | image
    notes = models.TextField(blank=True, default="")
    locked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["character_id"]


class ConsistencyCheck(models.Model):
    """One consistency check of a picture against its character's locked identity (kept as history; the newest per shot+character counts)."""

    character = models.ForeignKey("pages.Character", related_name="consistency_checks", on_delete=models.CASCADE)
    shot = models.ForeignKey("story.Shot", null=True, blank=True, related_name="consistency_checks", on_delete=models.CASCADE)
    asset = models.ForeignKey("assets.Asset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    lock_version = models.IntegerField(default=0)
    palette_score = models.FloatField(null=True, blank=True)
    structure_score = models.FloatField(null=True, blank=True)
    vision_score = models.FloatField(null=True, blank=True)
    method = models.CharField(max_length=40, default="palette+structure")
    ok = models.BooleanField(default=True)
    notes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["shot", "character"])]
