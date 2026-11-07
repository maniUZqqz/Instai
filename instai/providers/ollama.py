"""Ollama adapter (local models, uses the GPU). Structured output: the JSON schema goes in `format`.

The answer is streamed (`stream: true`), so
  * a long generation never dies on one fixed read timeout: only SILENCE is limited (`first_token_timeout` for model loading + reading the
    prompt, then `idle_timeout` between tokens);
  * the job queue shows the tokens produced so far and which model runs on which device (JobContext.live), and the job can be cancelled
    while the model is still writing.
Retry policy: a refused/reset connection (Ollama restarting) is retried twice inside the call; a model that is too big for the card
(out of memory) or too slow (nothing for a long time) is NOT retried the same way - the error says in Persian what to do instead.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import queue
import re
import socket
import threading
import time
from urllib.parse import urlsplit

import requests

from . import ollama_fit
from .base import LLMResult, ProviderError, TextProvider

log = logging.getLogger("instai.ollama")
_THINK = re.compile(r"<think>.*?</think>", re.S)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


FIRST_TOKEN_TIMEOUT = _env_float("INSTAI_OLLAMA_FIRST_SEC", 900.0)     # loading a big model + reading a long prompt can take minutes on a CPU
IDLE_TIMEOUT = _env_float("INSTAI_OLLAMA_IDLE_SEC", 120.0)             # silence between two tokens
CONNECT_RETRY_DELAYS: tuple[float, ...] = tuple(float(x) for x in os.environ.get("INSTAI_OLLAMA_RETRY_DELAYS", "1.5,4").split(",") if x.strip())
SERVER_RETRY_DELAY = 3.0
MEMORY_ERRORS = ("requires more system memory", "out of memory", "cuda error", "failed to allocate", "insufficient memory", "unable to allocate",
                 "model is too large", "not enough memory")
PLACEMENT_TO_DEVICE = {"gpu": "gpu", "mixed": "mixed", "cpu": "cpu"}


class _Conn(Exception):
    """The connection could not be made or broke (before or during the answer)."""

    def __init__(self, err: BaseException, got_tokens: bool = False):
        super().__init__(f"{type(err).__name__}: {err}")
        self.err, self.got_tokens = err, got_tokens


class _Http(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(f"HTTP {status}: {text[:300]}")
        self.status, self.text = status, text


class _Silence(Exception):
    def __init__(self, seconds: float, got_tokens: bool):
        super().__init__(f"no data for {int(seconds)} s")
        self.seconds, self.got_tokens = seconds, got_tokens


def _fa_num(n) -> str:
    return str(n).translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))


def _job_context():
    """The running job's context, or None (no job: tests, scripts, the settings test button, a worker PC without a database)."""
    try:
        from instai.jobs import context as jobctx

        return jobctx.current()
    except Exception:  # noqa: BLE001
        return None


class _Watch(threading.Thread):
    """Polls /api/ps while a request is in flight, so the queue can say 'model loaded, 38% on GPU' before the first token arrives.
    Touches no database (the job thread applies what it finds)."""

    def __init__(self, base_url: str, model: str, first_delay: float = 1.0, interval: float = 2.5):
        super().__init__(daemon=True)
        self.base_url, self.model, self.first_delay, self.interval = base_url, model, first_delay, interval
        self.info: dict | None = None
        self._stop_evt = threading.Event()

    def run(self) -> None:
        delay = self.first_delay
        while not self._stop_evt.wait(delay):
            delay = self.interval
            try:
                info = ollama_fit.loaded_one(self.base_url, self.model, timeout=1.5)
            except Exception:  # noqa: BLE001
                info = None
            if info:
                self.info = info

    def stop(self) -> None:
        self._stop_evt.set()


class OllamaProvider(TextProvider):
    name = "ollama"
    resource = "gpu"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "", keep_alive: str = "10m", num_ctx: int | None = None,
                 num_gpu: int | None = None, first_token_timeout: float | None = None, idle_timeout: float | None = None):
        self.base_url = base_url.rstrip("/")
        self._model = model
        self.keep_alive = keep_alive
        # Ollama's default context is small; prompts carry story memory and the full script
        self.num_ctx = int(num_ctx or os.environ.get("INSTAI_OLLAMA_NUM_CTX") or 8192)
        env_gpu = str(os.environ.get("INSTAI_OLLAMA_NUM_GPU", "")).strip()
        # None = let Ollama decide how many layers fit in VRAM (right in almost every case); a number forces it (999 = try all layers)
        self.num_gpu = num_gpu if num_gpu is not None else (int(env_gpu) if env_gpu.lstrip("-").isdigit() else None)
        self.first_token_timeout = float(first_token_timeout or FIRST_TOKEN_TIMEOUT)
        self.idle_timeout = float(idle_timeout or IDLE_TIMEOUT)
        self._default: dict | None = None

    @property
    def model(self) -> str:
        return self._model

    def options(self, temperature: float, max_tokens: int) -> dict:
        o = {"temperature": temperature, "num_predict": max_tokens, "num_ctx": self.num_ctx}
        if self.num_gpu is not None:
            o["num_gpu"] = self.num_gpu
        return o

    def health(self) -> dict:
        try:
            r = requests.get(self.base_url + "/api/tags", timeout=1.5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return {"ok": True, "detail": f"{len(names)} models", "models": names}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "detail": f"{type(e).__name__}", "models": []}

    # ---- which model
    @staticmethod
    def _vram_mb() -> float | None:
        try:
            from instai.core import hardware

            g = hardware.gpu_status()
            return float(g["total_mb"]) if g and g.get("total_mb") else None
        except Exception:  # noqa: BLE001
            return None

    def default_choice(self) -> dict:
        """The model used when none was chosen: {model, partial, reason_fa, reason_en} (see ollama_fit.pick_default). Cached per provider."""
        if self._default is None:
            vram = self._vram_mb()
            models = ollama_fit.fetch_models(self.base_url, self.num_ctx, vram)
            if models is None:
                raise ProviderError(f"Ollama is not reachable at {self.base_url}", code="ollama_down",
                                    fa=f"InstAI به Ollama وصل نشد ({self.base_url}). مطمئن شوید برنامهٔ Ollama روشن است.")
            choice = ollama_fit.pick_default(models, vram) if models else None
            if choice is None:
                raise ProviderError("Ollama has no models installed", retryable=False, code="no_model",
                                    fa="هیچ مدل زبانی در Ollama نصب نیست. یک مدل مثل qwen3:8b نصب کنید (در صفحهٔ «مدل‌ها» توضیح داده شده).")
            self._default = choice
        return self._default

    def effective_model(self) -> str:
        """The model a call will really use (the chosen one, else the default pick)."""
        return self._model or self.default_choice()["model"]

    def _pick_model(self, model: str | None) -> str:
        return model or self.effective_model()

    # ---- chat
    def generate(self, messages, *, schema=None, temperature=0.4, max_tokens=4096, task=None, meta=None,
                 model=None, timeout=None, idle_timeout=None) -> LLMResult:
        """`timeout` = most seconds to wait for the FIRST token (model loading + reading the prompt); `idle_timeout` = most silence
        between tokens afterwards. There is no limit on the total time: a long answer is fine while tokens keep coming (the job's own
        timeout and the cancel button still apply)."""
        ctx = _job_context()
        mdl = self._pick_model(model)
        body: dict = {"model": mdl, "messages": messages, "stream": True, "keep_alive": self.keep_alive, "options": self.options(temperature, max_tokens)}
        if schema:
            body["format"] = schema
        if mdl.lower().startswith("qwen3"):
            body["think"] = False  # thinking mode wastes minutes on a 3060 and can break structured output
        first_t = float(timeout) if timeout else self.first_token_timeout
        idle_t = float(idle_timeout) if idle_timeout else self.idle_timeout
        t0 = time.time()
        if ctx:
            ctx.live(phase="loading_model", model=mdl, provider="ollama", tokens=0, tps=None, max_tokens=max_tokens, gpu_pct=None, device=None)
        connect_tries, server_tries = 0, 0
        while True:
            try:
                got = self._stream_once(body, mdl, first_t, idle_t, ctx, max_tokens)
                break
            except _Http as e:
                low = e.text.lower()
                if e.status == 400 and "think" in low and "think" in body:
                    body.pop("think")
                    continue
                if e.status == 404:
                    raise ProviderError(f"Ollama model not found: {mdl}", retryable=False, code="model_missing",
                                        fa=f"مدل «{mdl}» در Ollama نصب نیست. نام مدل‌های نصب‌شده را در صفحهٔ «مدل‌ها» ببینید و یکی را انتخاب کنید.") from None
                self._raise_server_error(mdl, e.status, e.text, server_tries)
                server_tries += 1
                self._sleep(SERVER_RETRY_DELAY, ctx)
                continue
            except _Conn as e:
                if not e.got_tokens and connect_tries < len(CONNECT_RETRY_DELAYS):
                    delay = CONNECT_RETRY_DELAYS[connect_tries]
                    connect_tries += 1
                    log.warning("Ollama connection problem (%s); retry %d in %.1f s", e, connect_tries, delay)
                    if ctx:
                        ctx.live(phase="retry", retry=connect_tries)
                    self._sleep(delay, ctx)
                    continue
                if e.got_tokens:
                    raise ProviderError(f"Ollama connection lost while answering: {e}", code="ollama_lost",
                                        fa="ارتباط با Ollama وسط نوشتن پاسخ قطع شد (احتمالاً Ollama بسته یا ری‌استارت شد). دوباره تلاش می‌شود.") from None
                raise ProviderError(f"Ollama request failed: {e}", code="ollama_down",
                                    fa=f"InstAI به Ollama وصل نشد ({self.base_url}). مطمئن شوید برنامهٔ Ollama روشن است.") from None
            except _Silence as e:
                raise self._silence_error(mdl, e, first_t, idle_t) from None
        text = _THINK.sub("", got["text"]).strip()
        dt = time.time() - t0
        fin = got["final"]
        ev, ed = fin.get("eval_count"), fin.get("eval_duration")
        tps = round(ev / (ed / 1e9), 1) if ev and ed else None
        place = got.get("placement") or {}
        raw = {"done_reason": fin.get("done_reason"), "load_seconds": round((fin.get("load_duration") or 0) / 1e9, 2),
               "first_token_seconds": got.get("first_token_seconds"), "gpu_pct": place.get("gpu_pct"), "placement": place.get("placement"),
               "size_mb": place.get("size_mb"), "vram_mb": place.get("vram_mb")}
        if ctx:
            ctx.live(phase="parsing", tokens=ev or got["tokens"], tps=tps)
            ctx.flush_live()
        return LLMResult(text=text, provider=self.name, model=mdl, seconds=dt, prompt_tokens=fin.get("prompt_eval_count"),
                         completion_tokens=ev, tokens_per_second=tps, raw=raw)

    # ---- one streamed request
    def _stream_once(self, body: dict, mdl: str, first_t: float, idle_t: float, ctx, max_tokens: int) -> dict:
        u = urlsplit(self.base_url)
        host, port = u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)
        path = (u.path.rstrip("/") or "") + "/api/chat"
        payload = json.dumps(body).encode("utf-8")
        q: queue.Queue = queue.Queue()
        holder: dict = {}

        def worker() -> None:
            conn = None
            try:
                cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
                conn = holder["conn"] = cls(host, port, timeout=10)
                conn.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
                holder["sent_at"] = time.time()          # from here on silence is counted (the connect itself has its own 10 s limit)
                if conn.sock is not None:
                    conn.sock.settimeout(None)       # the model may load for minutes; the caller enforces the limits and closes the socket
                resp = conn.getresponse()
                q.put(("status", resp.status))
                if resp.status != 200:
                    q.put(("body", resp.read(4000).decode("utf-8", "replace")))
                    q.put(("end", None))
                    return
                buf = b""
                while True:
                    data = resp.read1(65536)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line.strip():
                            q.put(("line", line))
                if buf.strip():
                    q.put(("line", buf))
                q.put(("end", None))
            except BaseException as e:  # noqa: BLE001 - the caller decides what it means
                q.put(("err", e))

        def abort() -> None:
            conn = holder.get("conn")
            if conn is not None:
                try:
                    if conn.sock is not None:
                        conn.sock.shutdown(socket.SHUT_RDWR)      # wakes a thread blocked in recv (close() alone may not, on Windows)
                except OSError:
                    pass
                try:
                    conn.close()
                except OSError:
                    pass

        threading.Thread(target=worker, daemon=True, name="ollama-stream").start()
        watch = _Watch(self.base_url, mdl) if ctx else None
        if watch:
            watch.start()
        parts: list[str] = []
        tokens, status, err_body = 0, 200, ""
        final: dict = {}
        t_start = last = time.time()
        t_first: float | None = None
        shown_place: dict | None = None
        try:
            while True:
                try:
                    kind, val = q.get(timeout=0.5)
                except queue.Empty:
                    if ctx:
                        ctx.check()
                    if watch and watch.info is not None and watch.info is not shown_place:
                        shown_place = watch.info
                        self._show_placement(ctx, mdl, shown_place, t_first)
                    if "sent_at" not in holder:
                        continue                          # still connecting: a refusal or the 10 s connect limit ends it
                    silent = time.time() - max(last, holder["sent_at"])
                    if silent > (idle_t if t_first is not None else first_t):
                        abort()
                        raise _Silence(silent, t_first is not None)
                    continue
                last = time.time()
                if kind == "status":
                    status = val
                elif kind == "body":
                    err_body = val
                elif kind == "err":
                    abort()
                    raise _Conn(val, got_tokens=t_first is not None)
                elif kind == "end":
                    break
                elif kind == "line":
                    if status != 200:
                        continue
                    try:
                        obj = json.loads(val)
                    except ValueError:
                        continue
                    if obj.get("error"):
                        raise _Http(500, str(obj["error"]))
                    msg = obj.get("message") or {}
                    piece, thought = msg.get("content") or "", msg.get("thinking") or ""
                    if piece or thought:
                        if t_first is None:
                            t_first = time.time()
                            if ctx:
                                ctx.live(phase="generating")
                        tokens += 1
                        if piece:
                            parts.append(piece)
                        if ctx:
                            dur = time.time() - t_first
                            ctx.live(tokens=tokens, tps=round(tokens / dur, 1) if dur > 0.5 else None)
                            if tokens % 8 == 0:
                                ctx.check()
                    elif t_first is None and ctx and obj.get("done") is not True:
                        ctx.live(phase="prefill")
                    if obj.get("done"):
                        final = obj
            if status != 200:
                raise _Http(status, err_body)
            if not final:
                raise _Conn(ConnectionError("the answer ended before Ollama said it was done"), got_tokens=bool(parts))
        finally:
            abort()
            if watch:
                watch.stop()
        place = ollama_fit.loaded_one(self.base_url, mdl, timeout=1.5)
        if place:
            self._show_placement(ctx, mdl, place, t_first, final=True)
        return {"text": "".join(parts), "final": final, "tokens": tokens, "placement": place,
                "first_token_seconds": round((t_first or time.time()) - t_start, 2) if t_first else None}

    @staticmethod
    def _show_placement(ctx, mdl: str, place: dict, t_first, final: bool = False) -> None:
        if not ctx:
            return
        dev = PLACEMENT_TO_DEVICE.get(place["placement"], "")
        warned = ctx.live_value("placement_warned")
        ctx.live(device=dev, gpu_pct=place["gpu_pct"], phase=(ctx.live_value("phase") if t_first is not None or final else "prefill"))
        if dev in ("mixed", "cpu") and not warned and OllamaProvider._vram_mb():
            ctx.live(placement_warned=True)
            ctx.log(f"هشدار: مدل «{mdl}» فقط {_fa_num(place['gpu_pct'])}٪ روی کارت گرافیک است و بقیه روی CPU کار می‌کند؛ کند است. "
                    f"برای سرعت، مدل کوچک‌تری انتخاب کنید (صفحهٔ «مدل‌ها»).", "warning")

    @staticmethod
    def _sleep(seconds: float, ctx) -> None:
        if ctx:
            ctx.sleep(seconds)
        else:
            time.sleep(seconds)

    # ---- plain-language errors
    def _raise_server_error(self, mdl: str, status: int, text: str, tries: int) -> None:
        msg = text
        try:
            msg = str(json.loads(text).get("error") or text)
        except ValueError:
            pass
        low = msg.lower()
        if any(k in low for k in MEMORY_ERRORS):
            raise ProviderError(f"Ollama could not load {mdl}: {msg[:300]}", retryable=False, code="llm_oom",
                                fa=f"حافظهٔ کارت گرافیک یا رم برای مدل «{mdl}» کافی نبود (مدل برای این رایانه بزرگ است). "
                                   "یک مدل کوچک‌تر مثل qwen3:8b انتخاب کنید (صفحهٔ «مدل‌ها» یا «تنظیمات»).")
        if tries >= 1:
            raise ProviderError(f"Ollama error (HTTP {status}): {msg[:300]}", code="ollama_error",
                                fa=f"Ollama با خطا جواب داد: {msg[:160]}. اگر تکرار شد، Ollama را ببندید و دوباره روشن کنید.")

    def _silence_error(self, mdl: str, e: _Silence, first_t: float, idle_t: float) -> ProviderError:
        place = None
        try:
            place = ollama_fit.loaded_one(self.base_url, mdl, timeout=1.5)
        except Exception:  # noqa: BLE001
            pass
        partial = bool(place and place["placement"] in ("mixed", "cpu") and self._vram_mb())
        if e.got_tokens:
            return ProviderError(f"Ollama stopped producing tokens for {int(e.seconds)} s (model {mdl})", code="llm_stalled",
                                 fa=f"مدل «{mdl}» وسط نوشتن {_fa_num(int(e.seconds))} ثانیه ساکت ماند. دوباره تلاش می‌شود؛ اگر تکرار شد Ollama را ببندید و دوباره روشن کنید.")
        why_fa = (f" فقط {_fa_num(place['gpu_pct'])}٪ مدل روی کارت گرافیک است و بقیه روی CPU کار می‌کند؛ مدل برای کارت گرافیک بزرگ است."
                  if partial else " ممکن است مدل بزرگ باشد یا Ollama مشغول کار دیگری باشد.")
        return ProviderError(f"Ollama sent nothing for {int(e.seconds)} s (model {mdl}; loading + reading the prompt)" + (f"; only {place['gpu_pct']}% on the GPU" if partial else ""),
                             retryable=not partial, code="llm_timeout",
                             fa=f"مدل «{mdl}» تا {_fa_num(int(e.seconds))} ثانیه هیچ پاسخی نداد.{why_fa} "
                                "در صفحهٔ «مدل‌ها» یا «تنظیمات» مدل کوچک‌تری (مثلاً qwen3:8b) انتخاب کنید.")

    # ---- housekeeping
    def loaded_models(self) -> list[str]:
        try:
            r = requests.get(self.base_url + "/api/ps", timeout=3)
            return [m.get("name", "") for m in r.json().get("models", [])]
        except Exception:  # noqa: BLE001
            return []

    def pull(self, model: str, on_progress=None, should_stop=None) -> dict:
        """Download a model into Ollama (its own /api/pull, streamed). Ollama keeps the finished parts of a stopped pull, so a pull that is
        stopped (`should_stop()` -> True, e.g. the night window closed) continues where it was the next time. `on_progress(fraction, text)`.
        Returns {"status": "success"}. A refused connection is `ollama_down` (the job waits for Ollama)."""
        try:
            r = requests.post(self.base_url + "/api/pull", json={"model": model, "name": model, "stream": True}, stream=True, timeout=(5, 120))
        except requests.RequestException as e:
            raise ProviderError(f"Ollama is not reachable at {self.base_url}: {type(e).__name__}", code="ollama_down",
                                fa=f"InstAI به Ollama وصل نشد ({self.base_url}). مطمئن شوید برنامهٔ Ollama روشن است.") from None
        try:
            if r.status_code != 200:
                raise ProviderError(f"Ollama could not pull {model} (HTTP {r.status_code}): {r.text[:200]}", retryable=r.status_code >= 500, code="pull_failed",
                                    fa=f"Ollama مدل «{model}» را نگرفت. نام مدل را بررسی کنید.")
            last = {"status": ""}
            for line in r.iter_lines():
                if should_stop and should_stop():
                    return {"status": "stopped"}
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except ValueError:
                    continue
                if last.get("error"):
                    raise ProviderError(f"Ollama pull error: {last['error']}", retryable=False, code="pull_failed", fa=f"Ollama مدل «{model}» را نگرفت: {last['error'][:120]}")
                total, done = last.get("total"), last.get("completed")
                if on_progress and total:
                    on_progress(min(1.0, (done or 0) / total), str(last.get("status") or "")[:100])
                elif on_progress:
                    on_progress(0.0, str(last.get("status") or "")[:100])
            if last.get("status") != "success":
                raise ProviderError(f"Ollama pull of {model} ended without success ({last.get('status')})", code="pull_failed",
                                    fa="دانلود مدل کامل نشد؛ دوباره امتحان کنید (از همان‌جا ادامه می‌یابد).")
            return last
        except requests.RequestException as e:
            raise ProviderError(f"Ollama connection lost while pulling {model}: {type(e).__name__}", code="pull_failed",
                                fa="ارتباط با Ollama وسط دانلود قطع شد؛ دوباره امتحان می‌شود (از همان‌جا ادامه می‌یابد).") from None
        finally:
            r.close()

    def unload(self, keep: str | None = None) -> None:
        """keep_alive 0 for every loaded model except `keep` (frees VRAM for ComfyUI / voice models / another LLM)."""
        for name in self.loaded_models():
            if keep and ollama_fit.same_model(name, keep):
                continue
            try:
                requests.post(self.base_url + "/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
            except requests.RequestException:
                pass
