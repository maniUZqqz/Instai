"""0.6.0 scheduled downloads: every download can start now / at a time / inside the night window (02:00-07:00 by default); it waits for the
clock AND for its computer, stops cleanly when the window closes and resumes in the next one."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.utils import timezone

from instai.jobs import queue, schedule, workers
from instai.jobs.models import Job, RemoteTask, WorkerNode
from instai.jobs.registry import HANDLERS, handler
from instai.jobs.worker import WorkerRunner
from instai.providers.base import ProviderError
from tests.fakes import wait_until

pytestmark = pytest.mark.django_db(transaction=True)
IRAN = timedelta(hours=3, minutes=30)


@pytest.fixture(autouse=True)
def iran_clock(monkeypatch):
    """The owner's computer: Windows local time = UTC+3:30. `clock.at("2026-11-07 14:00")` sets the local time."""
    monkeypatch.setattr(schedule, "local_offset", lambda at=None: IRAN)

    class Clock:
        now = datetime(2026, 11, 7, 10, 30, tzinfo=dt_timezone.utc)        # 14:00 local

        def at(self, local: str):
            d = datetime.strptime(local, "%Y-%m-%d %H:%M")
            Clock.now = (d - IRAN).replace(tzinfo=dt_timezone.utc)

        def advance(self, **kw):
            Clock.now = Clock.now + timedelta(**kw)
    clock = Clock()
    monkeypatch.setattr(timezone, "now", lambda: Clock.now)
    return clock


@pytest.fixture
def reg():
    added = []

    def add(kind, fn, **kw):
        handler(kind, **kw)(fn)
        added.append(kind)

    yield add
    for k in added:
        HANDLERS.pop(k, None)


def local(dt_utc: datetime) -> str:
    return (dt_utc + IRAN).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ the clock rules

def test_night_window_rules_including_midnight(iran_clock):
    iran_clock.at("2026-11-07 14:00")
    assert not schedule.in_window("02:00-07:00") and schedule.in_window("")
    assert local(schedule.next_window_start("02:00-07:00")) == "2026-11-08 02:00"
    iran_clock.at("2026-11-08 03:15")
    assert schedule.in_window("02:00-07:00") and schedule.next_window_start("02:00-07:00") == timezone.now()
    assert local(schedule.window_end("02:00-07:00")) == "2026-11-08 07:00"
    iran_clock.at("2026-11-08 01:59")
    assert not schedule.in_window("02:00-07:00")
    assert schedule.in_window("22:00-04:00"), "01:59 is inside a window that runs over midnight"
    iran_clock.at("2026-11-08 23:30")
    assert schedule.in_window("22:00-04:00") and local(schedule.window_end("22:00-04:00")) == "2026-11-09 04:00"
    iran_clock.at("2026-11-08 12:00")
    assert not schedule.in_window("22:00-04:00") and local(schedule.next_window_start("22:00-04:00")) == "2026-11-08 22:00"
    assert schedule.parse_window("02:00-02:00") is None and schedule.parse_window("25:00-03:00") is None and schedule.parse_window("abc") is None
    assert schedule.parse_window("۰۲:۰۰-۰۷:۰۰") == (120, 420), "Persian digits are fine"


def test_when_choices_and_their_errors(iran_clock):
    iran_clock.at("2026-11-07 14:00")
    assert schedule.resolve("now") == {"not_before": None, "window": ""}
    r = schedule.resolve("03:30")
    assert local(r["not_before"]) == "2026-11-08 03:30" and r["window"] == ""
    r = schedule.resolve({"mode": "at", "time": "۱۵:۰۰"})
    assert local(r["not_before"]) == "2026-11-07 15:00"
    assert schedule.resolve({"mode": "window"})["window"] == "02:00-07:00", "the default night window"
    assert schedule.resolve({"mode": "window", "window": "01:00-05:00"})["window"] == "01:00-05:00"
    assert schedule.resolve(None) == {"not_before": None, "window": ""}, "the default is 'now' until the owner changes it"
    for bad in ({"mode": "at"}, {"mode": "at", "time": "25:61"}, {"mode": "window", "window": "07:00-07:00"}, {"mode": "later"}, 5):
        with pytest.raises(schedule.ScheduleError) as e:
            schedule.resolve(bad)
        assert any("؀" <= c <= "ۿ" for c in str(e.value)) and e.value.en, "a plain Persian message and an English one"
    from instai.core import settings_store

    settings_store.set_setting("ops_config", {"download_mode": "window", "download_window": "01:00-04:00"})
    assert schedule.resolve(None)["window"] == "01:00-04:00", "the owner's saved default applies when nothing is chosen"
    assert schedule.resolve("now")["window"] == "", "'now' always means now"


# ------------------------------------------------------------------ the API

def test_api_schedules_a_download_for_the_night_and_the_queue_respects_it(api, iran_clock):
    iran_clock.at("2026-11-07 14:00")
    r = api.post("/api/downloads", {"packages": ["ffmpeg"], "when": {"mode": "window"}}, format="json")
    assert r.status_code == 202, r.content
    j = r.json()["job"]
    assert j["window"] == "02:00-07:00" and local(datetime.fromisoformat(j["run_after"].replace("Z", "+00:00"))) == "2026-11-08 02:00"
    assert queue.claim("w", ("net",)) is None, "nothing starts in the afternoon"
    iran_clock.at("2026-11-08 02:00")
    claimed = queue.claim("w", ("net",))
    assert claimed is not None and claimed.pk == j["id"]
    q = api.get("/api/downloads/queue").json()
    assert q["jobs"][0]["is_download"] and q["config"]["download_window"] == "02:00-07:00"


def test_a_window_job_claimed_at_the_wrong_hour_is_pushed_to_the_next_opening(iran_clock):
    iran_clock.at("2026-11-07 14:00")
    job = queue.enqueue("downloads.run", {"packages": []}, window="02:00-07:00")
    assert queue.claim("w", ("net",)) is None
    job.refresh_from_db()
    assert local(job.run_after) == "2026-11-08 02:00" and job.wait_code == "window" and job.attempts == 0


def test_when_at_a_time_starts_exactly_then(api, iran_clock):
    iran_clock.at("2026-11-07 14:00")
    j = api.post("/api/downloads", {"packages": ["ffmpeg"], "when": "15:30"}, format="json").json()["job"]
    assert j["window"] == "" and local(datetime.fromisoformat(j["run_after"].replace("Z", "+00:00"))) == "2026-11-07 15:30"
    assert queue.claim("w", ("net",)) is None
    iran_clock.at("2026-11-07 15:31")
    assert queue.claim("w", ("net",)).pk == j["id"]


def test_bad_time_and_unknown_package_get_plain_persian_errors(api):
    r = api.post("/api/downloads", {"packages": ["ffmpeg"], "when": {"mode": "at", "time": "99:99"}}, format="json")
    assert r.status_code == 400 and "ساعت" in r.json()["error"]["message"]
    assert api.post("/api/downloads", {"packages": ["nope"]}, format="json").status_code == 400
    assert api.post("/api/downloads", {"packages": ["ffmpeg"], "target": "999"}, format="json").status_code == 400


def test_reschedule_and_run_now_only_for_downloads_that_have_not_started(api, iran_clock):
    iran_clock.at("2026-11-07 14:00")
    j = api.post("/api/downloads", {"packages": ["ffmpeg"], "when": {"mode": "window"}}, format="json").json()["job"]
    r = api.post(f"/api/jobs/{j['id']}/schedule", {"when": "20:00"}, format="json")
    assert r.status_code == 200 and r.json()["window"] == "" and local(datetime.fromisoformat(r.json()["run_after"].replace("Z", "+00:00"))) == "2026-11-07 20:00"
    r = api.post(f"/api/jobs/{j['id']}/run-now", {}, format="json")
    assert r.status_code == 200 and r.json()["window"] == ""
    assert queue.claim("w", ("net",)).pk == j["id"]
    assert api.post(f"/api/jobs/{j['id']}/run-now", {}, format="json").status_code == 409, "already running"
    other = queue.enqueue("story.script", {})
    assert api.post(f"/api/jobs/{other.pk}/schedule", {"when": "now"}, format="json").status_code == 400, "only downloads"


def test_ops_config_is_validated_and_saved(api):
    assert api.get("/api/ops/config").json()["download_window"] == "02:00-07:00"
    r = api.put("/api/ops/config", {"download_mode": "window", "download_window": "01:30-05:00", "max_wait_hours": 12, "retention_days": 14}, format="json")
    assert r.status_code == 200 and r.json() == {"download_mode": "window", "download_window": "01:30-05:00", "max_wait_hours": 12.0, "retention_days": 14}
    for bad in ({"download_mode": "x"}, {"download_window": "05:00-05:00"}, {"max_wait_hours": -1}, {"retention_days": 0}):
        assert api.put("/api/ops/config", bad, format="json").status_code == 400
    j = api.post("/api/downloads", {"packages": ["ffmpeg"]}, format="json").json()["job"]
    assert j["window"] == "01:30-05:00", "saved 'night window' mode applies to a download with no explicit time"
    assert api.post("/api/downloads", {"packages": ["python312"], "when": "now"}, format="json").json()["job"]["window"] == ""


# ------------------------------------------------------------------ running: the window closes mid-download, resume in the next one

def test_window_closing_stops_the_download_cleanly_and_the_next_night_resumes(reg, iran_clock):
    iran_clock.at("2026-11-08 06:59")
    progress = {"done": 0, "starts": 0}

    def fake_download(ctx):
        progress["starts"] += 1
        while progress["done"] < 10:                  # like ctx.run_cmd: check() every pass, so the closing window stops the work
            ctx.check()
            progress["done"] += 1
            if progress["done"] == 4:
                iran_clock.at("2026-11-08 07:01")     # the window closes while it is downloading
            time.sleep(0.01)
        return {"installed": ["x"]}
    reg("downloads.test", fake_download, resource="net")
    job = queue.enqueue("downloads.test", {}, window="02:00-07:00", max_attempts=2)
    assert WorkerRunner("w").run_once()
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.attempts == 0, "a closed window is a pause, not a failed attempt"
    assert job.window == "02:00-07:00" and local(job.run_after) == "2026-11-09 02:00" and progress["done"] == 4
    assert not WorkerRunner("w").run_once(), "not before the next night"
    iran_clock.at("2026-11-09 02:00")
    assert WorkerRunner("w").run_once()
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and progress["done"] == 10 and progress["starts"] == 2 and job.attempts == 1


def test_the_real_downloader_process_is_stopped_when_the_window_closes(iran_clock, monkeypatch):
    """downloads.run really starts a subprocess and run_cmd kills it at the window end (a stand-in script replaces download_models.py)."""
    import sys

    from instai.jobs.handlers import downloads as dl

    iran_clock.at("2026-11-08 06:59")
    marker = {}

    class FakeScript:
        pass
    real_run_cmd = None

    def fake_cmd_run(self, cmd, **kw):                      # keep the real run_cmd, but swap the command for a long sleeper
        marker["cmd"] = cmd
        return real_run_cmd(self, [sys.executable, "-c", "import time; time.sleep(60)"], **{k: v for k, v in kw.items() if k != "timeout"}, timeout=30)
    from instai.jobs.context import JobContext

    real_run_cmd = JobContext.run_cmd
    monkeypatch.setattr(JobContext, "run_cmd", fake_cmd_run)
    job = queue.enqueue("downloads.run", {"packages": ["ffmpeg"], "target": "local"}, window="02:00-07:00")
    started = time.time()

    def close_later():
        time.sleep(1.0)
        iran_clock.at("2026-11-08 07:00")
    threading.Thread(target=close_later, daemon=True).start()
    WorkerRunner("w").run_once()
    assert time.time() - started < 20, "the process was killed, not waited for"
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.attempts == 0 and local(job.run_after) == "2026-11-09 02:00", (job.status, job.error)
    assert marker["cmd"][-1] == "--yes" and "download_models.py" in marker["cmd"][1]
    assert dl.ROOT.joinpath("scripts", "download_models.py").is_file()


# ------------------------------------------------------------------ a download for the second PC waits for it

def make_b(online):
    return WorkerNode.objects.create(name="pcb", token_hash=workers.hash_secret("b"), enabled=True, capabilities=["downloads", "gpu"], vram_total_mb=4096,
                                     last_seen=timezone.now() if online else timezone.now() - timedelta(hours=1))


def test_download_for_the_second_pc_waits_while_it_is_off_then_runs(api, iran_clock):
    w = make_b(online=False)
    j = api.post("/api/downloads", {"packages": ["ffmpeg"], "target": str(w.pk), "when": "now"}, format="json").json()["job"]
    assert j["title"].endswith("pcb")
    WorkerRunner("w").run_once()
    job = Job.objects.get(pk=j["id"])
    assert job.status == Job.QUEUED and job.wait_code == "worker_offline" and job.attempts == 0 and "pcb" in job.waiting_reason
    # PC B connects and takes the download
    WorkerNode.objects.filter(pk=w.pk).update(last_seen=timezone.now())
    seen = {}

    def b():
        from django.db import close_old_connections

        end = time.time() + 20
        while time.time() < end:
            t = workers.claim(WorkerNode.objects.get(pk=w.pk))
            if t:
                seen["task"] = (t.kind, t.payload["packages"], t.needs)
                workers.finish(t, w, True, "", True, {"installed": t.payload["packages"]}, 1.0)
                break
            time.sleep(0.05)
        close_old_connections()
    th = threading.Thread(target=b, daemon=True)
    th.start()
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    WorkerRunner("w").run_once()
    th.join(10)
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and job.result["target"] == "pcb", (job.status, job.error)
    assert seen["task"] == ("download.pack", ["ffmpeg"], ["downloads"])


def test_download_for_a_second_pc_with_an_old_program_says_what_to_do(api):
    w = make_b(online=True)
    WorkerNode.objects.filter(pk=w.pk).update(capabilities=["gpu"])
    j = api.post("/api/downloads", {"packages": ["ffmpeg"], "target": str(w.pk)}, format="json").json()["job"]
    WorkerRunner("w").run_once()
    job = Job.objects.get(pk=j["id"])
    assert job.status == Job.FAILED and "قدیمی" in job.error


def test_download_pack_task_runs_the_downloader_on_the_worker_side(tmp_path, monkeypatch):
    """The worker PC's executor: progress from the downloader's percent lines, failure -> a Persian error, cancel kills the process."""
    import sys

    from instai.gpu import executors

    out, inp = tmp_path / "out", tmp_path / "in"
    out.mkdir()
    inp.mkdir()
    seen = []
    io = executors.TaskIO(inp, out, progress=lambda f, t="": seen.append((round(f, 2), t)), cancelled=lambda: False)
    monkeypatch.setattr(executors, "run_download", executors.run_download)
    # stand-in downloader: prints percent lines, exits 0
    script = tmp_path / "fake.py"
    script.write_text("print('x 10%'); print('x 55%'); print('done')", encoding="utf-8")
    import subprocess

    real_popen = subprocess.Popen
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: real_popen([sys.executable, str(script)], **{k: v for k, v in kw.items() if k != "cwd"}))
    assert executors.run("download.pack", {"packages": ["ffmpeg"]}, io) == {"installed": ["ffmpeg"]}
    assert any(f >= 0.5 for f, _ in seen)
    script.write_text("import sys; print('boom'); sys.exit(3)", encoding="utf-8")
    with pytest.raises(ProviderError) as e:
        executors.run("download.pack", {"packages": ["ffmpeg"]}, io)
    assert e.value.code == "download_failed" and e.value.fa
    script.write_text("import time; time.sleep(30)", encoding="utf-8")
    flag = {"stop": False}
    io2 = executors.TaskIO(inp, out, progress=lambda f, t="": None, cancelled=lambda: flag["stop"])
    threading.Timer(0.7, lambda: flag.update(stop=True)).start()
    started = time.time()
    with pytest.raises(executors.TaskCancelled):
        executors.run("download.pack", {"packages": ["ffmpeg"]}, io2)
    assert time.time() - started < 10
    assert executors.run("download.pack", {"packages": ["bad id!"]}, io) == {"installed": []}, "ids that are not plain ids are ignored"


# ------------------------------------------------------------------ Ollama models

def test_ollama_download_goes_through_the_queue_and_waits_for_ollama(api, monkeypatch):
    r = api.post("/api/downloads/ollama", {"model": "qwen3:8b"}, format="json")
    assert r.status_code == 202 and r.json()["job"]["kind"] == "downloads.ollama"
    job = Job.objects.get(pk=r.json()["job"]["id"])
    WorkerRunner("w").run_once()                                     # Ollama (127.0.0.1:9 in tests) is not reachable
    job.refresh_from_db()
    assert job.status == Job.QUEUED and job.wait_code == "ollama_down" and job.attempts == 0
    from instai.providers.ollama import OllamaProvider

    got = []

    def fake_pull(self, model, on_progress=None, should_stop=None):
        for f in (0.2, 0.7, 1.0):
            should_stop()
            on_progress(f, "pulling")
        got.append(model)
        return {"status": "success"}
    monkeypatch.setattr(OllamaProvider, "pull", fake_pull)
    Job.objects.filter(pk=job.pk).update(run_after=timezone.now())
    WorkerRunner("w").run_once()
    job.refresh_from_db()
    assert job.status == Job.SUCCEEDED and got == ["qwen3:8b"]
    assert api.post("/api/downloads/ollama", {"model": "bad name; rm"}, format="json").status_code == 400


def test_ollama_pull_streams_progress_and_stops_on_request():
    """The real OllamaProvider.pull against an in-process fake /api/pull."""
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from instai.providers.ollama import OllamaProvider

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for row in ({"status": "pulling manifest"}, {"status": "pulling abc", "total": 100, "completed": 30}, {"status": "pulling abc", "total": 100, "completed": 100},
                        {"status": "success"}):
                self.wfile.write((json.dumps(row) + "\n").encode())
                self.wfile.flush()

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        prov = OllamaProvider(f"http://127.0.0.1:{srv.server_port}")
        seen = []
        assert prov.pull("qwen3:8b", on_progress=lambda f, t: seen.append(f))["status"] == "success"
        assert seen[0] == 0.0 and 0.3 in seen and 1.0 in seen
        stopped = prov.pull("qwen3:8b", should_stop=lambda: True)
        assert stopped["status"] == "stopped"
    finally:
        srv.shutdown()
    with pytest.raises(ProviderError) as e:
        OllamaProvider("http://127.0.0.1:9").pull("qwen3:8b")
    assert e.value.code == "ollama_down"


def test_catalog_lists_every_downloadable_item_and_the_places_it_can_go(api):
    w = make_b(online=True)
    c = api.get("/api/downloads/catalog").json()
    ids = {p["id"] for p in c["packages"]}
    assert {"ffmpeg", "piper", "wan22", "moss-tts", "acestep", "flux"} <= ids
    assert all(p["title"] for p in c["packages"]) and c["ollama"] and c["config"]["download_window"] == "02:00-07:00"
    assert [t["id"] for t in c["targets"]] == ["local", str(w.pk)]
