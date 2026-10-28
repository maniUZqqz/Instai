from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _reset_state():
    from instai.core import hardware, settings_store
    from instai.providers import registry

    settings_store.clear_cache()
    hardware._CACHE.update(at=0.0, value=None)
    hardware._NODES_CACHE.update(at=0.0, info=None, url=None)
    registry.set_provider_for_tests(None)
    yield
    registry.set_provider_for_tests(None)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def worker():
    from instai.jobs.worker import WorkerRunner

    return WorkerRunner("test-worker")


def run_jobs(worker, limit: int = 50) -> int:
    """Run queued jobs in the test thread (no lanes, no sleeping)."""
    return worker.drain(limit)


@pytest.fixture
def run(worker):
    return lambda: run_jobs(worker)


def finish(api, worker, resp, expect: str = "succeeded") -> dict:
    """Drain the queue and return the finished job of a 202 response."""
    assert resp.status_code in (200, 202), resp.content
    job_id = resp.json()["job"]["id"]
    for _ in range(40):
        run_jobs(worker)
        j = api.get(f"/api/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            break
    assert j["status"] == expect, j
    return j


@pytest.fixture
def ffmpeg_available():
    from instai.core import runtime

    info = runtime.ffmpeg_info()
    if not (info["ffmpeg"] and info["ffprobe"]):
        pytest.skip("ffmpeg not found here; this test runs where START.bat has fetched it (the GPU PC)")
    return info
