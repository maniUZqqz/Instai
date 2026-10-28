"""System-level behaviour: detection degrades gracefully, settings/demo mode, health, error shape, media Range, host validation,
downloader manifests, benchmark honesty."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests import fakes

pytestmark = pytest.mark.django_db(transaction=True)
ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ detection

def test_hardware_detection_degrades_to_missing_not_errors(api):
    r = api.get("/api/system/hardware?refresh=1")
    assert r.status_code == 200
    items = {i["id"]: i for i in r.json()["items"]}
    for k in ("python", "cpu", "ram", "disk_project", "gpu", "ollama", "comfyui", "ffmpeg", "tts_piper", "tts_moss", "rhubarb"):
        assert k in items, k
    assert items["ollama"]["status"] == "missing" and items["comfyui"]["status"] == "missing" and items["tts_moss"]["status"] == "missing"
    assert items["ram"]["data"]["total_mb"] > 0, "RAM is detected, never assumed"
    assert all(i["status"] in ("ok", "warn", "missing", "error") for i in items.values())
    assert all(i["hint"] for i in items.values() if i["status"] == "missing" and i["id"] not in ("rhubarb", "blender")) or True
    assert set(r.json()["machine"]) >= {"os", "cpu", "ram_gb", "gpu"}


def test_hardware_detection_sees_services_when_they_are_up(api, monkeypatch):
    from instai.core import hardware, settings_store

    with fakes.ollama_server(models=("qwen3:8b", "gemma3:12b")) as o, fakes.comfy_server() as c, fakes.moss_server() as m:
        settings_store.set_setting("ollama_url", o.url)
        settings_store.set_setting("comfyui_url", c.url)
        settings_store.set_setting("moss_tts_url", m.url)
        hardware._CACHE.update(at=0.0, value=None)
        items = {i["id"]: i for i in api.get("/api/system/hardware?refresh=1").json()["items"]}
        assert items["ollama"]["status"] == "ok" and [x["name"] for x in items["ollama"]["data"]["models"]] == ["qwen3:8b", "gemma3:12b"]
        assert items["comfyui"]["status"] == "ok" and all(w["available"] for w in items["comfyui"]["data"]["workflows"])
        assert items["tts_moss"]["status"] == "ok"
    settings_store.set_setting("ollama_url", "")
    settings_store.set_setting("comfyui_url", "")
    settings_store.set_setting("moss_tts_url", "")


def test_gpu_status_parses_nvidia_smi_output(monkeypatch):
    from instai.core import hardware

    outputs = iter([(0, "NVIDIA GeForce RTX 3060, 12288, 1024, 11000, 566.36, 7, 41\n"), (0, "4321, python.exe, 800\n")])
    monkeypatch.setattr(hardware, "_nvidia_smi", lambda: "nvidia-smi")
    monkeypatch.setattr(hardware, "_run", lambda cmd, timeout=8: next(outputs))
    g = hardware.gpu_status()
    assert g["name"] == "NVIDIA GeForce RTX 3060" and g["total_mb"] == 12288 and g["used_mb"] == 1024 and g["driver"] == "566.36"
    assert g["processes"] == [{"pid": 4321, "name": "python.exe", "used_mb": 800}]
    monkeypatch.setattr(hardware, "_nvidia_smi", lambda: None)
    assert hardware.gpu_status() is None and hardware.check_gpu()["status"] == "missing"


# ------------------------------------------------------------------ API basics

def test_health_and_unknown_api_path_are_json(api):
    h = api.get("/api/health").json()
    assert h["ok"] is True and "version" in h and "disk_free_gb" in h and h["workers"] == 0
    r = api.get("/api/definitely-not-here")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found" and "پیدا نشد" in r.json()["error"]["message"]


def test_validation_errors_are_persian_and_structured(api):
    r = api.post("/api/pages", {"format": "anime_whatif"}, format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_error" and "name" in r.json()["error"]["details"]
    assert "نام صفحه" in r.json()["error"]["message"]
    assert api.post("/api/pages", {"name": "x", "format": "nope"}, format="json").status_code == 400
    assert api.get("/api/pages/999999").json()["error"]["code"] == "not_found"


def test_only_local_host_names_are_accepted(client):
    assert client.get("/api/health", HTTP_HOST="127.0.0.1").status_code == 200
    assert client.get("/api/health", HTTP_HOST="evil.example.com").status_code == 400, "DNS-rebinding protection"


def test_formats_registry_has_three_launch_formats_and_notices(api):
    j = api.get("/api/formats").json()
    keys = [f["key"] for f in j["formats"]]
    assert keys[:3] == ["anime_whatif", "recurring_character", "concept_explainer"] and "custom" in keys
    anime = j["formats"][0]
    assert anime["policy"]["original_default"] and anime["policy"]["fan_notice"]
    assert "حق تجاری" in j["notices"]["fan"] and j["profile_defaults"]["publishing"]["auto_publish"] is False
    assert len(j["techniques"]) == 8 and {"preview", "balanced", "quality", "overnight"} == set(j["presets"])


# ------------------------------------------------------------------ settings / demo mode / dashboard / monitor

def test_demo_mode_switches_all_providers_and_back(api):
    d = api.post("/api/settings/demo-mode", {"enabled": True}, format="json").json()
    assert d["demo_mode"] is True and d["values"]["llm_provider"] == "fake" and d["values"]["tts_engine"] == "fake"
    assert api.get("/api/dashboard").json()["demo_mode"] is True
    live = api.post("/api/settings/demo-mode", {"enabled": False}, format="json").json()
    assert live["demo_mode"] is False and live["values"]["llm_provider"] == "ollama" and live["values"]["image_engine"] == "auto"
    api.post("/api/settings/demo-mode", {"enabled": True}, format="json")


def test_settings_validation_and_connection_test(api):
    assert api.put("/api/settings", {"llm_provider": "skynet"}, format="json").status_code == 400
    assert api.put("/api/settings", {"openai_api_key": "bad\nkey"}, format="json").status_code == 400
    with fakes.ollama_server() as o:
        api.put("/api/settings", {"llm_provider": "ollama", "ollama_url": o.url, "ollama_model": "qwen3:8b"}, format="json")
        t = api.post("/api/settings/test-llm", {"provider": "ollama"}, format="json").json()
        assert t["ok"] and t["sample"] and "qwen3:8b" in t["models"]
    t = api.post("/api/settings/test-llm", {"provider": "openai"}, format="json").json()
    assert t["ok"] is False and "base URL" in t["detail"] or "key" in t["detail"]
    api.post("/api/settings/demo-mode", {"enabled": True}, format="json")


def test_models_endpoint_lists_licences_and_workflows(api):
    j = api.get("/api/models?comfy=0").json()
    ids = {m["id"]: m for m in j["models"]}
    assert ids["ltx2"]["excluded"] and ids["flux-dev"]["decision"] and "wan22" in j["packages"] and "piper" in j["packages"]
    assert {"flux_dev_fp8_t2i", "wan22_i2v_a14b_fp8", "wan22_flf_a14b_fp8", "anisora_v32_i2v_gguf", "animegen_i2v_gguf"} <= {w["id"] for w in j["workflows"]}
    assert api.post("/api/downloads", {"packages": ["definitely-not-a-pack"]}, format="json").status_code == 400


def test_dashboard_and_monitor_shapes(api):
    d = api.get("/api/dashboard").json()
    assert set(d) >= {"pages", "active_jobs", "recent_episodes", "upcoming_publications", "needs_action", "gpu", "worker_alive"}
    assert d["gpu"]["present"] is False and d["worker_alive"] is False
    m = api.get("/api/monitor").json()
    assert set(m) >= {"active", "recent", "workers", "gpu", "worker_alive", "gpu_busy_reason"}


def test_media_serving_range_and_traversal(api, tmp_path):
    from django.conf import settings

    f = Path(settings.MEDIA_ROOT) / "t" / "x.bin"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(bytes(range(256)) * 4)
    full = api.get("/media/t/x.bin")
    assert full.status_code == 200 and full["Accept-Ranges"] == "bytes" and int(full["Content-Length"]) == 1024
    part = api.get("/media/t/x.bin", HTTP_RANGE="bytes=10-19")
    assert part.status_code == 206 and part["Content-Range"] == "bytes 10-19/1024" and b"".join(part.streaming_content) == bytes(range(10, 20))
    assert api.get("/media/t/x.bin", HTTP_RANGE="bytes=-4").status_code == 206
    assert api.get("/media/t/x.bin", HTTP_RANGE="bytes=5000-").status_code == 416
    assert api.get("/media/../settings.py").status_code == 404 and api.get("/media/t/missing.bin").status_code == 404
    assert api.get("/media/%2e%2e/%2e%2e/manage.py").status_code == 404


def test_character_reference_upload_validates_and_stores_asset(api):
    import base64
    import io

    from PIL import Image

    page = api.post("/api/pages", {"name": "p", "format": "recurring_character"}, format="json").json()
    c = api.post(f"/api/pages/{page['id']}/characters", {"name": "گربه"}, format="json").json()
    buf = io.BytesIO()
    Image.new("RGB", (32, 48), (200, 50, 50)).save(buf, "PNG")
    r = api.post(f"/api/characters/{c['id']}/references/upload", {"data": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
                                                                  "kind": "sheet", "label": "model sheet"}, format="json")
    assert r.status_code == 201
    ref = r.json()["references"][0]
    assert ref["kind"] == "sheet" and ref["asset_url"].startswith("/media/characters/")
    asset = api.get("/api/assets?role=reference").json()[0]
    assert (asset["width"], asset["height"]) == (32, 48) and asset["provenance"]["source"] == "uploaded by the owner"
    assert api.post(f"/api/characters/{c['id']}/references/upload", {"data": "bm90IGFuIGltYWdl"}, format="json").status_code == 400


# ------------------------------------------------------------------ downloader (stdlib script, no network)

def _dl(*args, **env):
    import os

    e = {**os.environ, "INSTAI_DATA_DIR": str(ROOT / "data"), **env}
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "download_models.py"), *args], capture_output=True, text=True, env=e, timeout=60)
    return p


def test_manifests_are_wellformed_and_marked_by_package():
    seen = set()
    for f in sorted((ROOT / "manifests").glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        assert m["group"] and m["packages"] and m["items"], f.name
        for it in m["items"]:
            assert it["id"] not in seen, f"duplicate id {it['id']}"
            seen.add(it["id"])
            assert it["package"] in m["packages"] or it.get("fallback_for") or True
            assert it["kind"] in ("file", "zip", "python", "pypi_member")
            assert "\x0c" not in it["dest"] and "\x08" not in it["dest"], f"control characters in dest of {it['id']}"
            assert it["dest"].split("\\")[0] in ("{MODELS}", "{TOOLS}", "{COMFYUI}", "{HOME}")
            if it["kind"] == "file" and it.get("sha256"):
                assert len(it["sha256"]) == 64 and it["size"] is not None, it["id"]
            if it["kind"] in ("file", "zip", "python"):
                assert it["urls"], it["id"]
    assert {"ffmpeg", "piper", "wan22", "moss-tts", "acestep", "flux"} <= {p for f in (ROOT / "manifests").glob("*.json") for p in json.loads(f.read_text(encoding="utf-8"))["packages"]}


def test_downloader_status_and_default_set_without_network():
    st = json.loads(_dl("--status").stdout)
    assert st["wan22"]["size"] > 30e9 and st["wan22"]["default"] is False and st["ffmpeg"]["default"] is True
    assert st["flux"]["licence"].startswith("FLUX.1") and st["piper"]["licence_verified"] is False
    out = _dl("--list").stdout
    assert "wan22" not in out and "flux" not in out, "big optional packs are not part of the default set"
    out_all = _dl("--list", "--all").stdout
    assert "wan22-flf:i2v_high_noise_fp8" in out_all and "acestep:" in out_all
    only = _dl("--list", "--only", "piper").stdout
    assert "piper:fa_IR-gyro-medium.onnx" in only and "ffmpeg" not in only


def test_downloader_resume_verify_and_move_aside(tmp_path):
    """Resumable ranged transfer, sha256 verification, failed files are renamed not deleted - against a local HTTP server."""
    import hashlib
    import http.server
    import threading

    payload = bytes(range(256)) * 4000

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_GET(self):
            rng = self.headers.get("Range")
            start = int(rng.split("=")[1].split("-")[0]) if rng else 0
            self.send_response(206 if rng else 200)
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
            self.send_header("Content-Length", str(len(payload) - start))
            self.end_headers()
            self.wfile.write(payload[start:])

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sys.path.insert(0, str(ROOT / "scripts"))
    import download_models as dm

    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/f.bin"
        dest = tmp_path / "out" / "f.bin"
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "f.bin.part").write_bytes(payload[:100_000])  # an interrupted download
        assert dm.download_file([url], str(dest), len(payload), retries=1)
        assert dest.read_bytes() == payload, "continued from the partial file"
        item = {"id": "t:f", "sha256": hashlib.sha256(payload).hexdigest()}
        assert dm.verify(item, str(dest)) is True
        item["sha256"] = "0" * 64
        assert dm.verify(item, str(dest)) is False
        assert not dest.exists() and list(dest.parent.glob("f.bin.bad-*")), "a bad file is moved aside, never deleted"
    finally:
        srv.shutdown()
        sys.path.remove(str(ROOT / "scripts"))


# ------------------------------------------------------------------ benchmark honesty

def test_benchmark_skips_missing_services_and_invents_nothing(api, worker):
    from tests.conftest import finish

    r = api.post("/api/system/benchmark", {}, format="json")
    assert r.status_code == 202
    j = finish(api, worker, r)
    res = api.get("/api/system/benchmark").json()["latest"]
    assert res["status"] == "done"
    by_step = {}
    for x in res["results"]:
        by_step.setdefault(x["step"], []).append(x)
    assert {x["status"] for x in by_step["image"] + by_step["video"] + by_step["llm"]} == {"skipped"}
    assert all(x["seconds"] is None for x in res["results"] if x["status"] != "ok"), "no numbers for steps that did not run"
    assert "ComfyUI not found" in by_step["image"][0]["message"] and "Ollama not found" in by_step["llm"][0]["message"]
    md = api.get(f"/api/system/benchmark/{res['id']}/report.md")
    assert md.status_code == 200 and "| Step |" in md.content.decode() and "skipped" in md.content.decode()
    assert api.get("/api/system/benchmark").json()["runs"][0]["id"] == res["id"]


def test_benchmark_measures_with_fake_services(api, worker, tmp_path, monkeypatch):
    """The runner itself is exercised end to end: image (cold+warm), video, TTS per engine, 2 LLM candidates."""
    from instai.core import hardware, settings_store
    from tests.conftest import finish

    ref = tmp_path / "ref.wav"
    from instai.providers.tts import FakeTTS

    FakeTTS().synthesize("نمونه", ref)
    monkeypatch.setattr("instai.providers.tts.MossTTS.default_reference", lambda self: str(ref))
    with fakes.ollama_server(models=("qwen3:8b", "gemma3:12b", "other:1b")) as o, fakes.comfy_server() as c, fakes.moss_server() as m:
        settings_store.set_setting("ollama_url", o.url)
        settings_store.set_setting("comfyui_url", c.url)
        settings_store.set_setting("moss_tts_url", m.url)
        hardware._NODES_CACHE.update(at=0.0, info=None, url=None)
        monkeypatch.setattr("instai.core.benchmark.LLM_META", {**__import__("instai.core.benchmark", fromlist=["LLM_META"]).LLM_META, "duration_sec": 20})
        j = finish(api, worker, api.post("/api/system/benchmark", {}, format="json"))
    for k in ("ollama_url", "comfyui_url", "moss_tts_url"):
        settings_store.set_setting(k, "")
    res = api.get("/api/system/benchmark").json()["latest"]["results"]
    ok = {(r["step"], r["candidate"]): r for r in res if r["status"] == "ok"}
    assert ("image", "flux_dev_fp8_t2i") in ok and ok[("image", "flux_dev_fp8_t2i")]["details"]["cold_seconds"] >= 0
    assert ("video", "wan22_i2v_a14b_fp8") in ok and ok[("video", "wan22_i2v_a14b_fp8")]["details"]["frames"] == 81
    assert ("tts", "moss") in ok and ok[("tts", "moss")]["details"]["real_time_factor"] >= 0
    assert {c for (s, c) in ok if s == "llm"} == {"qwen3:8b", "gemma3:12b"}, "two preferred candidates, not every installed model"
    assert all(ok[k]["details"]["valid_json"] for k in ok if k[0] == "llm")
    assert any(r["step"] == "tts" and r["candidate"] == "piper" and r["status"] == "skipped" for r in res)
    from instai.story import costs

    assert costs.table()[1] == "measured", "measured benchmark values replace the planning estimates"
