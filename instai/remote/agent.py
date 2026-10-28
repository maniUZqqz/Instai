"""InstAI worker agent (PC B). Started by START-WORKER.bat:  python -m instai.remote.agent

It pairs with the main PC once (address + one-time code), then loops: report what this PC can do, claim a task over HTTP, fetch the input
files, run it on THIS PC's GPU under THIS PC's own arbiter (one heavy task at a time), upload the output files, report the result.
It only ever talks to the main PC; the main PC never connects to it. Idea and protocol follow NMarketing's node agent
(Qasem processing-server/agent.py: token auth, pull jobs, progress/heartbeat, upload, finish), simplified. Console text is English/ASCII.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")
os.environ.setdefault("INSTAI_WORKER_MODE", "1")           # no database on this PC: settings come from .env only

log = logging.getLogger("instai.agent")
VERSION = "1.0"
HELLO_EVERY = 20.0


class AuthError(Exception):
    pass


class Server:
    """Thin HTTP client for the main PC's /api/worker/* endpoints."""

    def __init__(self, base: str, token: str = ""):
        self.base = base.rstrip("/")
        self.token = token
        self.http = requests.Session()

    def _headers(self) -> dict:
        return {"Authorization": f"Worker {self.token}"} if self.token else {}

    def call(self, method: str, path: str, *, json_body=None, data=None, headers=None, timeout=60, stream=False):
        try:
            r = self.http.request(method, self.base + path, json=json_body, data=data, headers={**self._headers(), **(headers or {})}, timeout=timeout,
                                  stream=stream)
        except requests.RequestException as e:
            raise ConnectionError(f"main PC unreachable ({type(e).__name__})") from e
        if r.status_code in (401, 403) and path != "/api/worker/pair" and "tasks/" not in path:
            raise AuthError(r.text[:200])
        return r

    def pair(self, code: str, name: str, info: dict) -> dict:
        r = self.call("POST", "/api/worker/pair", json_body={"code": code, "name": name, "info": info})
        if r.status_code != 200:
            try:
                msg = r.json()["error"]["message"]
            except Exception:  # noqa: BLE001
                msg = r.text[:200]
            raise RuntimeError(f"pairing failed: {msg}")
        return r.json()


class AgentCtx:
    """Looks like a JobContext to the GPU arbiter (waiting / check / progress / gpu seconds)."""

    def __init__(self, agent: "Agent", task_id: int):
        self.agent, self.job = agent, SimpleNamespace(pk=task_id, priority=0)
        self.gpu_seconds, self.vram_peak_mb = 0.0, 0

    def waiting(self, reason: str) -> None:
        if reason:
            self.agent.set_progress(None, reason)

    def check(self) -> None:
        if self.agent.cancel_flag.is_set():
            from instai.gpu.executors import TaskCancelled

            raise TaskCancelled()

    def sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(0.5)
            self.check()

    def progress(self, fraction: float, text: str = "") -> None:
        self.agent.set_progress(fraction, text)

    def add_gpu_seconds(self, seconds: float, vram_peak_mb: int = 0) -> None:
        self.gpu_seconds += seconds
        self.vram_peak_mb = max(self.vram_peak_mb, vram_peak_mb)


class Agent:
    def __init__(self, server: Server, data_dir: Path, name: str):
        self.server, self.data_dir, self.name = server, data_dir, name
        self.cancel_flag = threading.Event()
        self.stop = threading.Event()
        self._progress = (0.0, "")
        self._task_id: int | None = None
        self.last_hello = 0.0
        self.done = 0

    # ---- reporting
    def set_progress(self, fraction: float | None, text: str) -> None:
        f = self._progress[0] if fraction is None else fraction
        self._progress = (f, text)

    def _heartbeat_loop(self, task_id: int) -> None:
        while self._task_id == task_id and not self.stop.is_set():
            try:
                r = self.server.call("POST", f"/api/worker/tasks/{task_id}/progress", json_body={"progress": self._progress[0], "text": self._progress[1]}, timeout=20)
                if r.status_code == 200 and r.json().get("cancel"):
                    self.cancel_flag.set()
                elif r.status_code in (403, 404):      # the task is not ours any more
                    self.cancel_flag.set()
            except (ConnectionError, ValueError, AuthError):
                pass
            self.stop.wait(8)

    def hello(self) -> None:
        from instai.gpu import capabilities

        cap = capabilities.local_capabilities(refresh=True)
        gpu = {"name": cap["gpu_name"], "total_mb": cap["vram_total_mb"], "free_mb": cap["vram_free_mb"]}
        r = self.server.call("POST", "/api/worker/hello", json_body={"gpu": gpu, "caps": cap["caps"], "models": cap["models"],
                                                                      "info": {"agent": VERSION, "os": platform.platform(), "python": platform.python_version(),
                                                                               "host": socket.gethostname()}}, timeout=60)
        if r.status_code != 200:
            raise ConnectionError(f"hello answered HTTP {r.status_code}")
        self.last_hello = time.time()
        self.caps, self.free_mb = cap["caps"], cap["vram_free_mb"]

    # ---- one task
    def download_inputs(self, task: dict, in_dir: Path) -> None:
        in_dir.mkdir(parents=True, exist_ok=True)
        for f in task["inputs"]:
            tmp = in_dir / (f["name"] + ".part")
            last = None
            for attempt in range(4):
                try:
                    r = self.server.call("GET", f"/api/worker/tasks/{task['id']}/inputs/{f['name']}", timeout=120, stream=True)
                    if r.status_code != 200:
                        raise ConnectionError(f"HTTP {r.status_code}")
                    with open(tmp, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
                    if f.get("size") and tmp.stat().st_size != f["size"]:
                        raise ConnectionError("truncated download")
                    tmp.replace(in_dir / f["name"])
                    break
                except ConnectionError as e:
                    last = e
                    time.sleep(2 * (attempt + 1))
            else:
                raise RuntimeError(f"could not download input {f['name']}: {last}")

    def upload_outputs(self, task_id: int, out_dir: Path) -> list[str]:
        names = []
        for f in sorted(out_dir.iterdir()):
            if not f.is_file():
                continue
            h = hashlib.sha256()
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            last = None
            for attempt in range(4):
                try:
                    with open(f, "rb") as fh:
                        r = self.server.call("PUT", f"/api/worker/tasks/{task_id}/outputs/{f.name}", data=fh, headers={"X-Content-SHA256": h.hexdigest()},
                                             timeout=1800)
                    if r.status_code == 200:
                        break
                    last = f"HTTP {r.status_code} {r.text[:80]}"
                except ConnectionError as e:
                    last = str(e)
                time.sleep(3 * (attempt + 1))
            else:
                raise RuntimeError(f"could not upload {f.name}: {last}")
            names.append(f.name)
        return names

    def execute(self, task: dict) -> None:
        from instai.gpu import executors
        from instai.gpu.arbiter import ARBITER
        from instai.providers.base import ProviderError

        tid = task["id"]
        work = self.data_dir / "work" / str(tid)
        shutil.rmtree(work, ignore_errors=True)
        in_dir, out_dir = work / "in", work / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._task_id, self._progress = tid, (0.0, "starting")
        self.cancel_flag.clear()
        threading.Thread(target=self._heartbeat_loop, args=(tid,), daemon=True).start()
        ctx = AgentCtx(self, tid)
        t0 = time.time()
        body: dict
        try:
            self.download_inputs(task, in_dir)
            io = executors.TaskIO(in_dir, out_dir, progress=lambda f, t="": self.set_progress(f, t), cancelled=self.cancel_flag.is_set)
            with ARBITER.hold(ctx, executors.OCCUPANT.get(task["kind"], "comfy")):
                result = executors.run(task["kind"], task["payload"], io)
            self.set_progress(0.97, "uploading results")
            names = self.upload_outputs(tid, out_dir)
            body = {"ok": True, "result": result, "outputs": names, "seconds": round(time.time() - t0, 2)}
        except executors.TaskCancelled:
            body = {"ok": False, "error": "cancelled", "retryable": False}
        except ProviderError as e:
            body = {"ok": False, "error": str(e)[:1500], "retryable": e.retryable}
        except Exception as e:  # noqa: BLE001 - a task bug must not kill the agent
            log.exception("task %s crashed", tid)
            body = {"ok": False, "error": f"{type(e).__name__}: {e}"[:1500], "retryable": True}
        finally:
            self._task_id = None
        try:
            self.server.call("POST", f"/api/worker/tasks/{tid}/finish", json_body=body, timeout=60)
        except ConnectionError as e:
            log.warning("could not report task %s: %s", tid, e)
        shutil.rmtree(work, ignore_errors=True)
        self.done += 1
        log.info("task %s (%s) %s in %.1fs", tid, task["kind"], "done" if body["ok"] else "failed: " + body.get("error", "")[:100], time.time() - t0)

    # ---- main loop
    def run_forever(self) -> None:
        backoff = 3.0
        log.info("worker %s ready; waiting for work from %s", self.name, self.server.base)
        while not self.stop.is_set():
            try:
                if time.time() - self.last_hello > HELLO_EVERY:
                    self.hello()
                r = self.server.call("POST", "/api/worker/claim", json_body={"caps": getattr(self, "caps", None), "free_mb": getattr(self, "free_mb", None), "wait": 15},
                                     timeout=45)
                if r.status_code != 200:
                    raise ConnectionError(f"claim answered HTTP {r.status_code}")
                task = r.json().get("task")
                backoff = 3.0
                if task:
                    self.execute(task)
            except AuthError as e:
                log.error("the main PC rejected this worker (%s). It was removed or disabled; pair again (delete data/worker.json).", str(e)[:100])
                self.stop.wait(30)
            except ConnectionError as e:
                log.warning("%s; retrying in %.0fs", e, backoff)
                self.stop.wait(backoff)
                backoff = min(60.0, backoff * 1.6)
            except Exception:  # noqa: BLE001
                log.exception("agent loop error")
                self.stop.wait(5)


# ------------------------------------------------------------------ start-up

def config_path() -> Path:
    from django.conf import settings

    return Path(settings.DATA_DIR) / "worker.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=1), encoding="utf-8")


def normalise_server(s: str) -> str:
    s = s.strip().rstrip("/")
    if not s.startswith("http"):
        s = "http://" + s
    if s.count(":") == 1:             # http://192.168.1.5  -> default worker port
        s += ":8766"
    return s


def pair_interactively(args) -> dict:
    print("\n  This PC is not paired with the main InstAI PC yet.")
    print("  On the main PC open InstAI > Workers > 'Show pairing code'. It shows an address and a code.\n")
    server = normalise_server(args.server or input("  Address of the main PC (for example 192.168.1.20:8766): "))
    code = args.code or input("  Pairing code (for example K7QX-93MF): ")
    name = args.name or input(f"  A name for this PC [{socket.gethostname()}]: ").strip() or socket.gethostname()
    info = {"agent": VERSION, "os": platform.platform(), "host": socket.gethostname()}
    res = Server(server).pair(code, name, info)
    cfg = {"server": server, "token": res["token"], "name": res["worker"]["name"]}
    save_config(cfg)
    print(f"\n  Paired as '{cfg['name']}'. The token is stored in {config_path()} (keep it private).\n")
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="InstAI worker agent")
    ap.add_argument("--server", default="")
    ap.add_argument("--code", default="")
    ap.add_argument("--name", default="")
    ap.add_argument("--reset", action="store_true", help="forget the pairing and pair again")
    args = ap.parse_args(argv)
    import django

    django.setup()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    if args.reset:
        config_path().unlink(missing_ok=True)
    cfg = load_config()
    if not cfg.get("token"):
        try:
            cfg = pair_interactively(args)
        except (RuntimeError, ConnectionError, EOFError, KeyboardInterrupt) as e:
            print(f"\n  [!!] {e}")
            return 2
    from django.conf import settings

    agent = Agent(Server(cfg["server"], cfg["token"]), Path(settings.DATA_DIR), cfg.get("name", socket.gethostname()))
    try:
        agent.run_forever()
    except KeyboardInterrupt:
        agent.stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
