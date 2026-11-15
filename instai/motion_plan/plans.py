"""The live plan and its version history: every change (the owner, the chat, the model, an automatic fix of the QA or of the critique) is one version;
undo and redo only move the cursor.

SOURCE: ported from NMarketing:backend/apps/motion/plans.py @ motion v2, adapted for InstAI: a plan belongs to a shot (or to nothing), not to a store and a user;
summaries carry Persian and English text.

Rules: an edit after an undo throws the «ahead» branch away (as in any editor), at most 60 versions are kept, and every change goes through
specs.normalize_spec, so the saved plan is always valid. The honesty rule is applied here too: the sources a number may name are the VERIFIED sources of the
shot's episode.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from . import patch as patch_mod
from . import specs
from .models import MotionPlan, MotionPlanRev

MAX_REVS = 60
SOURCES = ("user", "ai", "chat", "patch", "qa", "critique", "import", "undo", "fallback")


class PlanError(ValueError):
    """`str(e)` is Persian, `e.en` the English text."""

    def __init__(self, fa: str, en: str = ""):
        super().__init__(fa)
        self.fa = fa
        self.en = en or fa


def verified_sources(plan: MotionPlan):
    """The titles a number on screen may name (None = the plan is not tied to an episode: the owner's own source text is trusted)."""
    if plan.shot_id is None:
        return None
    try:
        ep = plan.shot.scene.episode
        return [s.title for s in ep.sources.all() if s.verified]
    except Exception:  # noqa: BLE001
        return []


def _clean(plan: MotionPlan | None, spec: dict, notes=None) -> dict:
    try:
        out = specs.normalize_spec(spec, max_total=specs.MAX_TOTAL_S, notes=notes, allowed_sources=verified_sources(plan) if plan is not None else None)
    except specs.SpecError as exc:
        raise PlanError(str(exc), exc.en) from exc
    out.pop("total_s", None)
    return out


def _title_of(spec: dict) -> str:
    sc = spec["scenes"][0]
    return str(sc.get("title") or sc.get("name") or sc.get("text") or sc.get("caption") or "Scene plan")[:80]


@transaction.atomic
def create(spec: dict, *, shot=None, title: str = "", origin: str = "user", source: str = "user", label: str = "Version 1") -> MotionPlan:
    plan = MotionPlan(shot=shot, title="", spec={}, origin=origin, cursor=1)
    clean = _clean(plan if shot is not None else None, spec)
    plan.spec, plan.title = clean, (title or _title_of(clean))[:200]
    plan.save()
    MotionPlanRev.objects.create(plan=plan, n=1, spec=clean, label=label[:160], source=source if source in SOURCES else "user")
    return plan


def _same(a: dict, b: dict) -> bool:
    f = lambda s: {k: v for k, v in s.items() if k not in ("total_s", "safe")}  # noqa: E731
    return f(a) == f(b)


@transaction.atomic
def commit(plan: MotionPlan, spec: dict, *, label: str = "", source: str = "user", ops: list | None = None, coalesce: bool = False) -> MotionPlan:
    """A new version; if the plan did not change nothing happens. `coalesce`: quick successive edits by the owner (less than 15 s apart) become ONE version
    (typing does not make a version of its own)."""
    plan = MotionPlan.objects.select_for_update().get(pk=plan.pk)
    clean = _clean(plan, spec)
    if _same(clean, plan.spec):
        return plan
    if coalesce and source == "user":
        last = MotionPlanRev.objects.filter(plan=plan, n=plan.cursor).first()
        if last is not None and last.source == "user" and last.n > 1 and (timezone.now() - last.created_at).total_seconds() < 15 \
                and not MotionPlanRev.objects.filter(plan=plan, n__gt=plan.cursor).exists():
            last.spec, last.created_at = clean, timezone.now()
            last.save(update_fields=["spec", "created_at"])
            plan.spec, plan.qa = clean, {}
            plan.save(update_fields=["spec", "qa", "updated_at"])
            return plan
    MotionPlanRev.objects.filter(plan=plan, n__gt=plan.cursor).delete()          # the «ahead» branch is thrown away
    n = plan.cursor + 1
    MotionPlanRev.objects.create(plan=plan, n=n, spec=clean, label=(label or "edit")[:160], source=source if source in SOURCES else "user", ops=ops or [])
    old = list(MotionPlanRev.objects.filter(plan=plan).order_by("n").values_list("pk", flat=True))
    if len(old) > MAX_REVS:
        MotionPlanRev.objects.filter(pk__in=old[: len(old) - MAX_REVS]).delete()
    plan.spec, plan.cursor = clean, n
    plan.qa = {}                      # the old report is not for this version any more
    plan.save(update_fields=["spec", "cursor", "qa", "updated_at"])
    return plan


def apply_ops(plan: MotionPlan, ops, *, label: str = "", source: str = "patch") -> tuple[MotionPlan, list]:
    """A patch => a new version. => (plan, the summary [{fa, en}] of what changed + the silent corrections)."""
    notes: list = []
    try:
        new = patch_mod.apply_patch(plan.spec, ops, notes=notes, allowed_sources=verified_sources(plan))
    except patch_mod.PatchError as exc:
        raise PlanError(str(exc), exc.en) from exc
    summary = patch_mod.diff_summary(plan.spec, new)
    text = patch_mod.diff_text(summary, "en")[:150]
    plan = commit(plan, new, label=label or text or "change", source=source, ops=ops if isinstance(ops, list) else [ops])
    return plan, summary + notes


def history(plan: MotionPlan) -> list:
    return [{"n": r.n, "label": r.label, "source": r.source, "current": r.n == plan.cursor, "created_at": r.created_at.isoformat(), "ops": r.ops}
            for r in MotionPlanRev.objects.filter(plan=plan).order_by("n")]


@transaction.atomic
def step(plan: MotionPlan, direction: int) -> MotionPlan:
    """direction -1 = undo, +1 = redo."""
    plan = MotionPlan.objects.select_for_update().get(pk=plan.pk)
    target = plan.cursor + (1 if direction > 0 else -1)
    rev = MotionPlanRev.objects.filter(plan=plan, n=target).first()
    if rev is None:
        raise PlanError("چیزی برای برگشتن نیست." if direction < 0 else "چیزی برای جلوتر رفتن نیست.", "There is nothing to undo." if direction < 0 else "There is nothing to redo.")
    plan.spec, plan.cursor, plan.qa = rev.spec, rev.n, {}
    plan.save(update_fields=["spec", "cursor", "qa", "updated_at"])
    return plan


@transaction.atomic
def restore(plan: MotionPlan, n: int) -> MotionPlan:
    rev = MotionPlanRev.objects.filter(plan=plan, n=n).first()
    if rev is None:
        raise PlanError("این نسخه پیدا نشد.", "This version was not found.")
    plan = MotionPlan.objects.select_for_update().get(pk=plan.pk)
    plan.spec, plan.cursor, plan.qa = rev.spec, rev.n, {}
    plan.save(update_fields=["spec", "cursor", "qa", "updated_at"])
    return plan


def can_undo(plan: MotionPlan) -> bool:
    return MotionPlanRev.objects.filter(plan=plan, n=plan.cursor - 1).exists()


def can_redo(plan: MotionPlan) -> bool:
    return MotionPlanRev.objects.filter(plan=plan, n=plan.cursor + 1).exists()


def plan_dict(plan: MotionPlan, *, with_history: bool = True) -> dict:
    from . import timeline

    spec = dict(plan.spec)
    spec["total_s"] = round(timeline.total_seconds(spec), 2) if spec.get("scenes") else 0
    d = {"id": plan.pk, "shot_id": plan.shot_id, "title": plan.title, "origin": plan.origin, "spec": spec, "rev": plan.cursor, "can_undo": can_undo(plan), "can_redo": can_redo(plan),
         "qa": plan.qa or {}, "critique": plan.critique or {}, "updated_at": plan.updated_at.isoformat(), "created_at": plan.created_at.isoformat()}
    if with_history:
        d["history"] = history(plan)
    return d
