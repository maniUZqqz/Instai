"""What a handler sees: progress, logs, cancellation/timeout checkpoints, cancellable subprocesses and GPU accounting."""
from __future__ import annotations

import subprocess
import threading
import time
from typing import Callable

from . import queue
from .models import Job

_LOCAL = threading.local()


def current() -> "JobContext | None":
    """The context of the job this thread is running (None outside a job: tests, scripts, the settings test button).
    Providers use it to report what they are doing (tokens so far, sampler step, model and device) without every call site passing it along."""
    return getattr(_LOCAL, "ctx", None)


def set_current(ctx: "JobContext | None") -> None:
    _LOCAL.ctx = ctx


def report_live(**fields) -> None:
    """ctx.live(...) of the running job; does nothing outside a job and never raises (reporting must not break the work)."""
    ctx = current()
    if ctx is not None:
        try:
            ctx.live(**fields)
        except Exception:  # noqa: BLE001
            pass


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass


class JobDeferred(Exception):
    """Raised by a handler (or `JobContext.check` at the end of a scheduled window) to say: this job cannot go on NOW but nothing is
    wrong - put it back in the queue. `run_after` is when to look again (None = soon, the queue's own pause); `count=False` marks a
    planned pause (the night window closed) rather than a broken thing. It never costs an attempt."""

    def __init__(self, reason: str, code: str = "scheduled", *, run_after=None, count: bool = True):
        super().__init__(reason)
        self.reason, self.code, self.run_after, self.count = reason, code, run_after, count


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
        self._live: dict = {}
        self._live_at = 0.0
        self._live_dirty = False
        self._live_lock = threading.Lock()

    # ---- checkpoints
    def check(self) -> None:
        if queue.is_cancel_requested(self.job.pk):
            raise JobCancelled()
        if time.time() > self.deadline:
            raise JobTimeout(f"job exceeded its timeout of {self.job.timeout_sec}s")
        if self.job.window:
            self._check_window()

    def _check_window(self) -> None:
        """A job that may only run inside a window (a scheduled download) stops cleanly when the window closes; it resumes at the next opening."""
        from . import schedule

        if not schedule.in_window(self.job.window):
            raise JobDeferred("بازهٔ شبانه تمام شد؛ ادامه از بازهٔ بعدی (از همان‌جا که مانده بود).", "window",
                              run_after=schedule.next_window_start(self.job.window), count=False)

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

    def live(self, force: bool = False, **fields) -> None:
        """Tell the queue screen what is happening right now: phase, model, device, gpu_pct, tokens, tps, step, steps, shot, shots ...
        A value of None removes a key. The database is written at most about once a second (a token stream calls this many times a
        second), except when the phase changes or `force` is set; `flush_live()` writes whatever is pending."""
        with self._live_lock:
            changed_phase = "phase" in fields and fields["phase"] != self._live.get("phase")
            for k, v in fields.items():
                if v is None:
                    self._live.pop(k, None)
                else:
                    self._live[k] = v
            now = time.time()
            if force or changed_phase or now - self._live_at >= 0.9:
                self._live_at, self._live_dirty = now, False
                snapshot = dict(self._live)
            else:
                self._live_dirty = True
                return
        queue.set_live(self.job, snapshot)

    def flush_live(self) -> None:
        with self._live_lock:
            if not self._live_dirty:
                return
            self._live_at, self._live_dirty = time.time(), False
            snapshot = dict(self._live)
        queue.set_live(self.job, snapshot)

    def live_value(self, key: str, default=None):
        return self._live.get(key, default)

    def add_gpu_seconds(self, seconds: float, vram_peak_mb: int = 0) -> None:
        self.gpu_seconds += seconds
        self.vram_peak_mb = max(self.vram_peak_mb, vram_peak_mb)

    # ---- helpers
    def run_cmd(self, cmd: list[str], *, cwd: str | None = None, on_line: Callable[[str], None] | None = None,
                timeout: float | None = None, env: dict | None = None) -> tuple[int, str]:
        """Run a subprocess that stays cancellable: killed on cancel/timeout. Returns (returncode, combined output tail)."""
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             creationflags=flags, env=env)
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
