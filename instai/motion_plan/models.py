"""The scene plan of a motion-graphics shot (or a stand-alone plan of the Remotion page) and its version history.

SOURCE: adapted from NMarketing:backend/apps/motion/models.py (MotionPlan, MotionPlanRev) @ motion v2: a plan belongs to a SHOT of an episode (or to nothing, when
it is made on the Remotion page), not to a store and a user.
"""
from __future__ import annotations

from django.db import models


class MotionPlan(models.Model):
    """The live plan. `spec` is always valid (it went through specs.normalize_spec); `cursor` is the number of the version it equals."""

    shot = models.ForeignKey("story.Shot", null=True, blank=True, related_name="motion_plans", on_delete=models.CASCADE)
    title = models.CharField(max_length=200, blank=True, default="")
    spec = models.JSONField(default=dict)
    cursor = models.IntegerField(default=1)
    origin = models.CharField(max_length=12, default="user")                # fallback | ai | user | page
    source_hash = models.CharField(max_length=40, blank=True, default="")   # the inputs a generated plan was written from (shots.inputs_hash); a changed hash re-writes an unedited plan
    qa = models.JSONField(default=dict, blank=True)                         # the report of the rule checks (qa.run_loop), for the version in `spec`
    critique = models.JSONField(default=dict, blank=True)                   # the state and the rounds of the visual critique
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]


class MotionPlanRev(models.Model):
    """One version of a plan: every change (the owner, the chat, the model, an automatic fix of the QA or of the critique) is one; undo and redo only move the cursor."""

    plan = models.ForeignKey(MotionPlan, related_name="revs", on_delete=models.CASCADE)
    n = models.IntegerField()
    spec = models.JSONField(default=dict)
    label = models.CharField(max_length=160, blank=True, default="")
    source = models.CharField(max_length=12, default="user")                # user | ai | chat | patch | qa | critique | import | undo | fallback
    ops = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["plan_id", "n"]
        unique_together = [("plan", "n")]
