from __future__ import annotations

from instai.jobs.registry import handler


@handler("bench.run", resource="cpu", timeout=4 * 3600)
def run(ctx):
    from instai.core import benchmark
    from instai.core.models import BenchmarkRun

    return benchmark.run_benchmark(ctx, BenchmarkRun.objects.get(pk=ctx.payload["run_id"]))
