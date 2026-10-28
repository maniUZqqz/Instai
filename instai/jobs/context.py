"""What a handler sees: progress, logs, cancellation/timeout checkpoints, cancellable subprocesses and GPU accounting."""
from __future__ import annotations

import subprocess
import time
from typing import Callable

from . import queue
from .models import Job


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass


class JobContext:
    def __init__(self, job: Job, worker: str = "inline", lease_sec: int = 90):
        self.job = job
        self.worker = worker
        self.lease_sec = lease_sec
        self.payload = job.payload or {}
        self.deadline = time.time() + job.timeout_sec
        self.gpu_seconds = 0.0
        self.vram_peak_mb = 0
        self._last_progress = 0.0

    # ---- checkpoints
    def check(self) -> None:
        if queue.is_cancel_requested(self.job.pk):
            raise JobCancelled()
        if time.time() > self.deadline:
            raise JobTimeout(f"job exceeded its timeout of {self.job.timeout_sec}s")

    def sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(min(0.5, max(0.0, end - time.time())))
            self.check()

    # ---- reporting
    def progress(self, fraction: float, text: str = "") -> None:
        now = time.time()
        if now - self._last_progress > 0.3 or fraction >= 1.0:
            self._last_progress = now
            queue.set_progress(self.job, fraction, text)
        queue.heartbeat(self.job, self.worker, self.lease_sec)

    def log(self, message: str, level: str = "info") -> None:
        queue.log_job(self.job, message, level)

    def waiting(self, reason: str) -> None:
        queue.set_waiting(self.job, reason)
        queue.heartbeat(self.job, self.worker, self.lease_sec)

    def add_gpu_seconds(self, seconds: float, vram_peak_mb: int = 0) -> None:
        self.gpu_seconds += seconds
        self.vram_peak_mb = max(self.vram_peak_mb, vram_peak_mb)

    # ---- helpers
    def run_cmd(self, cmd: list[str], *, cwd: str | None = None, on_line: Callable[[str], None] | None = None,
                timeout: float | None = None) -> tuple[int, str]:
        """Run a subprocess that stays cancellable: killed on cancel/timeout. Returns (returncode, combined output tail)."""
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             creationflags=flags)
        import threading

        tail: list[str] = []

        def reader():
            for line in p.stdout:  # type: ignore[union-attr]
                tail.append(line.rstrip())
                del tail[:-60]
                if on_line:
                    try:
                        on_line(line.rstrip())
                    except Exception:  # noqa: BLE001
                        pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        end = time.time() + (timeout or 10 ** 9)
        try:
            while p.poll() is None:
                time.sleep(0.25)
                self.check()
                if time.time() > end:
                    raise JobTimeout("command timed out")
        except BaseException:
            p.kill()
            raise
        finally:
            t.join(timeout=2)
        return p.returncode, "\n".join(tail)
