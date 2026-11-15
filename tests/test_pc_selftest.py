"""The automatic self-test of THIS PC (0.14.0): real small checks, each judged on its own; what cannot run yet WAITS with a reason and runs by itself the moment it can;
the report is kept, the API shows and starts it, and it queues itself per version and when a requirement appears."""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from instai.ops import pcselftest as st
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)

PC_KEYS = ["database", "disk", "ffmpeg", "persian_text", "captions", "update_channel", "autostart"]
GPU_KEYS = ["gpu_card", "nvenc", "ollama_run", "comfyui"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    shutil.rmtree(st.report_path().parent, ignore_errors=True)
    st._LAST_AUTO[0] = 0.0
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: "")          # never the network in the test suite
    from instai.jobs.handlers import remotion as rh

    kicked = []
    monkeypatch.setattr(rh, "kick_setup", lambda: kicked.append(1))              # never a real Node.js install from a test
    st._TEST_KICKS = kicked
    yield
    shutil.rmtree(st.report_path().parent, ignore_errors=True)


def rows(rep):
    return {r["key"]: r for r in rep["checks"]}


def ctx():
    return SimpleNamespace(check=lambda: None, progress=lambda *a, **k: None, live=lambda *a, **k: None)


def no_gpu(monkeypatch):
    from instai.core import gpu_diag, hardware

    monkeypatch.setattr(hardware, "gpu_status", lambda: None)
    monkeypatch.setattr(gpu_diag, "probe_ollama", lambda: None)


GPU = {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": 900, "free_mb": 11000, "driver": "576.02", "utilization": 3, "temperature": 40, "processes": []}


# ------------------------------------------------------------------------------------------------------------------------------ the cheap checks

def test_the_cheap_checks_run_for_real_and_say_what_they_saw(ffmpeg_available, monkeypatch):
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: st.stamp())      # GitHub has the same version
    rep = st.run(ctx(), gpu=False, only=PC_KEYS)
    r = rows(rep)
    assert [x["key"] for x in rep["checks"]] == PC_KEYS
    assert r["database"]["verdict"] == "ok" and r["database"]["metrics"]["journal"] == "wal"
    assert r["disk"]["verdict"] in ("ok", "warn") and r["disk"]["metrics"]["free_gb"]
    assert r["ffmpeg"]["verdict"] in ("ok", "warn"), r["ffmpeg"]["reason_en"]
    assert r["ffmpeg"]["metrics"]["version"] and r["ffmpeg"]["seconds"] >= 0
    assert r["persian_text"]["verdict"] == "ok" and r["persian_text"]["metrics"]["ink"] > 400
    assert r["captions"]["verdict"] == "ok", r["captions"]["reason_en"]               # seven presets x two frame shapes through the real libass, ink inside the safe zone
    assert r["captions"]["metrics"]["samples"] == 14
    assert r["update_channel"]["verdict"] == "ok" and r["update_channel"]["metrics"]["start_bat_has_updater"] is True
    assert r["autostart"]["verdict"] in ("ok", "warn", "skip")
    assert rep["ok"] and st.load_report()["stamp"] == st.stamp() and rep["machine"]["python"]
    for x in rep["checks"]:
        assert x["reason_fa"] and x["reason_en"] and x["at"] and x["stamp"] == st.stamp()


def test_the_persian_reasons_write_their_numbers_in_persian_digits(monkeypatch):
    from instai.core import hardware

    monkeypatch.setattr(hardware, "disk_info", lambda p: {"free_gb": 12.5, "total_gb": 100})
    row = st.check_disk(None)
    assert row["verdict"] == "warn" and "۱۲٫۵" in row["reason_fa"] and "12.5" in row["reason_en"]
    assert not re.search(r"[0-9]", row["reason_fa"])
    monkeypatch.setattr(hardware, "disk_info", lambda p: {"free_gb": 1.2, "total_gb": 100})
    assert st.check_disk(None)["verdict"] == "fail"
    monkeypatch.setattr(hardware, "disk_info", lambda p: {"free_gb": 250.0, "total_gb": 500})
    assert st.check_disk(None)["verdict"] == "ok"
    assert st._fd(12.5) == "۱۲٫۵"


def test_a_missing_ffmpeg_is_a_failure_with_the_fix(monkeypatch, tmp_path):
    from instai.core import runtime

    monkeypatch.setattr(runtime, "ffmpeg_info", lambda: {"ffmpeg": None, "ffprobe": None, "version": None, "features": {}})
    row = st.check_ffmpeg_encode(tmp_path)
    assert row["verdict"] == "fail" and "START.bat" in row["reason_fa"]


def test_ffmpeg_that_cannot_encode_is_a_failure_and_one_without_features_a_warning(monkeypatch, tmp_path):
    from instai.core import runtime

    feats = {"libx264": True, "ass": True, "zoompan": True, "xfade": True}
    monkeypatch.setattr(runtime, "ffmpeg_info", lambda: {"ffmpeg": "ffmpeg", "ffprobe": None, "version": "7.1", "features": feats})
    monkeypatch.setattr(st, "_ffmpeg_encode", lambda ff, out, codec, timeout=90: (False, "Unknown encoder 'libx264'", 0.1))
    assert st.check_ffmpeg_encode(tmp_path)["verdict"] == "fail"

    def good(ff, out, codec, timeout=90):
        out.write_bytes(b"x" * 4000)
        return True, "", 0.31

    monkeypatch.setattr(st, "_ffmpeg_encode", good)
    ok = st.check_ffmpeg_encode(tmp_path)
    assert ok["verdict"] == "ok" and "۰٫۳۱" in ok["reason_fa"]
    monkeypatch.setattr(runtime, "ffmpeg_info", lambda: {"ffmpeg": "ffmpeg", "ffprobe": None, "version": "7.1", "features": {**feats, "xfade": False}})
    warn = st.check_ffmpeg_encode(tmp_path)
    assert warn["verdict"] == "warn" and warn["metrics"]["missing"] == ["xfade"]


def test_a_missing_persian_font_fails_the_text_check(monkeypatch, tmp_path):
    from PIL import ImageFont

    from instai.render import fa_text

    monkeypatch.setattr(fa_text, "font", lambda size, bold=False, **k: ImageFont.load_default())
    row = st.check_persian_text(tmp_path)
    assert row["verdict"] == "fail" and "Vazirmatn" in row["reason_fa"]


# ------------------------------------------------------------------------------------------------------------------------------ the update channel

def test_an_old_folder_whose_start_bat_cannot_update_is_told_what_to_do(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "_read_start_bat", lambda: "@echo off\r\ncall scripts\\bootstrap.py\r\n")             # an old Download-ZIP START.bat: no updater line
    row = st.check_update_channel(tmp_path)
    assert row["verdict"] == "warn" and row["metrics"]["start_bat_has_updater"] is False
    assert "ZIP" in row["reason_fa"] and "NMarketing" in row["reason_fa"] and "cannot update itself" in row["reason_en"]
    monkeypatch.setattr(st, "_read_start_bat", lambda: "")
    assert st.check_update_channel(tmp_path)["verdict"] == "warn"


def test_the_update_channel_compares_with_github_in_every_direction(monkeypatch, tmp_path):
    local = st.stamp()
    major, minor, patch = (int(x) for x in local.split("."))
    newer, older = f"{major}.{minor + 1}.0", f"{major}.{max(minor - 1, 0)}.{patch + 5}" if minor else f"{major}.0.0"
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: local)
    assert st.check_update_channel(tmp_path)["verdict"] == "ok"
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: newer)
    r = st.check_update_channel(tmp_path)
    assert r["verdict"] == "warn" and newer in r["reason_fa"] and "STOP.bat" in r["reason_fa"]
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: f"{major}.{minor}.0" if patch else f"{major}.{max(minor - 1, 0)}.0")
    ahead = st.check_update_channel(tmp_path)
    if patch or minor:                                                               # the working copy is ahead of GitHub (the improvements were not pushed)
        assert ahead["verdict"] == "warn" and "not pushed" in ahead["reason_en"]
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: "")
    off = st.check_update_channel(tmp_path)
    assert off["verdict"] == "warn" and "GitHub" in off["reason_fa"] and off["metrics"]["github"] == ""


def test_the_remote_version_is_read_from_a_raw_file_and_garbage_is_ignored(monkeypatch):
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        body = b"1.2.3\n"

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.undo()                                                           # the autouse stub of the network is not wanted here
    monkeypatch.setenv("INSTAI_UPDATE_RAW", f"http://127.0.0.1:{srv.server_port}")
    try:
        assert st._remote_version(3) == "1.2.3"
        H.body = b"<html>not a version</html>"
        assert st._remote_version(3) == ""
    finally:
        srv.shutdown()
    monkeypatch.setenv("INSTAI_UPDATE_RAW", "http://127.0.0.1:9")
    assert st._remote_version(1) == ""                                           # no server: empty, never an exception


# ------------------------------------------------------------------------------------------------------------------------------ Remotion

def test_remotion_waits_while_it_installs_and_starts_the_install_by_itself(monkeypatch, tmp_path):
    from instai.remotion import toolchain

    base = {"ready": False, "node": None, "packages": False, "browser": None, "state": "idle", "phase": "", "message_fa": "", "message_en": "", "error": "", "auto": True}
    monkeypatch.setattr(toolchain, "status", lambda: dict(base))
    row = st.check_remotion_toolchain(tmp_path)
    assert row["verdict"] == "pending" and "خودش نصب می‌شود" in row["reason_fa"]
    assert st._TEST_KICKS == [1]                                                  # the idempotent background setup was started
    monkeypatch.setattr(toolchain, "status", lambda: {**base, "state": "running", "message_fa": "در حال دانلود Node.js (۴۰٪)"})
    r2 = st.check_remotion_toolchain(tmp_path)
    assert r2["verdict"] == "pending" and "Node.js" in r2["reason_fa"] and st._TEST_KICKS == [1]    # already running: not started again
    monkeypatch.setattr(toolchain, "status", lambda: {**base, "state": "error", "error": "npm ERR! network"})
    assert st.check_remotion_toolchain(tmp_path)["verdict"] == "fail"
    monkeypatch.setattr(toolchain, "status", lambda: {**base, "ready": True, "state": "ready", "node": {"path": "node", "version": "24.2.0"}, "packages": True, "browser": {"path": "chrome", "mode": "x"}})
    assert st.check_remotion_toolchain(tmp_path)["verdict"] == "ok"


def test_the_remotion_render_check_judges_the_frame(monkeypatch, tmp_path):
    from instai.jobs.handlers import remotion as rh
    from instai.remotion import toolchain

    monkeypatch.setattr(toolchain, "status", lambda: {"ready": False})
    assert st.check_remotion_render(tmp_path)["verdict"] == "pending"
    monkeypatch.setattr(toolchain, "status", lambda: {"ready": True, "node": {"path": "node", "version": "24"}, "browser": {"path": "chrome", "mode": "headless-shell"}})
    mode = {"ok": True}

    def fake_run(cmd, **kw):
        import json as _j

        spec = _j.loads(open(cmd[2], encoding="utf-8").read())
        assert spec["composition"] == "TitleCard" and spec["still"] == 30 and spec["props"]["size"] == "square" and spec["props"]["title"] == "آزمون خودکار"
        if mode["ok"]:
            open(spec["out"], "wb").write(b"\x89PNG" + b"0" * 9000)
            out = rh.EVENT + '{"event":"composition","id":"TitleCard","width":1080,"height":1080,"fps":30,"frames":150}\n' + rh.EVENT + '{"event":"done"}\n'
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        return SimpleNamespace(returncode=1, stdout=rh.EVENT + '{"event":"error","message":"Failed to launch the browser"}\n', stderr="")

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    ok = st.check_remotion_render(tmp_path)
    assert ok["verdict"] == "ok" and ok["metrics"]["width"] == 1080 and "۱۰۸۰×۱۰۸۰" in ok["reason_fa"]
    mode["ok"] = False
    bad = st.check_remotion_render(tmp_path)
    assert bad["verdict"] == "fail" and "مرورگر" in bad["reason_fa"]               # the known error is explained in plain Persian


# ------------------------------------------------------------------------------------------------------------------------------ the GPU checks

def test_without_a_gpu_pc_every_gpu_check_waits_with_a_reason_and_nothing_fails(monkeypatch):
    no_gpu(monkeypatch)
    rep = st.run(ctx(), gpu=True, only=GPU_KEYS)
    r = rows(rep)
    assert [r[k]["verdict"] for k in GPU_KEYS] == ["pending"] * 4, {k: r[k]["reason_en"] for k in GPU_KEYS}
    assert "GPU PC" in r["gpu_card"]["reason_en"] and "رایانهٔ GPU" in r["gpu_card"]["reason_fa"] and rep["ok"]
    assert rep["summary"]["state"] == "waiting" and rep["summary"]["pending"] == 4
    assert not any(r[k]["ready"] for k in GPU_KEYS)                                # nothing was ready: the automatic start knows to try again when something is


def test_the_gpu_checks_pass_on_a_working_gpu_pc(monkeypatch, tmp_path):
    from instai.core import gpu_diag, hardware, runtime
    from instai.providers.comfy import launcher

    monkeypatch.setattr(hardware, "gpu_status", lambda: GPU)
    assert st.check_gpu_card(tmp_path)["verdict"] == "ok" and "۱۲" in st.check_gpu_card(tmp_path)["reason_fa"]
    monkeypatch.setattr(hardware, "gpu_status", lambda: {**GPU, "total_mb": 6144})
    assert st.check_gpu_card(tmp_path)["verdict"] == "warn"
    monkeypatch.setattr(hardware, "gpu_status", lambda: GPU)
    # NVENC
    monkeypatch.setattr(runtime, "ffmpeg_info", lambda: {"ffmpeg": "ffmpeg", "version": "7", "features": {}})
    monkeypatch.setattr(st, "_nvenc_listed", lambda ff: False)
    assert st.check_nvenc(tmp_path)["verdict"] == "warn"
    monkeypatch.setattr(st, "_nvenc_listed", lambda ff: True)
    monkeypatch.setattr(st, "_ffmpeg_encode", lambda ff, out, codec, timeout=90: (codec == "h264_nvenc", "driver too old", 0.2))
    assert st.check_nvenc(tmp_path)["verdict"] == "ok"
    monkeypatch.setattr(st, "_ffmpeg_encode", lambda ff, out, codec, timeout=90: (False, "driver too old", 0.2))
    assert st.check_nvenc(tmp_path)["verdict"] == "warn"
    # the owner's Ollama model on the GPU
    good = gpu_diag._check("ollama_run", "ok", "اجرای آزمایشی: مدل کامل روی کارت گرافیک اجرا شد", "Trial run: the model ran completely on the graphics card", "مدل qwen3:8b: ۱۰۰٪ روی GPU", "model qwen3:8b: 100% on the GPU")
    monkeypatch.setattr(gpu_diag, "probe_ollama", lambda: good)
    o = st.check_ollama_run(tmp_path)
    assert o["verdict"] == "ok" and "qwen3:8b" in o["reason_en"]
    monkeypatch.setattr(gpu_diag, "probe_ollama", lambda: gpu_diag._check("ollama_run", "warn", "بخشی روی CPU", "part on the CPU", "", "", "مدل کوچک‌تر", "a smaller model"))
    assert st.check_ollama_run(tmp_path)["verdict"] == "warn"
    monkeypatch.setattr(gpu_diag, "probe_ollama", lambda: gpu_diag._check("ollama_run", "bad", "روی CPU", "on the CPU"))
    assert st.check_ollama_run(tmp_path)["verdict"] == "fail"
    monkeypatch.setattr(gpu_diag, "probe_ollama", lambda: None)
    assert st.check_ollama_run(tmp_path)["verdict"] == "pending"
    # ComfyUI: started the way a job starts it, asked about its card and workflows
    monkeypatch.setattr(launcher, "ensure_running", lambda progress=None, cancelled=None, timeout=420: "http://127.0.0.1:8188")
    monkeypatch.setattr(launcher, "device_info", lambda url, timeout=4.0: {"type": "cuda", "name": "cuda:0 NVIDIA GeForce RTX 3060", "version": "0.3.60"})
    wf = [{"id": "flux_dev_fp8_t2i", "available": True}, {"id": "wan", "available": False}]
    monkeypatch.setattr(hardware, "check_comfyui", lambda url=None: {"data": {"node_count": 900, "workflows": wf}})
    c = st.check_comfyui(tmp_path)
    assert c["verdict"] == "ok" and c["metrics"]["workflows_ready"] == 1 and "RTX 3060" in c["reason_en"]
    monkeypatch.setattr(hardware, "check_comfyui", lambda url=None: {"data": {"node_count": 900, "workflows": [{"id": "x", "available": False}]}})
    assert st.check_comfyui(tmp_path)["verdict"] == "warn"


def test_comfyui_that_works_on_the_cpu_fails_and_one_that_will_not_start_waits(monkeypatch, tmp_path):
    from instai.core import hardware
    from instai.providers.base import ProviderError
    from instai.providers.comfy import launcher

    monkeypatch.setattr(hardware, "gpu_status", lambda: GPU)

    def cpu(progress=None, cancelled=None, timeout=420):
        raise ProviderError("ComfyUI runs on the CPU", retryable=False, code="comfy_on_cpu", fa="ComfyUI روی پردازنده کار می‌کند.")

    monkeypatch.setattr(launcher, "ensure_running", cpu)
    r = st.check_comfyui(tmp_path)
    assert r["verdict"] == "fail" and "پردازنده" in r["reason_fa"]

    def down(progress=None, cancelled=None, timeout=420):
        raise ProviderError("not found", retryable=False, code="not_ready", wait="comfy_down", fa="ComfyUI روشن نیست.")

    monkeypatch.setattr(launcher, "ensure_running", down)
    assert st.check_comfyui(tmp_path)["verdict"] == "pending"
    # the loop turns a ProviderError of any check into "waiting", never a crash
    monkeypatch.setitem(st.BY_KEY["ollama_run"], "fn", lambda work: (_ for _ in ()).throw(ProviderError("Ollama down", fa="Ollama روشن نیست.")))
    rep = st.run(None, gpu=True, only=["ollama_run"])
    assert rows(rep)["ollama_run"]["verdict"] == "pending" and rep["ok"]


def test_a_broken_check_is_a_result_not_a_crash(monkeypatch):
    def boom(work):
        raise RuntimeError("kaput")

    monkeypatch.setitem(st.BY_KEY["disk"], "fn", boom)
    rep = st.run(None, gpu=False, only=["disk"])
    r = rows(rep)["disk"]
    assert r["verdict"] == "fail" and "kaput" in r["reason_en"] and rep["ok"] is False and rep["summary"]["state"] == "problems"


def test_a_run_without_the_gpu_keeps_the_gpu_rows_and_a_partial_run_keeps_the_rest(monkeypatch):
    no_gpu(monkeypatch)
    first = st.run(None, gpu=True, only=["gpu_card", "database"])
    again = st.run(None, gpu=False, only=["gpu_card", "database"])                  # gpu=False: the old GPU row is kept as it was, the cheap one is made again
    assert rows(again)["gpu_card"]["at"] == rows(first)["gpu_card"]["at"]
    part = st.run(None, gpu=False, only=["disk"])
    assert [x["key"] for x in part["checks"]] == ["database", "disk", "gpu_card"]       # the rows of the checks that were not asked for are kept, in the catalogue's order
    assert part["summary"]["ok"] + part["summary"]["warn"] >= 2


# ------------------------------------------------------------------------------------------------------------------------------ by itself

def test_due_rules_per_check():
    cur = st.stamp()
    now = datetime.now(timezone.utc)
    at = lambda s: (now - timedelta(seconds=s)).isoformat(timespec="seconds")                       # noqa: E731
    row = lambda key, group, verdict, age, **kw: {"key": key, "group": group, "verdict": verdict, "at": at(age), "stamp": kw.pop("stamp", cur), **kw}   # noqa: E731
    allr = [c["key"] for c in st.CHECKS]
    assert st.due({"checks": []}, cur, allr) == allr                                                  # never ran: everything that can run
    assert st.due({"checks": []}, cur, []) == []                                                      # nothing ready: nothing
    rep = {"checks": [row("gpu_card", "gpu", "pending", 60, ready=False), row("nvenc", "gpu", "pending", 60, ready=True),
                      row("database", "pc", "ok", 60), row("disk", "pc", "ok", st.REFRESH_BASE_S + 5), row("ffmpeg", "pc", "ok", 60, stamp="0.0.1"),
                      row("persian_text", "pc", "warn", 60), row("update_channel", "pc", "fail", st.RETRY_PROBLEM_S + 5),
                      row("remotion_render", "tools", "ok", 60), row("comfyui", "gpu", "ok", 60, stamp="0.0.1"), row("ollama_run", "gpu", "ok", st.REFRESH_HEAVY_S + 5)]}
    got = st.due(rep, cur, allr)
    assert "gpu_card" in got                                    # it waited while NOT ready; the situation changed: at once
    assert "nvenc" not in got                                   # it waited although ready a minute ago: not hammered
    assert "database" not in got and "persian_text" not in got  # fresh, and a warning is looked at again only after an hour
    assert "disk" in got                                        # a day old
    assert "ffmpeg" in got                                      # a result of an older version: the cheap checks at once
    assert "update_channel" in got                              # a failure is looked at again after an hour
    assert "remotion_render" not in got and "comfyui" not in got   # the heavy ones wait six hours after a new version
    assert "ollama_run" in got                                  # a week old
    rep["checks"][8]["at"] = at(st.VERSION_RETRY_S + 5)
    assert "comfyui" in st.due(rep, cur, allr)


def test_it_queues_itself_once_per_version_and_again_when_a_requirement_appears(monkeypatch):
    from instai.jobs.models import Job

    no_gpu(monkeypatch)
    monkeypatch.setattr(st, "ready_keys", lambda: PC_KEYS + ["remotion_toolchain"])
    assert st.auto_queue() is None                                                  # the test suite never gets surprise jobs
    j = st.auto_queue(force=True)
    assert j is not None and j.kind == "system.selftest" and j.payload["gpu"] is False and j.payload["only"] == PC_KEYS + ["remotion_toolchain"] and j.payload["auto"] is True
    assert j.priority <= -10 and j.resource == "cpu"
    assert st.auto_queue(force=True) is None                                         # one is queued already
    Job.objects.all().delete()
    st.run(None, gpu=False, only=PC_KEYS)
    j = st.auto_queue(force=True)                                                    # the cheap ones were just made; only the tool check (never ran) is left
    assert j is not None and j.payload["only"] == ["remotion_toolchain"]
    Job.objects.all().delete()
    st.run(None, gpu=True)
    monkeypatch.setattr(st, "ready_keys", lambda: PC_KEYS + ["remotion_toolchain", "remotion_render"] + GPU_KEYS)
    j = st.auto_queue(force=True)                                                    # the GPU PC came on: the checks that were waiting for it run by themselves
    assert j is not None and j.resource == "gpu" and set(j.payload["only"]) >= {"gpu_card", "ollama_run", "comfyui"} and "database" not in j.payload["only"]


def test_it_can_be_switched_off(monkeypatch):
    from instai.core import settings_store

    monkeypatch.setattr(st, "ready_keys", lambda: PC_KEYS)
    monkeypatch.setenv("INSTAI_PC_SELFTEST_AUTO", "0")
    assert st.auto_queue(force=True) is None
    monkeypatch.delenv("INSTAI_PC_SELFTEST_AUTO")
    settings_store.set_setting("pc_selftest_auto", False)
    try:
        assert st.auto_queue(force=True) is None
    finally:
        settings_store.set_setting("pc_selftest_auto", True)
    assert st.auto_queue(force=True) is not None


def test_the_automation_tick_calls_it():
    import inspect

    from instai.production import automation

    assert "pcselftest.auto_queue()" in inspect.getsource(automation)               # wired into the tick (the tick itself needs a whole database of pages)


# ------------------------------------------------------------------------------------------------------------------------------ API and job

def test_the_api_shows_the_report_and_runs_the_checks_as_one_job(api, worker, monkeypatch):
    no_gpu(monkeypatch)
    monkeypatch.setattr(st, "_remote_version", lambda timeout=8.0: st.stamp())
    d = api.get("/api/system/selftest").json()
    assert d["report"] is None and d["running"] is False and d["state"] is None
    assert [c["key"] for c in d["checks"]] == [c["key"] for c in st.CHECKS] and {c["group"] for c in d["checks"]} == {"pc", "tools", "gpu"}
    r = api.post("/api/system/selftest", {}, format="json")
    assert r.status_code == 202
    again = api.post("/api/system/selftest", {}, format="json")
    assert again.json()["job"]["id"] == r.json()["job"]["id"]                         # pressed twice: the one that is there
    j = finish(api, worker, r)
    assert j["result"]["summary"]["pending"] >= 3 and j["result"]["ok"] is True
    d = api.get("/api/system/selftest").json()
    assert d["report"]["stamp"] == st.stamp() and d["running"] is False and d["stale"] is False and d["state"] in ("waiting", "attention", "problems")
    by = {c["key"]: c for c in d["report"]["checks"]}
    assert by["gpu_card"]["verdict"] == "pending" and by["database"]["verdict"] == "ok"
    only = api.post("/api/system/selftest", {"only": ["disk", "nope"]}, format="json")
    assert only.status_code == 202 and only.json()["job"]["payload"]["only"] == ["disk"] and only.json()["job"]["payload"]["gpu"] is False
    finish(api, worker, only)
    assert len(api.get("/api/system/selftest").json()["report"]["checks"]) == len(st.CHECKS)       # the other rows were kept


def test_the_job_kind_has_a_plain_name_and_the_handler_is_registered():
    from instai.jobs import describe, registry

    registry.load_handlers()
    assert registry.default_resource("system.selftest", {"gpu": True}) == "gpu" and registry.default_resource("system.selftest", {"gpu": False}) == "cpu"
    assert describe.KIND_TEXT["system.selftest"][0].startswith("آزمون خودکار")


def test_the_checks_that_load_a_model_wait_for_a_quiet_card(monkeypatch):
    from instai.core import hardware, runtime
    from instai.providers import ollama_fit
    from instai.providers.comfy import launcher

    monkeypatch.setattr(runtime, "ffmpeg_info", lambda: {"ffmpeg": "ffmpeg", "version": "7", "features": {}})
    monkeypatch.setattr(ollama_fit, "loaded", lambda url, t=1.5: [])
    monkeypatch.setattr(launcher, "_up", lambda url: True)
    monkeypatch.setattr(hardware, "gpu_status", lambda: {**GPU, "utilization": 93})
    busy = st.ready_keys()
    assert "gpu_card" in busy and not any(k in busy for k in ("nvenc", "ollama_run", "comfyui")), busy      # somebody works hard on the card: only the harmless look waits no longer
    monkeypatch.setattr(hardware, "gpu_status", lambda: {**GPU, "utilization": 4})
    quiet = st.ready_keys()
    assert all(k in quiet for k in GPU_KEYS), quiet
    monkeypatch.setattr(hardware, "gpu_status", lambda: None)
    assert not any(k in st.ready_keys() for k in GPU_KEYS)
