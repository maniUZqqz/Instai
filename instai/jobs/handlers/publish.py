from __future__ import annotations

from instai.jobs.registry import handler


@handler("publish.export", resource="cpu", timeout=1800)
def export(ctx):
    from instai.publishing import services

    return services.export_package(ctx.payload["publication_id"])
