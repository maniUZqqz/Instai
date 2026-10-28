"""GPU arbiter: one heavy job at a time, with explicit unloading when the occupant changes.

Adapted from the idea of Qasem processing-server/agent.py ServiceManager.prepare_for (Ollama keep_alive 0, ComfyUI /free, stop idle
voice servers). Rules from the brief:
  * never run an LLM, a ComfyUI video job and a voice model on the GPU together;
  * before a job unload what it does not need;
  * another program (e.g. the NMarketing agent) may use the GPU: detect busy VRAM with nvidia-smi, WAIT and show "GPU busy";
  * never kill another program's process.
`hold()` serialises GPU jobs inside this worker; `Lease.use()` switches occupant (unloading the others) inside one job.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Callable

log = logging.getLogger("instai.gpu")

# VRAM that may stay in use by others (desktop compositor etc.) before we consider the GPU "busy": max(abs, fraction of total)
BUSY_ABS_MB = 2500
BUSY_FRACTION = 0.25


class Lease:
    def __init__(self, arbiter: "GPUArbiter", ctx):
        self.arbiter, self.ctx = arbiter, ctx
        self.t0 = time.time()
        self.peak_mb = 0
        self._stop = threading.Event()
        self._sampler: threading.Thread | None = None
        self.occupant: str | None = None

    def use(self, occupant: str, model: str | None = None) -> None:
        """Declare what will run on the GPU next ('llm' | 'comfy' | 'tts' | 'bench'); everything else is unloaded first."""
        if occupant != self.occupant or (occupant == "llm" and model and model != getattr(self, "model", None)):
            self.arbiter.unload_others(occupant)
            self.arbiter.wait_until_free(self.ctx)
        self.occupant, self.model = occupant, model

    def start_sampling(self) -> None:
        if self.arbiter.probe() is None:
            return

        def loop():
            while not self._stop.wait(2.0):
                g = self.arbiter.probe()
                if g and g.get("used_mb"):
                    self.peak_mb = max(self.peak_mb, g["used_mb"])

        self._sampler = threading.Thread(target=loop, daemon=True)
        self._sampler.start()

    def stop(self) -> float:
        self._stop.set()
        return time.time() - self.t0


class GPUArbiter:
    def __init__(self, probe: Callable[[], dict | None] | None = None, unloaders: dict[str, Callable[[], None]] | None = None,
                 poll: float = 5.0, ours: Callable[[], int] | None = None):
        self._lock = threading.Lock()
        self._probe = probe
        self._unloaders = unloaders
        self._ours = ours
        self.poll = poll
        self.holder: int | None = None   # job id currently holding the GPU
        self.busy_reason = ""

    @property
    def busy(self) -> bool:
        """True while a GPU job of this process holds the card (one heavy job per GPU)."""
        return self._lock.locked()

    # --- injectable pieces (tests replace them)
    def probe(self) -> dict | None:
        if self._probe is not None:
            return self._probe()
        from instai.core import hardware

        return hardware.gpu_status()

    def unloaders(self) -> dict[str, Callable[[], None]]:
        if self._unloaders is not None:
            return self._unloaders
        from instai.core import runtime
        from instai.providers.comfy.client import ComfyClient
        from instai.providers.ollama import OllamaProvider

        def llm():
            OllamaProvider(runtime.ollama_url()).unload()

        def comfy():
            c = ComfyClient(runtime.comfyui_url())
            if c.is_up():
                c.free()

        def voice():  # the voice servers this process started (never a server another program runs)
            from instai.providers.audio import services

            services.unload_voice()

        return {"llm": llm, "comfy": comfy, "voice": voice}

    def unload_others(self, occupant: str) -> None:
        unloaders = self.unloaders()
        if occupant in ("tts", "sfx", "music") and "voice" in unloaders:
            occupant = "voice"                      # speech, effects and music all live in the voice servers
        for name, fn in unloaders.items():
            if name != occupant:
                try:
                    fn()
                except Exception as e:  # noqa: BLE001 - unloading is best effort
                    log.warning("unload %s failed: %s", name, e)

    def our_load_mb(self) -> int:
        """VRAM held by services WE manage (Ollama's loaded models, ComfyUI's torch allocation). With an injected probe (tests) it is 0
        unless `ours` is injected too. Without this, a model ComfyUI keeps loaded after our own job would look like 'another program'."""
        if self._ours is not None:
            return self._ours()
        if self._probe is not None:
            return 0
        from instai.core import hardware, runtime

        mb = 0
        try:
            for m in hardware._get_json(runtime.ollama_url().rstrip("/") + "/api/ps", 1.0).get("models", []):
                mb += int((m.get("size_vram") or 0) / 1048576)
        except Exception:  # noqa: BLE001
            pass
        try:
            dev = (hardware._get_json(runtime.comfyui_url().rstrip("/") + "/system_stats", 1.0).get("devices") or [{}])[0]
            if dev.get("torch_vram_total"):
                mb += int(dev["torch_vram_total"] / 1048576) + 600  # + the CUDA context
        except Exception:  # noqa: BLE001
            pass
        return mb

    def foreign_load_mb(self) -> int:
        """VRAM used by OTHER programs: total used minus what Ollama/ComfyUI report as theirs (0 when there is no GPU/nvidia-smi)."""
        g = self.probe()
        if not g or g.get("used_mb") is None:
            return 0
        other = max(0, g["used_mb"] - self.our_load_mb())
        limit = max(BUSY_ABS_MB, int((g.get("total_mb") or 0) * BUSY_FRACTION))
        return other if other > limit else 0

    def wait_until_free(self, ctx, timeout: float = 7200) -> None:
        t0 = time.time()
        while True:
            used = self.foreign_load_mb()
            if not used:
                if self.busy_reason:
                    self.busy_reason = ""
                    ctx.waiting("")
                return
            self.busy_reason = f"GPU busy: another program uses {used / 1024:.1f} GB of VRAM"
            ctx.waiting(self.busy_reason)
            ctx.check()
            if time.time() - t0 > timeout:
                from instai.providers.base import ProviderError

                raise ProviderError("The GPU stayed busy (used by another program); try again later.", retryable=True, code="gpu_busy")
            ctx.sleep(self.poll)

    @contextmanager
    def hold(self, ctx, occupant: str = "llm", model: str | None = None):
        """Serialise GPU jobs; yields a Lease. Waiting for the lock or for foreign VRAM keeps the job responsive to cancel."""
        while not self._lock.acquire(timeout=1.0):
            ctx.waiting("waiting for another GPU job of InstAI")
            ctx.check()
        ctx.waiting("")
        self.holder = ctx.job.pk
        lease = Lease(self, ctx)
        try:
            lease.use(occupant, model)
            lease.start_sampling()
            yield lease
        finally:
            secs = lease.stop()
            ctx.add_gpu_seconds(secs, lease.peak_mb)
            self.holder = None
            self._lock.release()


ARBITER = GPUArbiter()
