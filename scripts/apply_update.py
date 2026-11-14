#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InstAI «به‌روزرسانی و راه‌اندازی دوباره»: the detached helper the update button starts (instai/ops/update.py).

  1. waits until no job runs (--wait-idle; up to 10 minutes, then goes on anyway: the queue re-queues what was running),
  2. stops the server and the worker (the same as STOP.bat),
  3. runs scripts/self_update.py (backup, rollback, protected folders),
  4. starts InstAI again without opening a browser (scripts/START-AUTO.bat), so the open page only has to reload.

Python standard library only; console text is English / ASCII; everything is also written to data/logs/update-apply.log.
Exit code 0 = started again, 1 = a step failed (the old version is back; the log says which).
`--dry-run` prints the steps without doing anything (tests).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = sys.platform.startswith("win")


def log(msg: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    try:
        d = os.path.join(ROOT, "data", "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "update-apply.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def env_value(name: str, default: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8-sig") as f:
            for raw in f:
                k, _, v = raw.strip().partition("=")
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def base_url() -> str:
    host = env_value("INSTAI_HOST", "127.0.0.1")
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{env_value('INSTAI_PORT', '8765')}"


def running_jobs() -> int:
    """Jobs running right now (-1 = the server does not answer)."""
    try:
        with urllib.request.urlopen(base_url() + "/api/queue/summary", timeout=3) as r:
            return int(json.loads(r.read().decode("utf-8")).get("running", 0))
    except Exception:  # noqa: BLE001
        return -1


def run(cmd: list[str], dry: bool, env: dict | None = None) -> int:
    log("run: " + " ".join(cmd))
    if dry:
        return 0
    return subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})}).returncode


def steps(py: str) -> list[tuple[str, list[str], dict]]:
    """(label, command, extra environment) of the stop / update / start steps."""
    quiet = {"INSTAI_NO_PAUSE": "1", "INSTAI_NO_BROWSER": "1"}
    if WINDOWS:
        return [("stop", ["cmd", "/c", "STOP.bat"], quiet),
                ("update", [py, os.path.join("scripts", "self_update.py")], {}),
                ("start", ["cmd", "/c", os.path.join("scripts", "START-AUTO.bat")], quiet)]
    return [("update", [py, os.path.join("scripts", "self_update.py")], {})]      # no windows to close or open outside Windows (a developer checkout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="InstAI: stop, update, start again")
    ap.add_argument("--wait-idle", action="store_true", help="wait (up to 10 minutes) until no job runs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    py = sys.executable
    log("update helper started" + (" (dry run)" if args.dry_run else ""))
    if args.wait_idle and not args.dry_run:
        end = time.time() + 600
        while time.time() < end:
            n = running_jobs()
            if n <= 0:
                break
            log(f"{n} job(s) still running; waiting")
            time.sleep(10)
    time.sleep(0 if args.dry_run else 2)                 # let the answer of the button reach the browser first
    for label, cmd, extra in steps(py):
        rc = run(cmd, args.dry_run, extra)
        if label == "update" and rc not in (0, 10):
            log(f"the update step failed (exit {rc}); the old version is kept; starting again")
        elif rc != 0 and label != "update":
            log(f"step {label} ended with exit {rc}")
    log("update helper finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
