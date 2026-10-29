"""Install optional model/tool packs from the Settings page: runs scripts/download_models.py and streams its output."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from instai.jobs.registry import handler

ROOT = Path(__file__).resolve().parents[3]
_PCT = re.compile(r"(\d+(?:\.\d+)?)%")


@handler("downloads.run", resource="net", timeout=24 * 3600)
def run(ctx):
    packages = [p for p in ctx.payload.get("packages", []) if re.fullmatch(r"[\w.:-]+", p)]   # package ids or single item ids
    if not packages:
        return {"installed": []}
    cmd = [sys.executable, str(ROOT / "scripts" / "download_models.py"), "--only", ",".join(packages), "--yes"]
    ctx.log("running: download_models --only " + ",".join(packages))

    def on_line(line: str) -> None:
        if line.strip():
            ctx.log(line[:300])
        m = _PCT.search(line)
        if m:
            ctx.progress(float(m.group(1)) / 100, line.strip()[:120])

    rc, tail = ctx.run_cmd(cmd, cwd=str(ROOT), on_line=on_line, timeout=24 * 3600)
    try:                      # what is installed now (both processes pick the new data/discovery.json up)
        from instai.core import model_status

        model_status.current(force=True)
    except Exception:  # noqa: BLE001
        pass
    if rc != 0:
        from instai.providers.base import ProviderError

        raise ProviderError("دانلود کامل نشد؛ جزئیات در گزارش کار است. دوباره امتحان کنید (ادامه از همان‌جا).", retryable=True)
    return {"installed": packages}
