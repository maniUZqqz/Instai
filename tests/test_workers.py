"""Two PCs: pairing (code + token), the LAN gate, atomic claim with leases, routing by capability/VRAM/busy, and a REAL second process
(the worker agent) that pairs over HTTP and runs tasks against its own fake ComfyUI / voice servers."""
from __future__ import annotations

import base64
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
import requests
from django.test import Client
from django.utils import timezone

from tests.fakes import comfy_server, wait_until

pytestmark = pytest.mark.django_db(transaction=True)
ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def lan():
    """The worker-gate listener of this (main) process on a free localhost port - a real HTTP server, only the worker API reachable."""
    from instai import lan as lan_mod

    server = lan_mod.LanServer()
    assert server.start(free_port(), host="127.0.0.1")
    yield server
    server.stop()


def post(client, path, body=None, token=None):
    h = {"HTTP_AUTHORIZATION": f"Worker {token}"} if token else {}
    return client.post(path, data=body or {}, content_type="application/json", **h)


# ------------------------------------------------------------------ pairing and auth

def test_pairing_code_is_one_time_and_expires():
    from instai.jobs import workers
    from instai.jobs.models import PairingCode

    code, _ = workers.new_pairing_code()
    assert len(code) == 9 and code[4] == "-"
    w, token = workers.pair(code.lower(), "PC-B", {"agent": "1"}, "10.0.0.5")       # case and the dash do not matter
    assert w.name == "PC-B" and len(token) > 30 and w.token_hash != token
    with pytest.raises(workers.PairingError):
        workers.pair(code, "again", {}, "10.0.0.6")                               # one time only
    code2, row = workers.new_pairing_code()
    PairingCode.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with pytest.raises(workers.PairingError):
        workers.pair(code2, "late", {}, "x")
    c3, _ = workers.new_pairing_code()
    c4, _ = workers.new_pairing_code()                                            # a new code replaces the older unused one
    with pytest.raises(workers.PairingError):
        workers.pair(c3, "old", {}, "x")
    w2, _ = workers.pair(c4, "PC-B", {}, "x")
    assert w2.name == "PC-B-2"                                                    # names stay unique


def test_http_pairing_auth_disable_and_throttle():
    from instai.jobs import workers
    from instai.jobs.models import WorkerNode

    c = Client()
    assert post(c, "/api/worker/hello", {}).status_code == 401
    assert post(c, "/api/worker/hello", {}, token="x" * 40).status_code == 401
    code, _ = workers.new_pairing_code()
    r = post(c, "/api/worker/pair", {"code": code, "name": "pc-b", "info": {"agent": "1.0"}})
    assert r.status_code == 200
    token = r.json()["token"]
    h = post(c, "/api/worker/hello", {"gpu": {"name": "RTX 3060", "total_mb": 12288, "free_mb": 11000}, "caps": ["gpu", "comfy:wan22_i2v_a14b_fp8"],
                                      "models": {"comfyui": True}, "info": {"agent": "1.0"}}, token=token)
    assert h.status_code == 200 and h.json()["protocol"] == 1
    w = WorkerNode.objects.get(name="pc-b")
    assert w.gpu_name == "RTX 3060" and w.vram_total_mb == 12288 and "gpu" in w.capabilities and w.last_seen
    WorkerNode.objects.filter(pk=w.pk).update(enabled=False)
    assert post(c, "/api/worker/hello", {}, token=token).status_code == 401       # a disabled worker is locked out at once
    # brute force: after a dozen failures this client is throttled, even with a valid code
    workers._FAILURES.clear()
    for _ in range(workers.MAX_FAILURES):
        assert post(c, "/api/worker/pair", {"code": "AAAA-BBBB", "name": "x"}).status_code == 403
    good, _ = workers.new_pairing_code()
    assert post(c, "/api/worker/pair", {"code": good, "name": "x"}).status_code == 429
    workers._FAILURES.clear()


def test_the_lan_gate_exposes_only_the_worker_api(lan):
    base = f"http://127.0.0.1:{lan.port}"
    assert requests.post(base + "/api/worker/hello", json={}, timeout=10).status_code == 401           # the worker API answers (needs a token)
    for blocked in ("/", "/api/health", "/api/jobs", "/api/pages", "/api/workers", "/api/workers/pairing", "/api/settings", "/media/x.png", "/static/app/x.js"):
        for method in ("GET", "POST"):
            r = requests.request(method, base + blocked, timeout=10)
            assert r.status_code == 404 and "pages" not in r.text, (method, blocked, r.status_code)
    # the Host header cannot be used to reach the rest of the app either
    assert requests.get(base + "/api/health", headers={"Host": "localhost"}, timeout=10).status_code == 404


def test_lan_addresses_never_include_loopback():
    from instai import lan as lan_mod

    assert all(not ip.startswith(("127.", "169.254.")) for ip in lan_mod.lan_addresses())


# ------------------------------------------------------------------ claim / lease

def make_worker(name="pcb", caps=("gpu", "comfy:flux_dev_fp8_t2i"), vram=12288, enabled=True):
    from instai.jobs import workers
    from instai.jobs.models import WorkerNode

    return WorkerNode.objects.create(name=name, token_hash=workers.hash_secret(name), enabled=enabled, last_seen=timezone.now(), capabilities=list(caps),
                                     vram_total_mb=vram, vram_free_mb=vram)


def test_claim_is_atomic_respects_caps_vram_and_pinning():
    from instai.jobs import workers
    from instai.jobs.models import RemoteTask

    a, b = make_worker("a"), make_worker("b", caps=("gpu", "voice:moss"))
    t = RemoteTask.objects.create(kind="comfy.graph", needs=["comfy:flux_dev_fp8_t2i"], vram_mb=10000)
    assert workers.claim(b) is None                                       # b lacks the capability
    small = make_worker("small", vram=4096)
    assert workers.claim(small) is None                                   # not enough VRAM
    results = []

    def go(w):
        results.append(workers.claim(w))
    ths = [threading.Thread(target=go, args=(a,)) for _ in range(6)]
    [th.start() for th in ths]
    [th.join() for th in ths]
    assert len([r for r in results if r is not None]) == 1                # six racers, one winner
    t.refresh_from_db()
    assert t.status == "running" and t.worker_id == a.pk and t.lease_expires > timezone.now()
    pinned = RemoteTask.objects.create(kind="voice.tts", needs=["voice:moss"], target_worker=b)
    other = make_worker("c", caps=("voice:moss",))
    assert workers.claim(other) is None and workers.claim(b).pk == pinned.pk   # pinned tasks go only to their worker


def test_progress_heartbeat_cancel_finish_and_lease_expiry():
    from instai.jobs import workers
    from instai.jobs.models import RemoteTask

    w = make_worker()
    t = RemoteTask.objects.create(kind="comfy.graph", needs=[])
    t = workers.claim(w)
    assert workers.progress(t, w, 0.4, "step 4/8") is False
    t.refresh_from_db()
    assert t.progress == pytest.approx(0.4) and t.progress_text == "step 4/8"
    RemoteTask.objects.filter(pk=t.pk).update(cancel_requested=True)
    assert workers.progress(t, w, 0.5, "x") is True                        # the main PC asks the worker to stop
    assert workers.finish(t, w, False, "cancelled", False, {}, 3.0)
    t.refresh_from_db()
    assert t.status == "cancelled"
    # a worker that goes silent loses the task: it FAILS (retryable) so the waiting job can use another device
    t2 = RemoteTask.objects.create(kind="comfy.graph", needs=[])
    t2 = workers.claim(w)
    RemoteTask.objects.filter(pk=t2.pk).update(lease_expires=timezone.now() - timedelta(seconds=1))
    assert workers.reap_expired() == 1
    t2.refresh_from_db()
    assert t2.status == "failed" and t2.retryable and "heartbeat" in t2.error
    assert workers.finish(t2, w, True, "", True, {}, 1.0) is False         # a late answer from the lost worker is ignored


def test_router_prefers_idle_faster_device_and_waits_when_all_busy():
    from instai.gpu import compute
    from instai.jobs.models import RemoteTask

    w = make_worker("fast", caps=("gpu", "voice:moss"))
    needs = ["voice:moss"]
    cands = compute.candidates("voice.tts", {"engine": "moss"}, needs=needs, vram_mb=9500, local_ok=False)
    assert [c.name for c in cands] == ["fast"] and compute.choose(cands).name == "fast"
    RemoteTask.objects.create(kind="voice.tts", needs=needs, target_worker=w)          # something already queued for it = busy
    assert compute.choose(compute.candidates("voice.tts", {"engine": "moss"}, needs=needs, vram_mb=9500, local_ok=False)) is None
    c1 = compute.Candidate("local", True, False, 11000, 12288, speed=30.0)
    c2 = compute.Candidate("pcb", False, False, 11000, 12288, speed=12.0)
    assert compute.choose([c1, c2]).name == "pcb"                                        # both idle: the measured faster one
    assert compute.choose([compute.Candidate("local", True, False, 1, 1), compute.Candidate("pcb", False, False, 1, 1)]).name == "local"   # unknown speeds: this PC first
    assert compute.choose([compute.Candidate("local", True, True, 1, 1), compute.Candidate("pcb", False, False, 1, 1)]).name == "pcb"       # busy local: the other PC
    # not enough total VRAM -> not even a candidate
    make_worker("tiny", caps=("voice:moss",), vram=4096)
    assert "tiny" not in [c.name for c in compute.candidates("voice.tts", {"engine": "moss"}, needs=needs, vram_mb=9500, local_ok=False)]


def test_management_api_pairing_disable_remove_benchmark(api, lan, monkeypatch):
    from instai import lan as lan_mod

    monkeypatch.setattr(lan_mod, "LAN", lan)                                           # the already running localhost listener
    r = api.post("/api/workers/pairing", {}, format="json").json()
    assert len(r["code"]) == 9 and r["valid_minutes"] == 15 and r["port"] == lan.port and isinstance(r["addresses"], list)
    w = make_worker("pcb")
    ov = api.get("/api/workers").json()
    assert [d["name"] for d in ov["devices"]][:2] == ["local", "pcb"] and ov["lan"]["running"]
    assert api.patch(f"/api/workers/{w.pk}", {"enabled": False}, format="json").json()["enabled"] is False
    assert api.post(f"/api/workers/{w.pk}/benchmark", {}, format="json").status_code == 409          # disabled
    api.patch(f"/api/workers/{w.pk}", {"enabled": True}, format="json")
    t = api.post(f"/api/workers/{w.pk}/benchmark", {}, format="json")
    assert t.status_code == 202 and t.json()["kind"] == "bench.node"
    assert api.post(f"/api/workers/{w.pk}/benchmark", {}, format="json").status_code == 409          # one at a time
    assert api.delete(f"/api/workers/{w.pk}").status_code == 204 and not api.get("/api/workers").json()["workers"]
    assert api.post("/api/workers/lan", {"enabled": False}, format="json").json()["enabled"] is False


# ------------------------------------------------------------------ a REAL second process

class Agent:
    """The worker agent as a separate OS process with its own data folder, its own (fake) ComfyUI and its own fake voice servers."""

    def __init__(self, tmp_path: Path, server_url: str, code: str, comfy_url: str, name="pc-b"):
        self.dir = tmp_path / "pcb-data"
        env = {**os.environ, "INSTAI_DATA_DIR": str(self.dir), "INSTAI_COMFYUI_URL": comfy_url, "INSTAI_OLLAMA_URL": "http://127.0.0.1:9", "INSTAI_VOICE_FAKE": "1",
               "PYTHONIOENCODING": "utf-8", "INSTAI_TTS_ENGINE": "fake", "INSTAI_SFX_ENGINE": "auto", "INSTAI_MUSIC_ENGINE": "auto", "INSTAI_MOSS_TTS_URL": "", "PYTHONUNBUFFERED": "1",
               **{f"INSTAI_VOICE_PORT_{k}": str(free_port()) for k in ("MOSS", "SFX", "MUSIC")}}
        self.log = open(tmp_path / "agent.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen([sys.executable, "-m", "instai.remote.agent", "--server", server_url, "--code", code, "--name", name], cwd=ROOT, env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)

    def stop(self):
        self.proc.kill()
        self.proc.wait(10)
        self.log.close()


@pytest.fixture
def pc_b(tmp_path, lan, ffmpeg_available):
    """Pair a real agent process with this process over HTTP. Yields (agent, worker row, fake comfy of PC B)."""
    from instai.jobs import workers
    from instai.jobs.models import WorkerNode

    comfy_b = comfy_server()
    comfy_b.__enter__()
    code, _ = workers.new_pairing_code()
    agent = Agent(tmp_path, f"http://127.0.0.1:{lan.port}", code, comfy_b.url)
    try:
        assert wait_until(lambda: any("comfy:flux_dev_fp8_t2i" in (w.capabilities or []) for w in WorkerNode.objects.filter(name="pc-b")), timeout=60), \
            "the agent did not pair and report capabilities:\n" + open(tmp_path / "agent.log", encoding="utf-8").read()[-1500:]
        yield agent, WorkerNode.objects.get(name="pc-b"), comfy_b
    finally:
        agent.stop()
        comfy_b.__exit__()


def job_ctx(title="t", episode=None):
    from instai.jobs import queue
    from instai.jobs.context import JobContext
    from instai.jobs.models import Job

    job = queue.enqueue("test.noop", {}, title=title)
    Job.objects.filter(pk=job.pk).update(status="running", lease_owner="w")
    return JobContext(Job.objects.get(pk=job.pk), "w")


def flux_payload(seed=1):
    from instai.providers.comfy.workflows import get_workflow

    graph = get_workflow("flux_dev_fp8_t2i").build({"prompt": "a lake", "width": 256, "height": 448, "steps": 4, "seed": seed})
    return {"graph": graph, "workflow": "flux_dev_fp8_t2i", "timeout": 120}


def test_real_agent_process_pairs_reports_and_runs_a_comfy_task(pc_b):
    from PIL import Image

    from instai.gpu import compute

    agent, worker, comfy_b = pc_b
    assert "gpu" not in worker.capabilities                       # no nvidia-smi here: honest, not invented
    assert "comfy:flux_dev_fp8_t2i" in worker.capabilities and "comfy:wan22_i2v_a14b_fp8" in worker.capabilities
    assert worker.models_info["comfyui"] is True and worker.info["agent"] == "1.0"
    ctx = job_ctx()
    res = compute.run_task(ctx, "comfy.graph", flux_payload())      # this PC has no ComfyUI: only the worker can do it
    try:
        assert res.device == "pc-b" and len(res.files) == 1 and res.files[0].suffix == ".png"
        with Image.open(res.files[0]) as im:
            assert im.size[0] >= 8
        assert res.result["prompt_id"] and res.seconds > 0
    finally:
        res.cleanup()
    assert len(comfy_b.prompts) == 1 and comfy_b.prompts[0]["4"]["inputs"]["text"] == "a lake"
    from instai.jobs.models import RemoteTask, WorkerNode

    t = RemoteTask.objects.get(kind="comfy.graph")
    assert t.status == "succeeded" and t.worker.name == "pc-b" and t.job_id == ctx.job.pk
    w = WorkerNode.objects.get(name="pc-b")
    assert w.measured["avg"]["flux_dev_fp8_t2i"]["n"] == 1         # the router learns this worker's speed from real runs


def test_real_agent_runs_voice_tasks_with_input_and_output_files(pc_b, tmp_path):
    from instai.gpu import compute
    from tests.test_voices import wav_bytes

    ref = tmp_path / "ref.wav"
    ref.write_bytes(wav_bytes(3.0))
    ctx = job_ctx()
    res = compute.run_task(ctx, "voice.tts", {"engine": "moss", "text": "سلام، این یک آزمون است", "language": "fa", "seed": 3, "reference_input": "ref.wav"},
                           inputs={"ref.wav": ref})
    try:
        assert res.device == "pc-b" and res.result["engine"] == "moss" and res.file("speech.wav").stat().st_size > 1000
    finally:
        res.cleanup()
    res = compute.run_task(ctx, "voice.sfx", {"prompt": "door creak", "seconds": 2.0, "seed": 1})
    try:
        assert res.result["engine"] == "moss-sfx" and res.file("sfx.wav")
    finally:
        res.cleanup()
    res = compute.run_task(ctx, "voice.music", {"prompt": "calm piano", "seconds": 10.0})
    try:
        assert res.result["engine"] == "acestep" and res.file("music.wav").stat().st_size > 1000
    finally:
        res.cleanup()


def test_both_gpus_work_at_the_same_time(pc_b, tmp_path):
    """This PC has its own (fake) ComfyUI and PC B another: 6 shots fan out over both, each device runs ONE heavy task at a time."""
    from instai.core import settings_store
    from instai.gpu import compute

    agent, worker, comfy_b = pc_b
    comfy_a = comfy_server(polls=2)
    comfy_b.polls = 2
    comfy_a.__enter__()
    try:
        settings_store.set_setting("comfyui_url", comfy_a.url)
        compute._CAP_CACHE.update(at=0.0, value=None)
        ctx = job_ctx()
        spans = []                                         # (device, start, end) of every shot task, measured around run_task

        def shot(i):
            a = time.time()
            r = compute.run_task(ctx, "comfy.graph", flux_payload(seed=i))
            spans.append((r.device, a, time.time()))
            r.cleanup()
            return r.device
        devices = compute.fan_out(ctx, list(range(6)), shot, kind="comfy.graph", payload={"workflow": "flux_dev_fp8_t2i"})
        assert set(devices) == {"local", "pc-b"}, devices                                      # both GPUs got work
        assert len(comfy_a.prompts) + len(comfy_b.prompts) == 6 and comfy_a.prompts and comfy_b.prompts
        # one heavy task per GPU: on each PC the ComfyUI prompts never overlapped (every task takes >= 2 s because of the polls)
        for times in (comfy_a.prompt_times, comfy_b.prompt_times):
            assert all(b - a >= 1.5 for a, b in zip(times, times[1:])), times
        # ... but the two PCs ran at the same time: some task on one PC overlapped in time with a task on the other
        overlap = max((min(e1, e2) - max(s1, s2) for d1, s1, e1 in spans for d2, s2, e2 in spans if d1 != d2), default=0)
        assert overlap > 2.0, spans
        for dev in ("local", "pc-b"):                                                          # and never two at once on the same PC
            mine = sorted((s_, e_) for d, s_, e_ in spans if d == dev)
            assert all(e1 <= s2 + 0.05 for (s1, e1), (s2, e2) in zip(mine, mine[1:])), mine
    finally:
        settings_store.set_setting("comfyui_url", "")
        comfy_a.__exit__()
        compute._CAP_CACHE.update(at=0.0, value=None)


def test_a_killed_worker_does_not_lose_the_task(pc_b):
    """The worker process dies while a task runs: the lease expires, the task fails (retryable) and, with no other device, the job gets a clear error."""
    from instai.gpu import compute
    from instai.jobs.models import RemoteTask
    from instai.providers.base import ProviderError

    agent, worker, comfy_b = pc_b
    comfy_b.polls = 60                                    # a long task
    ctx = job_ctx()
    err = []

    def go():
        try:
            compute.run_task(ctx, "comfy.graph", flux_payload(), timeout=60)
        except ProviderError as e:
            err.append(e)
        finally:
            from django.db import close_old_connections

            close_old_connections()
    th = threading.Thread(target=go)
    th.start()
    assert wait_until(lambda: RemoteTask.objects.filter(status="running").exists(), timeout=30)
    agent.proc.kill()
    RemoteTask.objects.filter(status="running").update(lease_expires=timezone.now() - timedelta(seconds=1))      # (the real lease is 120 s)
    from instai.jobs import workers

    workers.reap_expired()
    th.join(60)
    assert err and err[0].code in ("worker_failed", "not_ready"), err
    assert RemoteTask.objects.get().status == "failed"
