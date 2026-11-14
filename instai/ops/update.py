"""«نسخهٔ تازه آماده است»: is a newer InstAI on GitHub, and a button that installs it (audit 2026-11-14).

START.bat updates only at the start. With autostart the server runs for days, so the owner never saw a new version. Now:

* `check()` asks GitHub (the commit of main through the small API call, the `VERSION` file as a second way; no download), remembers the answer
  for six hours in `data/update-status.json`, and says whether a newer version exists. The worker's 30-second upkeep refreshes it once in the
  idle night window; the badge in the top bar reads it through `GET /api/update/status`.
* `apply()` starts a detached helper (`scripts/apply_update.py`) that waits until no job runs, stops the server and the worker, runs
  `scripts/self_update.py` (the careful updater: backup, rollback, protected folders) and starts everything again.

The updater itself is `scripts/self_update.py` (stdlib only, shared with START.bat); this module only reads its settings and state.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from instai import version as ver
from instai.core.errors import DomainError

ROOT = Path(__file__).resolve().parents[2]
TTL_SEC = 6 * 3600                    # how long an answer is trusted
NIGHT_WINDOW = "02:00-07:00"          # the idle night window in which the worker refreshes the answer by itself
_module = None


def _su():
    """`scripts/self_update.py` as a module (it is a script, not a package)."""
    global _module
    if _module is None:
        spec = importlib.util.spec_from_file_location("instai_self_update", ROOT / "scripts" / "self_update.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)                      # type: ignore[union-attr]
        _module = mod
    return _module


def _file() -> Path:
    return Path(settings.DATA_DIR) / "update-status.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> None:
    try:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _file())
    except OSError:
        pass


def disabled() -> bool:
    su = _su()
    if os.environ.get("INSTAI_TESTING") == "1" and os.environ.get("INSTAI_UPDATE_IN_TESTS") != "1":
        return True                      # the test suite never asks GitHub (like the other "surprise" guards); the updater's own tests set INSTAI_UPDATE_IN_TESTS=1
    return su.setting("INSTAI_NO_UPDATE") in ("1", "true", "yes") or su.setting("INSTAI_AUTO_UPDATE") in ("0", "false", "no")


def _remote() -> dict:
    """{"commit", "version"} of GitHub's main. Two small requests; either may fail (a blocked API still lets the raw file through)."""
    su = _su()
    repo, branch = su.setting("INSTAI_UPDATE_REPO", su.DEFAULT_REPO), su.setting("INSTAI_UPDATE_BRANCH", su.DEFAULT_BRANCH)
    commit = su.remote_commit(repo, branch)
    version = ""
    raw = su.setting("INSTAI_UPDATE_RAW", "https://raw.githubusercontent.com").rstrip("/")
    try:
        version = su.http_get(f"{raw}/{repo}/{branch}/VERSION", 10).decode("utf-8", "ignore").strip().splitlines()[0].strip()
    except Exception:  # noqa: BLE001
        pass
    return {"commit": commit, "version": version}


def _decide(remote: dict, current: str, known_commit: str) -> bool:
    """Newer version number on GitHub; or the same-or-higher number with a commit this PC has never installed (only when this PC installed one before)."""
    su = _su()
    rv, cv = su.parse_version(remote.get("version") or ""), su.parse_version(current)
    if remote.get("version") and rv > cv:
        return True
    return bool(remote.get("commit") and known_commit and remote["commit"] != known_commit and rv >= cv and remote.get("version"))


def _applying(d: dict) -> bool:
    """An update was started in the last 30 minutes for THIS version (once the new version runs, it is over)."""
    ts = d.get("applying_ts")
    return bool(ts and time.time() - float(ts) < 1800 and d.get("current", ver.read_version()) == ver.read_version())


def _known_commit() -> str:
    try:
        return str(_su().load_state().get("commit") or "")
    except Exception:  # noqa: BLE001
        return ""


def running_jobs() -> int:
    from instai.jobs.models import Job

    return Job.objects.filter(status=Job.RUNNING).count()


def _shape(d: dict) -> dict:
    return {"available": bool(d.get("available")), "current": ver.read_version(), "latest": d.get("latest") or "", "checked_at": d.get("checked_at") or None,
            "error": d.get("error") or "", "disabled": bool(d.get("disabled")), "running_jobs": running_jobs(), "applying": _applying(d)}


def check(force: bool = False) -> dict:
    """The update status, from the six-hour memory unless `force`. Never raises: an unreachable GitHub is `error`, not a crash."""
    old = _read()
    if disabled():
        return _shape({"disabled": True})
    age = time.time() - float(old.get("checked_ts") or 0)
    if not force and old and age < TTL_SEC and old.get("current") == ver.read_version():
        return _shape(old)
    if force and old and age < 20:                                     # a button pressed twice must not ask GitHub twice
        return _shape(old)
    try:
        remote = _remote()
        err = "" if (remote.get("commit") or remote.get("version")) else "unreachable"
    except Exception as e:  # noqa: BLE001
        remote, err = {}, f"{type(e).__name__}"
    known = _known_commit()
    d = {"available": (not err) and _decide(remote, ver.read_version(), known), "latest": remote.get("version") or "", "error": err,
         "checked_at": timezone.now().isoformat(), "checked_ts": time.time(), "current": ver.read_version(), "applying_ts": old.get("applying_ts")}
    if err and old and old.get("current") == ver.read_version():       # keep the last good answer when GitHub cannot be reached right now
        d.update({"available": old.get("available", False), "latest": old.get("latest", "")})
    _write(d)
    return _shape(d)


def in_night_window(now: datetime | None = None) -> bool:
    from instai.jobs import schedule

    try:
        return schedule.in_window(schedule.config().get("download_window") or NIGHT_WINDOW, now or timezone.now())
    except Exception:  # noqa: BLE001
        return schedule.in_window(NIGHT_WINDOW, now or timezone.now())


def night_check() -> bool:
    """The worker's upkeep step: in the idle night window (no job running) refresh the answer once. True when it asked GitHub."""
    if disabled() or not in_night_window() or running_jobs():
        return False
    old = _read()
    if old and time.time() - float(old.get("checked_ts") or 0) < TTL_SEC:
        return False
    check(force=True)
    return True


# ------------------------------------------------------------------ the button

def _spawn(cmd: list[str]) -> None:
    """Start the helper so that it survives the server being stopped (on Windows through `cmd /c start`: its parent is a process that is already
    gone, so `taskkill /t` of the server window cannot reach it)."""
    if sys.platform.startswith("win"):
        subprocess.Popen(["cmd", "/c", "start", "", "/min", *cmd], cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
    else:
        subprocess.Popen(cmd, cwd=str(ROOT), start_new_session=True, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apply(force: bool = False) -> dict:
    """«به‌روزرسانی و راه‌اندازی دوباره»: only when a newer version exists and no job runs (unless `force`)."""
    st = check(force=True)
    if st["disabled"]:
        raise DomainError("conflict", "به‌روزرسانی خودکار خاموش است (INSTAI_NO_UPDATE).", message_en="Automatic update is switched off.")
    if not st["available"]:
        raise DomainError("conflict", "نسخهٔ تازه‌ای پیدا نشد.", message_en="No newer version was found.")
    if st["running_jobs"] and not force:
        raise DomainError("conflict", f"هنوز {st['running_jobs']} کار در حال اجراست؛ بعد از پایانشان دوباره بزنید، یا «با وجود کارهای در حال اجرا» را انتخاب کنید.",
                          details={"running_jobs": st["running_jobs"]}, message_en=f"{st['running_jobs']} job(s) are still running; try again when they end, or choose to update anyway.")
    d = _read()
    d["applying_ts"] = time.time()
    _write(d)
    cmd = [sys.executable, str(ROOT / "scripts" / "apply_update.py")] + ([] if force else ["--wait-idle"])
    _spawn(cmd)
    return {**st, "applying": True}
