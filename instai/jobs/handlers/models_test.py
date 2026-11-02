"""models.test: the one-press test of a model on the Models page (instai/core/model_tests.py)."""
from __future__ import annotations

from instai.core import model_tests
from instai.jobs.registry import handler


@handler("models.test", resource=model_tests.resource_for, timeout=3 * 3600)
def models_test(ctx):
    return model_tests.run(ctx, str(ctx.payload.get("id") or ""))
