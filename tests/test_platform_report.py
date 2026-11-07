"""0.6.0 report of the processing computers: online sessions and gaps, resource samples, jobs per kind with durations and queue wait,
errors explained in Persian, log search, date filter, CSV, the queue page numbers and what PC B sends in its hello."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from instai.jobs import queue, workers
from instai.jobs.models import Job, JobLog, RemoteTask, WorkerNode
from instai.ops import report
from instai.ops.models import NodeEvent, NodeSample, NodeSession

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _fresh():
    report.reset_state()


def add_job(kind="prod.keyframes", status="succeeded", node="", created=None, wait=5.0, dur=60.0, error="", code="", gpu=30.0, devices=None):
    now = created or timezone.now()
    j = Job.objects.create(kind=kind, title=kind, status=status, payload={}, resource="gpu", node=node, error=error, error_code=code)
    first = now + timedelta(seconds=wait)
    Job.objects.filter(pk=j.pk).update(created_at=now, ready_at=now, first_started_at=first, started_at=first,
                                       finished_at=first + timedelta(seconds=dur) if status in ("succeeded", "failed", "cancelled") else None,
                                       duration_sec=dur if status in ("succeeded", "failed", "cancelled") else None, gpu_seconds=gpu,
                                       devices=devices if devices is not None else {(node or "local"): gpu})
    return Job.objects.get(pk=j.pk)


# ------------------------------------------------------------------ sessions: online timeline

def test_sessions_open_extend_and_split_on_a_gap_and_uptime_is_measured():
    t0 = timezone.now() - timedelta(hours=10)
    assert report.record_heartbeat("pcb", version="0.6.0", now=t0, force=True) is True        # came online
    assert report.record_heartbeat("pcb", now=t0 + timedelta(seconds=30), force=True) is False
    report.record_heartbeat("pcb", now=t0 + timedelta(minutes=60), force=True)              # one hour of silence: it was off in between
    report.record_heartbeat("pcb", now=t0 + timedelta(minutes=61), force=True)
    s = list(NodeSession.objects.filter(node="pcb").order_by("started_at"))
    assert len(s) == 2 and s[0].ended_at == s[0].last_seen and s[0].last_seen == t0 + timedelta(seconds=30) and s[1].ended_at is None
    kinds = list(NodeEvent.objects.filter(node="pcb").order_by("at", "id").values_list("kind", flat=True))
    assert kinds == ["online", "offline", "online"]
    rep = report.build_report(t0 - timedelta(hours=1), t0 + timedelta(hours=2), now=t0 + timedelta(hours=2))
    b = next(n for n in rep["nodes"] if n["key"] == "pcb")
    assert len(b["sessions"]) == 2 and b["version"] == "0.6.0"
    assert 0 < b["uptime_pct"] < 5, "about 1.5 minutes online out of 2 hours"
    assert b["online"] is False and b["last_seen"]


def test_a_silent_session_is_closed_by_maintenance_and_shown_offline():
    t0 = timezone.now() - timedelta(minutes=30)
    report.record_heartbeat("local", now=t0, force=True)
    assert NodeSession.objects.get().ended_at is None
    out = report.maintain(force=True)
    assert out["closed"] == 1 and NodeSession.objects.get().ended_at == t0
    from instai.ops import queue_view

    local = next(n for n in queue_view.node_status() if n["key"] == "local")
    assert local["online"] is False


def test_samples_are_throttled_to_one_a_minute_and_distrust_what_a_pc_sends():
    t0 = timezone.now()
    stats = {"gpu_util": 88, "gpu_temp": 71, "vram_used_mb": 9000, "vram_total_mb": 12288, "ram_used_mb": 14000, "ram_total_mb": 24000, "disk_free_gb": 120.5, "disk_total_gb": 500}
    report.record_heartbeat("pcb", stats=stats, now=t0)
    report.record_heartbeat("pcb", stats=stats, now=t0 + timedelta(seconds=20))               # too soon: no new sample
    report.record_heartbeat("pcb", stats={"gpu_util": "garbage", "vram_used_mb": float("nan"), "ram_total_mb": True, "disk_free_gb": -5, "gpu_temp": 500}, now=t0 + timedelta(seconds=70))
    rows = list(NodeSample.objects.order_by("at"))
    assert len(rows) == 2 and rows[0].gpu_util == 88 and rows[0].vram_total_mb == 12288 and rows[0].disk_free_gb == 120.5
    assert rows[1].gpu_util is None and rows[1].vram_used_mb is None and rows[1].ram_total_mb is None and rows[1].disk_free_gb is None and rows[1].gpu_temp is None


def test_upkeep_thins_old_samples_and_deletes_beyond_retention():
    now = timezone.now()
    for m in range(0, 120, 1):                                       # one sample per minute, 3 days ago: raw rows older than 48 h are thinned to one per 15 min
        NodeSample.objects.create(node="pcb", at=now - timedelta(days=3) + timedelta(minutes=m), gpu_util=50)
    NodeSample.objects.create(node="pcb", at=now - timedelta(days=60), gpu_util=1)
    NodeEvent.objects.create(node="pcb", at=now - timedelta(days=60), kind="log", message="old")
    NodeEvent.objects.create(node="pcb", at=now - timedelta(days=1), kind="log", message="recent")
    out = report.maintain(force=True)
    assert out["thinned"] >= 100 and out["deleted"] >= 2
    left = NodeSample.objects.filter(at__gte=now - timedelta(days=4)).count()
    assert 7 <= left <= 10, left
    assert list(NodeEvent.objects.values_list("message", flat=True)) == ["recent"]


# ------------------------------------------------------------------ jobs, durations, queue wait, errors

def test_report_numbers_per_computer_per_kind_with_wait_and_the_date_filter():
    now = timezone.now()
    report.record_heartbeat("pcb", now=now, force=True)
    WorkerNode.objects.create(name="pcb", token_hash="x", enabled=True)
    add_job("prod.keyframes", "succeeded", node="", dur=100, wait=10)
    add_job("prod.keyframes", "succeeded", node="", dur=200, wait=30)
    add_job("prod.keyframes", "failed", node="", dur=5, wait=2, error="Ollama is not reachable at http://127.0.0.1:11434", code="ollama_down")
    add_job("prod.clips", "succeeded", node="pcb", dur=600, wait=60, devices={"pcb": 580, "local": 20})
    add_job("prod.clips", "cancelled", node="pcb", dur=3, wait=1)
    add_job("prod.tts", "succeeded", created=now - timedelta(days=20), dur=9)                 # outside a 7-day window
    rep = report.build_report(now - timedelta(days=7), now + timedelta(minutes=1), now=now)
    t = rep["totals"]
    assert (t["jobs"], t["succeeded"], t["failed"], t["cancelled"]) == (5, 3, 1, 1)
    a = next(n for n in rep["nodes"] if n["key"] == "local")
    b = next(n for n in rep["nodes"] if n["key"] == "pcb")
    assert a["jobs"]["total"] == 3 and b["jobs"]["total"] == 2
    kf = next(k for k in a["by_kind"] if k["kind"] == "prod.keyframes")
    assert (kf["total"], kf["succeeded"], kf["failed"]) == (3, 2, 1)
    assert kf["duration"]["avg"] == 150.0 and kf["wait"]["max"] == 30.0 and kf["title_fa"] == "ساخت تصویرهای کلیدی" and kf["title_en"]
    assert b["jobs"]["gpu_seconds"] >= 580 and a["jobs"]["gpu_seconds"] >= 30
    wide = report.build_report(now - timedelta(days=30), now + timedelta(minutes=1), now=now)
    assert wide["totals"]["jobs"] == 6


def test_errors_are_explained_in_plain_persian_with_advice():
    now = timezone.now()
    add_job(status="failed", error="Ollama is not reachable at http://x", code="ollama_down")
    add_job(status="failed", error="CUDA out of memory. Tried to allocate 2 GiB", code="gpu_oom")
    add_job(status="failed", error="worker stopped before the job finished (it did so repeatedly)", code="lease_expired")
    add_job(status="failed", error="something nobody has seen before", code="")
    add_job(status="failed", error="Ollama is not reachable again", code="ollama_down")
    rep = report.build_report(now - timedelta(days=1), now + timedelta(minutes=1), now=now)
    by = {g["code"]: g for g in rep["errors"]}
    assert by["ollama_down"]["count"] == 2 and "Ollama" in by["ollama_down"]["what_fa"] and by["ollama_down"]["advice_fa"]
    assert by["out_of_memory"]["what_fa"] and by["out_of_memory"]["what_en"] and by["lease_expired"]["known"]
    assert by["unknown"]["known"] is False and by["unknown"]["what_fa"].startswith("خطای ناشناخته")
    assert rep["errors"][0]["code"] == "ollama_down", "the most frequent first"
    for g in rep["errors"]:
        assert any("؀" <= c <= "ۿ" for c in g["what_fa"] + g["advice_fa"]) and g["what_en"].isascii() and g["advice_en"].isascii()


def test_remote_task_statistics_of_the_worker_pc():
    now = timezone.now()
    w = WorkerNode.objects.create(name="pcb", token_hash="x", enabled=True)
    RemoteTask.objects.create(kind="comfy.graph", status="succeeded", worker=w, seconds=120)
    RemoteTask.objects.create(kind="comfy.graph", status="failed", worker=w, error="boom", error_code="")
    RemoteTask.objects.create(kind="voice.tts", status="failed", worker=w, error="worker stopped sending heartbeats", error_code="worker_lost")
    rep = report.build_report(now - timedelta(days=1), now + timedelta(minutes=1), now=now)
    b = next(n for n in rep["nodes"] if n["key"] == "pcb")
    tk = {t["kind"]: t for t in b["tasks"]}
    assert tk["comfy.graph"]["total"] == 2 and tk["comfy.graph"]["succeeded"] == 1 and tk["comfy.graph"]["duration"]["avg"] == 120.0
    assert tk["voice.tts"]["lost"] == 1
    assert {g["code"] for g in rep["errors"]} >= {"worker_offline"}


# ------------------------------------------------------------------ logs with search, CSV

def test_log_search_by_text_level_computer_and_date():
    now = timezone.now()
    j = add_job("prod.clips", "failed", node="pcb", error="x")
    JobLog.objects.create(job=j, level="info", message="started (attempt 1/3) by w")
    JobLog.objects.create(job=j, level="error", message="failed: CUDA out of memory")
    old = JobLog.objects.create(job=j, level="error", message="failed: ancient CUDA story")
    JobLog.objects.filter(pk=old.pk).update(at=now - timedelta(days=30))
    NodeEvent.objects.create(node="pcb", at=now, level="warning", kind="log", message="agent: ComfyUI did not answer")
    NodeEvent.objects.create(node="pcb", at=now, kind="offline", data={})
    start, end = now - timedelta(days=2), now + timedelta(minutes=1)
    r = report.search_logs({"q": "cuda"}, start, end)
    assert [x["message"] for x in r] == ["failed: CUDA out of memory"] and r[0]["node"] == "pcb" and r[0]["explain"]["code"] == "out_of_memory"
    assert len(report.search_logs({"level": "error"}, start, end)) == 1
    assert len(report.search_logs({"source": "events"}, start, end)) == 2
    assert len(report.search_logs({"q": "ComfyUI", "source": "events"}, start, end)) == 1
    assert len(report.search_logs({"node": "pcb", "source": "jobs"}, start, end)) == 2 and len(report.search_logs({"node": "local", "source": "jobs"}, start, end)) == 0
    off = [x for x in report.search_logs({"source": "events"}, start, end) if x["kind"] == "offline"][0]
    assert "آفلاین" in off["text_fa"] and "offline" in off["text_en"]
    wide = report.search_logs({"q": "ancient"}, now - timedelta(days=60), end)
    assert len(wide) == 1


def test_csv_export_is_excel_friendly_and_has_the_numbers(api):
    now = timezone.now()
    add_job("prod.keyframes", "failed", error="CUDA out of memory", code="gpu_oom", wait=7, dur=11)
    add_job("prod.clips", "succeeded", node="pcb")
    r = api.get("/api/reports/export.csv?section=jobs&days=1")
    assert r.status_code == 200 and r["Content-Type"].startswith("text/csv") and "attachment" in r["Content-Disposition"]
    body = r.content.decode("utf-8")
    assert body.startswith("﻿"), "BOM so Excel shows Persian right"
    rows = list(csv.DictReader(io.StringIO(body.lstrip("﻿"))))
    assert len(rows) == 2 and rows[0]["kind"] == "prod.keyframes" and rows[0]["queue_wait_sec"] == "7.0" and rows[0]["error_explained"].startswith("حافظه")
    assert rows[1]["computer"] == "pcb"
    for section in report.CSV_SECTIONS:
        rr = api.get(f"/api/reports/export.csv?section={section}&days=1")
        assert rr.status_code == 200 and rr.content.decode("utf-8").startswith("﻿"), section
    assert api.get("/api/reports/export.csv?section=passwords").status_code == 400


def test_csv_cells_that_look_like_formulas_are_neutralised(api):
    add_job("prod.keyframes", "failed", error='=HYPERLINK("http://evil","x")', code="x")
    add_job("prod.clips", "failed", error="+cmd|' /C calc'!A0", code="y")
    rows = list(csv.DictReader(io.StringIO(api.get("/api/reports/export.csv?section=jobs&days=1").content.decode("utf-8").lstrip("﻿"))))
    assert rows[0]["error"].startswith("'=") and rows[1]["error"].startswith("'+")
    assert all(not r["error"].startswith(("=", "+", "-", "@")) for r in rows)


def test_report_api_date_filter_and_shapes(api):
    now = timezone.now()
    add_job()
    add_job(created=now - timedelta(days=10))
    j7 = api.get("/api/reports/compute?days=7").json()
    assert j7["totals"]["jobs"] == 1 and [n["key"] for n in j7["nodes"]] == ["local"] and j7["range"]["days"] == 7.0
    day = (now - timedelta(days=11)).strftime("%Y-%m-%d")
    wide = api.get(f"/api/reports/compute?from={day}&to={now.strftime('%Y-%m-%d')}").json()
    assert wide["totals"]["jobs"] == 2
    logs = api.get("/api/reports/logs?q=zzz").json()
    assert logs["count"] == 0 and "range" in logs


# ------------------------------------------------------------------ queue page numbers

def test_queue_page_states_waiting_for_a_computer_scheduled_and_in_line(api):
    now = timezone.now()
    w = WorkerNode.objects.create(name="pcb", token_hash="x", enabled=True, last_seen=now - timedelta(hours=1))
    waiting = queue.enqueue("prod.clips", {}, resource="gpu")
    Job.objects.filter(pk=waiting.pk).update(wait_code="worker_offline", waiting_since=now - timedelta(minutes=12), waiting_reason="x", run_after=now + timedelta(seconds=30))
    first = queue.enqueue("prod.keyframes", {}, resource="gpu")
    second = queue.enqueue("prod.keyframes", {}, resource="gpu")
    sched = queue.enqueue("downloads.run", {"packages": ["ffmpeg"]}, run_after=now + timedelta(hours=3))
    night = queue.enqueue("downloads.run", {"packages": ["ffmpeg"]}, window="02:00-07:00")
    Job.objects.filter(pk=night.pk).update(run_after=now + timedelta(hours=1))
    s = api.get("/api/queue/summary").json()
    assert s["waiting_node"] == 1 and s["waiting"] == 1 and s["waiting_turn"] == 2 and s["scheduled"] == 2 and s["offline_nodes"] == ["pcb"]
    q = api.get("/api/queue").json()
    st = {r["id"]: r for r in q["active"]}
    assert st[waiting.pk]["state"] == "waiting_node" and "pcb" in st[waiting.pk]["state_fa"] and "۱۲" in st[waiting.pk]["state_fa"]
    assert st[first.pk]["state"] == "waiting_turn" and st[first.pk]["position"] == 1 and st[second.pk]["position"] == 2 and "نفر ۲" in st[second.pk]["state_fa"]
    assert st[sched.pk]["state"] == "scheduled" and "زمان‌بندی‌شده" in st[sched.pk]["state_fa"] and st[sched.pk]["is_download"]
    assert st[night.pk]["state"] == "window" and st[night.pk]["can_run_now"]
    assert st[waiting.pk]["can_cancel"] and not st[waiting.pk]["can_retry"]
    assert [n["key"] for n in q["nodes"]] == ["local", "pcb"] and q["nodes"][1]["online"] is False
    assert q["active"][0]["state"] == "waiting_node", "waiting-for-a-computer jobs are shown first, after the running ones"
    api.post(f"/api/jobs/{waiting.pk}/cancel", {}, format="json")
    assert api.get("/api/queue/summary").json()["waiting_node"] == 0


# ------------------------------------------------------------------ what PC B sends

def test_hello_of_pc_b_records_the_session_sample_version_and_its_log_lines():
    c = Client()
    code, _ = workers.new_pairing_code()
    token = c.post("/api/worker/pair", data={"code": code, "name": "pc-b", "info": {}}, content_type="application/json").json()["token"]
    body = {"gpu": {"name": "GTX 1650", "total_mb": 4096, "free_mb": 3500}, "caps": ["gpu", "downloads"], "models": {},
            "stats": {"gpu_util": 12, "vram_used_mb": 500, "vram_total_mb": 4096, "ram_used_mb": 8000, "ram_total_mb": 23000, "disk_free_gb": 90},
            "log": [{"at": timezone.now().timestamp(), "level": "warning", "message": "ComfyUI did not answer; retrying"}, {"level": "info", "message": ""}, "junk"],
            "info": {"agent": "1.0", "instai": "0.6.0", "host": "PC-B", "gpu_name": "GTX 1650"}}
    r = c.post("/api/worker/hello", data=body, content_type="application/json", HTTP_AUTHORIZATION=f"Worker {token}")
    assert r.status_code == 200
    s = NodeSession.objects.get(node="pc-b")
    assert s.version == "0.6.0" and s.info["gpu_name"] == "GTX 1650" and NodeSample.objects.get(node="pc-b").vram_total_mb == 4096
    ev = NodeEvent.objects.filter(node="pc-b", kind="log").get()
    assert ev.message == "ComfyUI did not answer; retrying" and ev.level == "warning"
    assert NodeEvent.objects.filter(node="pc-b", kind="online").count() == 1
    rep = report.build_report(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1))
    b = next(n for n in rep["nodes"] if n["key"] == "pc-b")
    assert b["online"] and b["version"] == "0.6.0" and b["gpu_name"] == "GTX 1650" and b["current"]["vram_total_mb"] == 4096
    assert rep["versions"]["main"] == b["version"] or rep["versions"]["workers"]["pc-b"] == "0.6.0"
