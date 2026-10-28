"""Episode state machine with explicit transitions (brief section 5):

draft -> planned -> scripting -> script_review -> storyboarding -> asset_generation -> animation -> assembly ->
quality_review -> ready_for_approval -> approved -> scheduled -> published   (+ failed / cancelled)

Rules: one step forward at a time (`animation` may be skipped when no shot needs video); any earlier editing state may be
re-entered (rework - assets stay and are flagged stale by input hash, so only what changed is regenerated);
any live state can fail or be cancelled; failed resumes where it stopped; cancelled restarts from draft.
"""
from __future__ import annotations

DRAFT, PLANNED, SCRIPTING, SCRIPT_REVIEW, STORYBOARDING = "draft", "planned", "scripting", "script_review", "storyboarding"
ASSET_GENERATION, ANIMATION, ASSEMBLY = "asset_generation", "animation", "assembly"
QUALITY_REVIEW, READY_FOR_APPROVAL, APPROVED = "quality_review", "ready_for_approval", "approved"
SCHEDULED, PUBLISHED, FAILED, CANCELLED = "scheduled", "published", "failed", "cancelled"

ORDER = [DRAFT, PLANNED, SCRIPTING, SCRIPT_REVIEW, STORYBOARDING, ASSET_GENERATION, ANIMATION, ASSEMBLY, QUALITY_REVIEW,
         READY_FOR_APPROVAL, APPROVED, SCHEDULED, PUBLISHED]
CHOICES = [(s, s) for s in ORDER + [FAILED, CANCELLED]]
REWORK_FROM = {SCRIPT_REVIEW, STORYBOARDING, ASSET_GENERATION, ANIMATION, ASSEMBLY, QUALITY_REVIEW, READY_FOR_APPROVAL}
REWORK_TO_MIN = ORDER.index(SCRIPT_REVIEW)
TERMINAL = {PUBLISHED}

LABELS_FA = {
    DRAFT: "پیش‌نویس", PLANNED: "برنامه‌ریزی‌شده", SCRIPTING: "در حال نوشتن فیلم‌نامه", SCRIPT_REVIEW: "بازبینی فیلم‌نامه",
    STORYBOARDING: "استوری‌بورد", ASSET_GENERATION: "ساخت تصویر و صدا", ANIMATION: "انیمیشن", ASSEMBLY: "مونتاژ",
    QUALITY_REVIEW: "بازبینی کیفیت", READY_FOR_APPROVAL: "آماده‌ی تأیید", APPROVED: "تأییدشده", SCHEDULED: "زمان‌بندی‌شده",
    PUBLISHED: "منتشرشده", FAILED: "ناموفق", CANCELLED: "لغوشده",
}


def idx(state: str) -> int:
    return ORDER.index(state)


def allowed_next(state: str, failed_state: str = "") -> list[str]:
    out: list[str] = []
    if state == FAILED:
        return [failed_state] if failed_state else [DRAFT]
    if state == CANCELLED:
        return [DRAFT]
    if state in TERMINAL or state not in ORDER:
        return out
    i = idx(state)
    if i + 1 < len(ORDER):
        out.append(ORDER[i + 1])
    if state == ASSET_GENERATION:
        out.append(ASSEMBLY)  # still-only episodes have nothing to animate
    if state == SCRIPT_REVIEW:
        out.append(SCRIPTING)  # regenerate the script
    if state in REWORK_FROM or state in (APPROVED, SCHEDULED):
        lo = REWORK_TO_MIN if state in REWORK_FROM else idx(READY_FOR_APPROVAL)
        out += [s for s in ORDER[lo:i]]
    out += [FAILED, CANCELLED]
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def can_transition(frm: str, to: str, failed_state: str = "") -> bool:
    return to in allowed_next(frm, failed_state)
