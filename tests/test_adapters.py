"""Real HTTP adapters (Ollama, OpenAI-compatible, ComfyUI, MOSS-TTS, Piper) tested against in-process fake servers."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from instai.agents import schemas
from instai.agents.jsonschema_lite import validate
from instai.agents.runner import call_json
from instai.providers.base import ProviderError
from instai.providers.comfy.client import ComfyCancelled, ComfyClient
from instai.providers.comfy.workflows import WORKFLOWS, get_workflow, workflow_availability
from instai.providers.ollama import OllamaProvider
from instai.providers.openai_compat import OpenAICompatProvider, normalize_base_url
from instai.providers.tts import FakeTTS, MossTTS, PiperTTS, estimate_seconds, get_tts, wav_duration
from tests import fakes

pytestmark = pytest.mark.django_db

MSG = [{"role": "user", "content": "hi"}]


# ------------------------------------------------------------------ Ollama

def test_ollama_structured_output_and_think_flag():
    with fakes.ollama_server() as srv:
        p = OllamaProvider(srv.url, "qwen3:8b")
        r = call_json("strategy", schemas.STRATEGY, system="s", user="u", provider=p)
        assert not validate(r.data, schemas.STRATEGY) and r.provider == "ollama" and r.model == "qwen3:8b"
        chat = [x for x in srv.requests if x["path"] == "/api/chat"][-1]["body"]
        assert chat["format"]["type"] == "object", "the JSON schema is passed natively in `format`"
        assert chat["think"] is False and chat["stream"] is False and chat["options"]["num_predict"] > 0
        assert p.generate(MSG).tokens_per_second == 50.0  # eval_count / eval_duration


def test_ollama_think_rejected_retries_without_it_and_strips_think_tags():
    with fakes.ollama_server(reject_think=True, thinking_prefix=True) as srv:
        p = OllamaProvider(srv.url, "qwen3:8b")
        res = p.generate(MSG, schema=schemas.CONTINUITY)
        assert res.text.startswith("{")
        chats = [x["body"] for x in srv.requests if x["path"] == "/api/chat"]
        assert "think" in chats[0] and "think" not in chats[1]


def test_ollama_health_picks_model_and_unloads():
    with fakes.ollama_server(models=("gemma3:12b", "qwen3.5:9b"), loaded=("gemma3:12b",)) as srv:
        p = OllamaProvider(srv.url)
        h = p.health()
        assert h["ok"] and h["models"] == ["gemma3:12b", "qwen3.5:9b"]
        assert p.generate(MSG).model == "qwen3.5:9b"  # preferred model of the installed ones
        p.unload()
        keep = [x["body"] for x in srv.requests if x["path"] == "/api/generate"]
        assert {"model": "gemma3:12b", "keep_alive": 0} in keep and not srv.loaded


def test_ollama_missing_model_is_not_retryable_and_down_is():
    with fakes.ollama_server() as srv:
        with pytest.raises(ProviderError) as e:
            OllamaProvider(srv.url, "nope:1b").generate(MSG)
        assert e.value.retryable is False
    with pytest.raises(ProviderError) as e:
        OllamaProvider("http://127.0.0.1:9", "x").generate(MSG, timeout=2)
    assert e.value.retryable is True
    assert OllamaProvider("http://127.0.0.1:9").health()["ok"] is False


# ------------------------------------------------------------------ OpenAI-compatible

def test_openai_compat_modes_key_and_url_normalisation(monkeypatch):
    with fakes.openai_server() as srv:
        base = srv.url + "/v1/chat/completions"
        assert normalize_base_url(base + "/") == srv.url + "/v1"
        p = OpenAICompatProvider(srv.url + "/v1", "gpt-test", json_mode="json_schema", api_key=srv.key)
        r = call_json("strategy", schemas.STRATEGY, system="s", user="u", provider=p)
        assert not validate(r.data, schemas.STRATEGY)
        req = [x for x in srv.requests if x["path"] == "/v1/chat/completions"][-1]
        assert req["headers"]["Authorization"] == f"Bearer {srv.key}"
        assert req["body"]["response_format"]["type"] == "json_schema"
        # json_object mode
        p2 = OpenAICompatProvider(srv.url + "/v1", "gpt-test", json_mode="json_object", api_key=srv.key)
        p2.generate(MSG, schema=schemas.SCRIPT)
        assert [x for x in srv.requests if x["path"] == "/v1/chat/completions"][-1]["body"]["response_format"] == {"type": "json_object"}
        assert p.health()["models"] == ["gpt-test", "other"]


def test_openai_compat_wrong_key_is_not_retryable_and_never_logged(caplog):
    with fakes.openai_server() as srv:
        p = OpenAICompatProvider(srv.url + "/v1", "gpt-test", api_key="wrong-key-should-not-leak-1234")
        with pytest.raises(ProviderError) as e:
            p.generate(MSG)
        assert e.value.retryable is False and "wrong-key" not in str(e.value)
        assert p.health() == {"ok": False, "detail": "key rejected", "models": []}
        with pytest.raises(ProviderError):
            OpenAICompatProvider(srv.url + "/v1", "", api_key="k").generate(MSG)
    from instai.core.logs import redact

    assert redact("Authorization: Bearer abcdefghijklmnop") == "Authorization: Bearer ***"
    assert "sk-abcdefghijklmnop1234" not in redact("key sk-abcdefghijklmnop1234 used")


def test_openai_compat_retries_overloaded_and_falls_back_from_json_schema(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    with fakes.openai_server(fail_times=2, reject_json_schema=True, reply='{"ok": true}') as srv:
        p = OpenAICompatProvider(srv.url + "/v1", "m", json_mode="json_schema", api_key=srv.key)
        res = p.generate(MSG, schema=schemas.SCRIPT)
        assert res.text == '{"ok": true}'
        bodies = [x["body"] for x in srv.requests if x["path"] == "/v1/chat/completions"]
        assert len(bodies) == 4 and "response_format" not in bodies[-1]  # 2x 503, 1x 400 (schema unsupported), then plain


def test_provider_key_comes_only_from_env_and_settings_api_masks_it(api, monkeypatch, tmp_path):
    from instai import envfile

    monkeypatch.setattr(envfile, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr("instai.core.api.write_env_value", lambda k, v, path=tmp_path / ".env": envfile.write_env_value(k, v, path))
    monkeypatch.delenv("INSTAI_OPENAI_API_KEY", raising=False)
    r = api.put("/api/settings", {"openai_api_key": "sk-owner-secret-0000abcd", "openai_base_url": "https://example.test/v1", "openai_model": "m1"}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["api_key"] == {"set": True, "hint": "…abcd"}
    assert "sk-owner-secret" not in r.content.decode()
    assert "INSTAI_OPENAI_API_KEY=sk-owner-secret-0000abcd" in (tmp_path / ".env").read_text()
    assert body["values"]["openai_base_url"] == "https://example.test/v1"
    monkeypatch.delenv("INSTAI_OPENAI_API_KEY", raising=False)


# ------------------------------------------------------------------ ComfyUI

def test_workflow_input_validation_and_bindings():
    w = get_workflow("flux_dev_fp8_t2i")
    g = w.build({"prompt": "hello", "seed": 7, "width": 640, "height": 1152})
    assert g["4"]["inputs"]["text"] == "hello" and g["2"]["inputs"]["seed"] == 7
    assert (g["5"]["inputs"]["width"], g["5"]["inputs"]["height"]) == (640, 1152)
    with pytest.raises(ProviderError):
        w.build({})  # prompt is required
    with pytest.raises(ProviderError):
        w.build({"prompt": "x", "steps": "many"})
    assert w.build({"prompt": "x", "width": 99999})["5"]["inputs"]["width"] == 2048  # out-of-range numbers are clamped
    v = get_workflow("wan22_i2v_a14b_fp8").build({"prompt": "move", "image": "a.png", "length": 81})
    assert v["1"]["inputs"]["image"] == "a.png" and v["12"]["inputs"]["length"] == 81 and v["16"]["inputs"]["fps"] == 16.0
    prov = w.provenance({"prompt": "p", "seed": 3})
    assert prov["workflow"] == "flux_dev_fp8_t2i" and prov["workflow_version"] == 1 and prov["seed"] == 3


def test_every_template_is_a_wellformed_graph():
    for w in WORKFLOWS.values():
        assert w.template_file.exists()
        graph = w.build({"prompt": "x", "image": "i.png"})
        assert {n["class_type"] for n in graph.values()} >= set(w.required_nodes) - {"LoadImage"} or "LoadImage" in w.required_nodes


def test_workflow_availability_checks_nodes_and_model_files():
    with fakes.comfy_server() as full, fakes.comfy_server(missing_models=("wan_2.1_vae.safetensors",)) as part:
        ok = {w["id"]: w for w in workflow_availability(full.object_info())}
        assert all(w["available"] for w in ok.values())
        bad = {w["id"]: w for w in workflow_availability(part.object_info())}
        assert bad["wan22_i2v_a14b_fp8"]["available"] is False and bad["wan22_i2v_a14b_fp8"]["missing_models"] == ["wan_2.1_vae.safetensors"]
        assert bad["flux_dev_fp8_t2i"]["available"] is True
    # newer ComfyUI nodes describe combo inputs as ["COMBO", {"options": [...]}]
    info = full_info = fakes.comfy_server().object_info()
    info["VAELoader"]["input"]["required"]["vae_name"] = ["COMBO", {"options": []}]
    assert {w["id"]: w for w in workflow_availability(info)}["wan22_i2v_a14b_fp8"]["missing_models"] == ["wan_2.1_vae.safetensors"]
    none = workflow_availability({})
    assert not any(w["available"] for w in none) and none[0]["missing_nodes"]


def test_comfy_client_runs_graph_downloads_and_frees(tmp_path):
    with fakes.comfy_server(polls=2) as srv:
        c = ComfyClient(srv.url)
        assert c.is_up() and "KSampler" in c.object_info()
        graph = get_workflow("flux_dev_fp8_t2i").build({"prompt": "a cat", "seed": 5, "width": 256, "height": 448})
        pid, files = c.run(graph, timeout=10)
        assert files and files[0].filename.endswith(".png")
        out = c.download(files[0], tmp_path / "x" / "o.png")
        from PIL import Image

        assert Image.open(out).size[0] > 0
        c.free()
        assert srv.freed == 1
        up = c.upload_image(out)
        assert up == "uploaded.png" and srv.uploads == 1


def test_comfy_errors_are_clear_and_cancel_interrupts(tmp_path):
    graph = get_workflow("flux_dev_fp8_t2i").build({"prompt": "x"})
    with fakes.comfy_server(reject=True) as srv:
        with pytest.raises(ProviderError) as e:
            ComfyClient(srv.url).run(graph, timeout=5)
        assert e.value.retryable is False and "validation" in str(e.value)
    with fakes.comfy_server(execution_error=True) as srv:
        with pytest.raises(ProviderError) as e:
            ComfyClient(srv.url).run(graph, timeout=5)
        assert "out of memory" in str(e.value) and e.value.retryable is False
    with fakes.comfy_server(polls=10_000) as srv:
        with pytest.raises(ComfyCancelled):
            ComfyClient(srv.url).run(graph, timeout=10, cancel=lambda: True)
        assert srv.interrupted == 1
    with pytest.raises(ProviderError):
        ComfyClient("http://127.0.0.1:9").object_info()


# ------------------------------------------------------------------ TTS

def test_fake_tts_duration_follows_reading_speed(tmp_path):
    text = "این یک جمله‌ی آزمایشی برای سنجش مدت گفتار است و کمی بلند است"
    r = FakeTTS().synthesize(text, tmp_path / "a.wav", language="fa")
    assert abs(r.seconds - estimate_seconds(text, "fa")) < 0.05 and abs(wav_duration(r.path) - r.seconds) < 0.05
    assert r.path.stat().st_size > 10_000


def test_moss_tts_adapter_and_engine_selection(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    FakeTTS().synthesize("نمونه", ref, language="fa")
    with fakes.moss_server() as srv:
        m = MossTTS(srv.url)
        assert m.available()[0] is True
        r = m.synthesize("یک متن کوتاه برای تست", tmp_path / "o.wav", reference=str(ref), seed=3)
        assert r.engine == "moss" and r.path.exists() and r.sample_rate == 24000
        run = [x for x in srv.requests if x["path"] == "/run"][-1]["body"]
        assert run["reference"] == str(ref) and run["seed"] == 3
        with pytest.raises(ProviderError):
            m.synthesize("x", tmp_path / "o2.wav")  # no reference voice -> clear, non-retryable
    with fakes.moss_server(status="loading") as srv:
        assert MossTTS(srv.url).available() == (False, "status=loading")
    assert MossTTS("").available()[0] is False


def test_piper_reports_missing_engine_and_auto_selection_fails_clearly(monkeypatch, tmp_path):
    from instai.core import settings_store

    settings_store.set_setting("tts_engine", "auto")
    ok, detail = PiperTTS().available()
    assert ok is False and "piper" in detail.lower()
    with pytest.raises(ProviderError) as e:
        get_tts()
    assert e.value.code == "not_ready"
    assert get_tts("fake").id == "fake"
    settings_store.set_setting("tts_engine", "fake")
