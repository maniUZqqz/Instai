"""Which human approvals a page demands, by automation level (brief: "human gates follow the page's automation level").

* manual    - every development step and every pre-production stage waits for an explicit human approval.
* assisted  - AI prepares everything; a human approves the series bible, the composition, the final development gate,
              the storyboard and the pre-production gate. Other steps pass by themselves once the AI result exists (and can still be edited).
* automatic - only the final gates (development approval, pre-production approval) wait for a human.

Nothing is ever published automatically, at any level (Phase 4 owns publishing and keeps it manual by default).
"""
from __future__ import annotations

DEV_REQUIRED = {
    "manual": None,  # None = every step
    "assisted": {"bible", "composition", "gate"},
    "automatic": {"gate"},
}
PREPROD_STAGES = ["script", "storyboard", "animatic", "design", "casting", "gate"]
PREPROD_REQUIRED = {
    "manual": set(PREPROD_STAGES),
    "assisted": {"storyboard", "gate"},
    "automatic": {"gate"},
}


def _level(page) -> str:
    return page.automation_level if page.automation_level in DEV_REQUIRED else "manual"


def dev_step_needs_human(page, step_kind: str) -> bool:
    req = DEV_REQUIRED[_level(page)]
    return True if req is None else step_kind in req


def preprod_stage_needs_human(page, stage: str) -> bool:
    return stage in PREPROD_REQUIRED[_level(page)]
