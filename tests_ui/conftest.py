"""Browser checks (Playwright). Separate from the Django suite: it starts the real server + worker as subprocesses in demo mode and
drives chromium. Run:  python -m pytest tests_ui -q   (any Python that has pytest + playwright; the project's venv does not need them).
Playwright's chromium must be installed already (this uses launch(channel="chromium"), falling back to the default)."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = ROOT / ".venv" / "bin" / "python"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Api:
    def __init__(self, base: str):
        self.base = base

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            raise AssertionError(f"{method} {path} -> {e.code} {e.read()[:300]!r}")

    def get(self, p): return self.call("GET", p)
    def post(self, p, b=None): return self.call("POST", p, b or {})
    def put(self, p, b): return self.call("PUT", p, b)

    def wait_job(self, resp, timeout=180):
        job = resp["job"] if "job" in resp else resp
        end = time.time() + timeout
        while time.time() < end:
            j = self.get(f"/api/jobs/{job['id']}")
            if j["status"] not in ("queued", "running"):
                assert j["status"] == "succeeded", j
                return j
            time.sleep(0.4)
        raise AssertionError("job timeout")


@pytest.fixture(scope="session")
def server():
    data = tempfile.mkdtemp(prefix="instai-ui-")
    port = _free_port()
    env = {**os.environ, "INSTAI_DATA_DIR": os.path.join(data, "data"), "INSTAI_PORT": str(port), "INSTAI_SECRET_KEY": "ui-test-key",
           "INSTAI_LLM_PROVIDER": "fake", "INSTAI_TTS_ENGINE": "fake", "INSTAI_IMAGE_ENGINE": "placeholder", "INSTAI_RESEARCH_FETCH": "fake",
           "INSTAI_OLLAMA_URL": "http://127.0.0.1:9", "INSTAI_COMFYUI_URL": "http://127.0.0.1:9", "PYTHONIOENCODING": "utf-8"}
    env.pop("INSTAI_TESTING", None)
    procs = [subprocess.Popen([str(PY), "-m", "instai.serve"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
             subprocess.Popen([str(PY), "manage.py", "run_worker"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
    # (run_worker waits for the migration the server performs at start-up)
    base = f"http://127.0.0.1:{port}"
    end = time.time() + 90
    while time.time() < end:
        try:
            urllib.request.urlopen(base + "/api/health", timeout=2)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    else:
        for p in procs:
            p.kill()
        raise RuntimeError("server did not start")
    time.sleep(6)  # the worker's first heartbeat
    yield base
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture(scope="session")
def seeded(server):
    """One page of each format with a plan; the anime episode goes all the way to a rendered preview."""
    api = Api(server)
    out = {}
    for fmt in ("anime_whatif", "recurring_character", "concept_explainer"):
        strat = api.wait_job(api.post("/api/strategy", {"page_name": f"نمونه {fmt}", "format": fmt, "language": "fa", "idea": "ایده"}))["result"]["strategy"]
        page = api.post("/api/pages", {"name": f"نمونه {fmt}", "format": fmt, "languages": ["fa"], "idea": "ایده", "strategy": strat,
                                       "series": {**strat["series_ideas"][0], "episodes": 5}, "profiles": {"production": {"episode_length_sec": 20}}})
        sid = api.get(f"/api/pages/{page['id']}/series")[0]["id"]
        plan = api.wait_job(api.post(f"/api/series/{sid}/plan", {"episodes_count": 5}))["result"]["plan"]
        s = api.post(f"/api/series/{sid}/apply-plan", {"plan": plan})
        out[fmt] = {"page": page["id"], "series": sid, "episodes": [e["id"] for e in s["episodes"]]}
    a = out["anime_whatif"]
    ep = a["episodes"][0]
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-script"))
    r = api.post(f"/api/episodes/{ep}/approve-script")
    api.wait_job(r["job"])
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-storyboard"))
    if api.get("/api/health")["ffmpeg"]:
        api.post(f"/api/episodes/{ep}/produce", {"mode": "preview"})
        end = time.time() + 240
        while time.time() < end and api.get(f"/api/episodes/{ep}")["state"] not in ("ready_for_approval", "quality_review", "failed"):
            time.sleep(1)
    out["api"] = api
    return out


@pytest.fixture(scope="session")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chromium")
        except Exception:  # noqa: BLE001
            b = p.chromium.launch()
        yield b
        b.close()
