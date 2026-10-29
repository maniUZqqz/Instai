"""Model discovery against a fake copy of the owner's GPU PC: ComfyUI portable on the Desktop (with a sub-folder and an
extra_model_paths.yaml), NMarketing's processing server (MOSS-TTS, Piper) and its moved data folder (ACE-Step), Ollama's model store.
Nothing on the real disk is read (INSTAI_SCAN_DEFAULTS=0 in conftest.py; every folder below lives in tmp_path)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from tests import fakes

pytestmark = pytest.mark.django_db(transaction=True)
ROOT = Path(__file__).resolve().parents[1]
WAN_HI = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
WAN_LO = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
UMT5 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "wan_2.1_vae.safetensors"
LORA = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
FLUX = "FLUX.1 [dev] FP8.safetensors"
ANISORA_HI = "Index-Anisora-V3.2-High-Q4_0.gguf"


def touch(p: Path, data: bytes = b"x" * 16, mtime: float | None = None) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    if mtime:
        os.utime(p, (mtime, mtime))
    return p


def venv(base: Path, name: str, home: Path, marker: bool = True) -> Path:
    py = base / name / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python")
    touch(py)
    (base / name / "pyvenv.cfg").write_text(f"home = {home}\ninclude-system-site-packages = false\n", encoding="utf-8")
    if marker:
        touch(base / name / f".nm-pip-venv-{name}.json", b"{}")
    return py


@pytest.fixture
def owner_pc(tmp_path):
    """The owner's layout (user QQz): Desktop\\N\\ComfyUI_windows_portable and Desktop\\N\\Main V4\\processing-server, plus
    %USERPROFILE%\\NMarketing-data where NMarketing is moving its heavy data."""
    user = tmp_path / "Users" / "QQz"
    desk = user / "Desktop"
    portable = desk / "N" / "ComfyUI_windows_portable"
    comfy = portable / "ComfyUI"
    (portable / "run_nvidia_gpu.bat").parent.mkdir(parents=True, exist_ok=True)
    (portable / "run_nvidia_gpu.bat").write_text(".\\python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build\r\npause\r\n", encoding="utf-8")
    touch(portable / "python_embeded" / "python.exe")
    (portable / "python_embeded" / "Lib" / "site-packages").mkdir(parents=True)
    touch(comfy / "main.py", b"# ComfyUI")
    touch(comfy / "comfy" / "__init__.py", b"")
    touch(comfy / "custom_nodes" / "ComfyUI-Manager" / "__init__.py", b"")
    m = comfy / "models"
    touch(m / "diffusion_models" / WAN_HI)
    touch(m / "diffusion_models" / "wan" / WAN_LO)                 # a sub-folder: ComfyUI lists it as wan\<name>
    touch(m / "text_encoders" / UMT5)
    touch(m / "vae" / VAE)
    touch(m / "loras" / LORA)
    touch(m / "checkpoints" / FLUX)
    touch(m / "clip_vision" / "clip_vision_h.safetensors")
    shared = tmp_path / "Shared" / "AI"
    touch(shared / "models" / "unet" / ANISORA_HI)
    touch(shared / "more_loras" / "style_a.safetensors")
    (comfy / "extra_model_paths.yaml").write_text(
        "# shared models\n"
        "other_ui:\n"
        f"    base_path: {shared.as_posix()}\n"
        "    unet: models/unet\n"
        "    loras: |\n"
        "        models/loras\n"
        "        more_loras\n", encoding="utf-8")
    touch(desk / "old" / "ComfyUI" / "models" / "checkpoints" / "decoy.safetensors")   # not a ComfyUI (no main.py)
    # NMarketing processing server (code + voice models), older
    ps = desk / "N" / "Main V4" / "processing-server"
    old = time.time() - 30 * 86400
    touch(ps / "python312" / "python.exe")
    venv(ps / "venvs", "moss-tts", ps / "python312")
    touch(ps / "vendor" / "MOSS-TTS" / "moss_tts_realtime" / "inferencer.py", b"#")
    touch(ps / "vendor" / "MOSS-TTS" / "moss_soundeffect_v2" / "pipeline_moss_soundeffect.py", b"#")
    for f in ("MOSS-TTS-Realtime/model.safetensors", "MOSS-Audio-Tokenizer/model-00001-of-00002.safetensors",
              "MOSS-Audio-Tokenizer/model-00002-of-00002.safetensors", "persian-lora/adapter_model.safetensors", "persian-lora/fa_normalize.py",
              "persian-lora/ref.wav"):
        touch(ps / "models" / "moss-tts" / f, mtime=old if f.startswith("MOSS-TTS-Realtime") else None)
    piper = ps / "tools" / "PersianAiKit" / "Voice" / "models" / "piper"
    touch(piper / "piper" / "piper.exe")
    touch(piper / "voices" / "fa_IR-gyro-medium.onnx")
    touch(piper / "voices" / "fa_IR-gyro-medium.onnx.json", b"{}")
    # the moved data folder: ACE-Step complete and newer; a half-copied MOSS-TTS that must NOT win over the complete one
    nd = user / "NMarketing-data"
    for f in ("acestep-v15-turbo/model.safetensors", "vae/diffusion_pytorch_model.safetensors", "Qwen3-Embedding-0.6B/model.safetensors"):
        touch(nd / "models" / "acestep" / "checkpoints" / f)
    touch(nd / "vendor" / "ACE-Step-1.5" / "acestep" / "api_server.py", b"#")
    venv(nd / "venvs", "acestep", ps / "python312")
    touch(nd / "models" / "moss-tts" / "MOSS-TTS-Realtime" / "model.safetensors")
    # Ollama's model store (OLLAMA_MODELS)
    om = tmp_path / "ollama-models"
    touch(om / "manifests" / "registry.ollama.ai" / "library" / "qwq" / "32b", b"{}")
    touch(om / "manifests" / "registry.ollama.ai" / "library" / "qwen3-vl" / "30b", b"{}")
    return {"user": user, "desk": desk, "portable": portable, "comfy": comfy, "shared": shared, "ps": ps, "nd": nd, "ollama": om, "piper": piper}


def scan_owner(owner_pc, monkeypatch, **kw):
    from instai.core import discovery

    monkeypatch.setenv("INSTAI_SCAN_ROOTS", os.pathsep.join([str(owner_pc["desk"]), str(owner_pc["user"] / "NMarketing-data")]))
    monkeypatch.setenv("OLLAMA_MODELS", str(owner_pc["ollama"]))
    discovery.forget()
    return discovery.scan(**kw)


def test_scan_finds_everything_on_the_owners_layout(owner_pc, monkeypatch):
    from instai.core import discovery

    d = scan_owner(owner_pc, monkeypatch, wanted=[WAN_HI.lower()])
    installs = d["comfyui"]["installs"]
    assert [Path(c["root"]) for c in installs] == [owner_pc["comfy"]], "one ComfyUI; the decoy folder without main.py is ignored"
    c = installs[0]
    assert Path(c["launcher"]) == owner_pc["portable"] / "run_nvidia_gpu.bat" and Path(c["python"]) == owner_pc["portable"] / "python_embeded" / "python.exe"
    assert c["port"] == 8188 and "--windows-standalone-build" in c["launch_args"] and c["custom_nodes"] == ["ComfyUI-Manager"]
    assert d["comfyui"]["selected"] == c["root"]
    files = discovery.comfy_visible_files(d)
    for name in (WAN_HI, WAN_LO, UMT5, VAE, LORA, FLUX, ANISORA_HI, "style_a.safetensors"):
        assert name.lower() in files, name
    assert files[WAN_LO.lower()]["listed"] == os.path.join("wan", WAN_LO) and files[WAN_LO.lower()]["kind"] == "diffusion_models"
    assert files[ANISORA_HI.lower()]["kind"] == "unet", "found through extra_model_paths.yaml"
    assert "decoy.safetensors" not in files
    # voice: MOSS-TTS from the processing server (complete), ACE-Step from the moved data folder, SFX missing
    v = d["voice"]
    assert Path(v["moss"]["models_dir"]) == owner_pc["ps"] / "models" and v["moss"]["complete"], v["moss"]["missing"]
    assert Path(v["moss"]["vendor_dir"]) == owner_pc["ps"] / "vendor" and Path(v["moss"]["python"]).parts[-3] == "moss-tts"
    assert Path(v["music"]["models_dir"]) == owner_pc["nd"] / "models" and v["music"]["complete"], v["music"]["missing"]
    assert not v["sfx"]["complete"] and any("vae_128d_48k.pth" in m for m in v["sfx"]["missing"])
    assert Path(d["piper"]["exe"]) == owner_pc["piper"] / "piper" / "piper.exe" and [x["id"] for x in d["piper"]["voices"]] == ["fa_IR-gyro-medium"]
    assert sorted(d["ollama"]["on_disk"]) == ["qwen3-vl:30b", "qwq:32b"] and d["ollama"]["running"] is False
    assert Path(json.loads(open(Path(discovery.data_dir()) / "discovery.json", encoding="utf-8").read())["comfyui"]["selected"]) == owner_pc["comfy"]


def test_newest_complete_copy_wins_and_broken_venv_is_reported(owner_pc, monkeypatch):
    # a second, newer and complete MOSS-TTS in the data folder wins over the processing server's
    nd = owner_pc["nd"] / "models" / "moss-tts"
    for f in ("MOSS-Audio-Tokenizer/model-00001-of-00002.safetensors", "MOSS-Audio-Tokenizer/model-00002-of-00002.safetensors",
              "persian-lora/adapter_model.safetensors", "persian-lora/fa_normalize.py", "persian-lora/ref.wav"):
        touch(nd / f)
    os.utime(nd / "MOSS-TTS-Realtime" / "model.safetensors", (time.time() + 60, time.time() + 60))
    import shutil

    shutil.rmtree(owner_pc["ps"] / "python312")                    # the venvs' base Python moved away: venvs are not relocatable
    d = scan_owner(owner_pc, monkeypatch)
    assert Path(d["voice"]["moss"]["models_dir"]) == owner_pc["nd"] / "models"
    assert any("base Python missing" in m for m in d["voice"]["moss"]["missing"])


def test_registry_matching_features_and_wiring(owner_pc, monkeypatch, api):
    from instai.core import discovery, model_status, runtime, settings_store
    from instai.providers.audio import services
    from instai.providers.tts import PiperTTS

    settings_store.set_setting("model_paths", [str(owner_pc["desk"]), str(owner_pc["user"] / "NMarketing-data")])
    monkeypatch.setenv("OLLAMA_MODELS", str(owner_pc["ollama"]))
    d = model_status.current(force=True)
    rows = {r["file"]: r for r in model_status.comfy_rows(d)}
    assert all(rows[f]["found"] for f in (WAN_HI, WAN_LO, UMT5, VAE, LORA, FLUX, ANISORA_HI))
    assert not rows["Index-Anisora-V3.2-Low-Q4_0.gguf"]["found"] and rows["Index-Anisora-V3.2-Low-Q4_0.gguf"]["package"] == "anisora"
    wf = {w["id"]: w for w in model_status.workflow_status(d)}
    assert wf["wan22_i2v_a14b_fp8"]["ready"] and wf["wan22_flf_a14b_fp8"]["ready"] and wf["flux_dev_fp8_t2i"]["ready"]
    a = wf["anisora_v32_i2v_gguf"]
    assert not a["ready"] and a["missing_models"] == ["Index-Anisora-V3.2-Low-Q4_0.gguf"] and a["missing_nodes"] == ["UnetLoaderGGUF"]
    assert a["node_packages"] == ["comfy-gguf"] and not wf["sdxl_anime_t2i"]["ready"]
    # providers use what was found
    assert Path(runtime.comfyui_dir()) == owner_pc["comfy"]
    p = services.paths("moss")
    assert Path(p["models_dir"]) == owner_pc["ps"] / "models" and services.missing("moss") == [] and services.installed("moss")
    cmd = services.MANAGER.command("moss")
    assert cmd[0] == p["python"] and cmd[cmd.index("--models-dir") + 1] == p["models_dir"] and cmd[cmd.index("--vendor-dir") + 1] == p["vendor_dir"]
    assert Path(runtime.find_tool("piper")) == owner_pc["piper"] / "piper" / "piper.exe"
    assert PiperTTS().available()[0] and Path(PiperTTS()._model("fa_IR-gyro-medium")).parent == owner_pc["piper"] / "voices"
    from instai.providers.tts import MossTTS

    assert Path(MossTTS().default_reference()) == owner_pc["ps"] / "models" / "moss-tts" / "persian-lora" / "ref.wav"
    # ComfyUI is not running, but it can be started: routing counts the workflows its files allow
    from instai.gpu import capabilities

    caps = capabilities.local_capabilities()
    assert "comfy:wan22_i2v_a14b_fp8" in caps["caps"] and "comfy:anisora_v32_i2v_gguf" not in caps["caps"] and caps["models"]["comfyui_startable"]
    assert "voice:moss" in caps["caps"] and "voice:music" in caps["caps"] and "voice:sfx" not in caps["caps"]
    # the Models screen
    r = api.get("/api/models/found").json()
    assert r["comfyui"]["startable"] and not r["comfyui"]["running"] and r["comfyui"]["installs"][0]["selected"]
    items = {i["id"]: i for i in r["items"]}
    assert items["comfy:" + WAN_LO]["found"] and items["voice:moss"]["found"] and not items["voice:sfx"]["found"] and items["piper"]["found"]
    assert set(items["ollama"]["models"]) == {"qwq:32b", "qwen3-vl:30b"} and not items["ollama"]["running"]
    feats = {f["id"]: f for f in r["features"]}
    assert feats["wan22_i2v_a14b_fp8"]["ready"] and not feats["anisora_v32_i2v_gguf"]["ready"] and "comfy-gguf" in feats["anisora_v32_i2v_gguf"]["packages"]
    offers = {o["id"]: o for o in r["offers"]}
    assert {"anisora", "animegen", "animagine"} <= set(offers)
    assert offers["anisora"]["why"]["fa"] and offers["anisora"]["why"]["en"] and offers["anisora"]["licence"]
    assert offers["anisora"]["missing_size"] >= 9032587904 and "comfy-gguf" in [n["id"] for n in offers["anisora"]["needs"]]
    assert offers["animagine"]["size"] == 6938350040 and offers["animagine"]["commercial"] == "yes"
    assert discovery.selected_comfy(d)["root"] == r["comfyui"]["selected"]


def test_workflow_names_follow_what_comfyui_lists(owner_pc):
    """Sub-folders, letter case and aliases: availability and the queued graph both use ComfyUI's own names."""
    from instai.providers.comfy.workflows import adapt_graph, get_workflow, match_model, workflow_availability

    lo = "wan\\" + WAN_LO
    info = {"UNETLoader": {"input": {"required": {"unet_name": [[WAN_HI.upper(), lo]]}}},
            "CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["flux1-dev-fp8.safetensors"]]}}},
            "CLIPLoader": {"input": {"required": {"clip_name": [[UMT5]]}}}, "VAELoader": {"input": {"required": {"vae_name": ["COMBO", {"options": [VAE]}]}}},
            "LoraLoaderModelOnly": {"input": {"required": {"lora_name": [["loras_sub/" + LORA]]}}}}
    for n in ("ModelSamplingSD3", "WanImageToVideo", "KSamplerAdvanced", "VAEDecode", "CreateVideo", "SaveVideo", "LoadImage", "KSampler", "CLIPTextEncode",
              "EmptyLatentImage", "SaveImage", "FluxGuidance"):
        info.setdefault(n, {"input": {"required": {}}})
    assert match_model(WAN_LO, [lo]) == lo and match_model(FLUX, ["flux1-dev-fp8.safetensors"]) == "flux1-dev-fp8.safetensors"
    assert match_model("nothing.safetensors", [lo]) is None
    av = {w["id"]: w for w in workflow_availability(info)}
    assert av["wan22_i2v_a14b_fp8"]["available"] and av["wan22_i2v_a14b_fp8"]["resolved"][WAN_LO] == lo
    assert av["flux_dev_fp8_t2i"]["available"]
    g = adapt_graph(get_workflow("wan22_i2v_a14b_fp8").build({"prompt": "p", "image": "a.png"}), info)
    names = {n["inputs"].get("unet_name") for n in g.values() if n["class_type"] == "UNETLoader"}
    assert names == {WAN_HI.upper(), lo}
    assert any(n["inputs"].get("lora_name") == "loras_sub/" + LORA for n in g.values())
    f = adapt_graph(get_workflow("flux_dev_fp8_t2i").build({"prompt": "p"}), info)
    assert f["1"]["inputs"]["ckpt_name"] == "flux1-dev-fp8.safetensors"


def test_sdxl_anime_workflow_keeps_its_negative_and_quality_tags():
    from instai.providers.comfy.workflows import get_workflow

    g = get_workflow("sdxl_anime_t2i").build({"prompt": "a girl in a rainy street", "negative_prompt": "text", "seed": 3})
    assert g["4"]["inputs"]["text"].startswith("a girl in a rainy street, masterpiece") and g["3"]["inputs"]["text"].startswith("text, lowres")
    assert g["1"]["inputs"]["ckpt_name"] == "animagine-xl-4.0-opt.safetensors" and (g["5"]["inputs"]["width"], g["5"]["inputs"]["height"]) == (768, 1344)
    assert get_workflow("sdxl_anime_t2i").build({"prompt": "x"})["3"]["inputs"]["text"].startswith("lowres")


def test_extra_model_paths_parser_handles_blocks_and_relative_base(tmp_path):
    from instai.core.discovery import parse_extra_model_paths

    y = tmp_path / "extra_model_paths.yaml"
    y.write_text("a111:\n    base_path: ../sd\n    checkpoints: models/Stable-diffusion  # comment\n    vae: models/VAE\n"
                 "    is_default: true\n"
                 "comfyui:\n    base_path: 'D:/AI/models'\n    diffusion_models: |\n      diffusion_models\n      unet\n    loras: loras\n", encoding="utf-8")
    got = [(k, Path(p)) for k, p in parse_extra_model_paths(str(y))]
    assert ("checkpoints", (tmp_path / ".." / "sd" / "models" / "Stable-diffusion").resolve()) in [(k, p.resolve()) for k, p in got]
    kinds = [k for k, _ in got]
    assert kinds == ["checkpoints", "vae", "diffusion_models", "diffusion_models", "loras"]
    assert Path(got[2][1]).as_posix().endswith("D:/AI/models/diffusion_models") and Path(got[3][1]).as_posix().endswith("D:/AI/models/unet")


def test_launcher_runs_the_bat_line_without_a_browser(owner_pc, monkeypatch):
    from instai.core import discovery
    from instai.providers.comfy import launcher

    d = scan_owner(owner_pc, monkeypatch)
    sel = discovery.selected_comfy(d)
    argv, cwd = launcher.command(sel)
    assert Path(argv[0]) == owner_pc["portable"] / "python_embeded" / "python.exe" and argv[1] == "-s"
    assert Path(argv[2]) == owner_pc["comfy"] / "main.py" and argv[3:] == ["--windows-standalone-build", "--disable-auto-launch"]
    assert Path(cwd) == owner_pc["portable"]
    assert launcher.command({"launcher": None}) is None


def test_launcher_starts_comfyui_when_a_task_needs_it(monkeypatch):
    """ensure_running: nothing answers -> start the found ComfyUI -> wait until it answers (a fake server stands in)."""
    from instai.core import settings_store
    from instai.providers.comfy import launcher

    with fakes.comfy_server() as c:
        settings_store.set_setting("comfyui_url", c.url)
        started = []
        state = {"up": False}
        monkeypatch.setattr(launcher, "_up", lambda url: state["up"])

        def fake_start(install=None):
            started.append(1)
            state["up"] = True
            return {"started": True, "already_running": False, "cmd": "x", "error": ""}

        monkeypatch.setattr(launcher, "start", fake_start)
        assert launcher.ensure_running(timeout=5) == c.url and started == [1]
        assert launcher.ensure_running(timeout=5) == c.url and started == [1], "already running: not started twice"
    monkeypatch.setattr(launcher, "_up", lambda url: False)
    monkeypatch.setattr(launcher, "start", lambda install=None: {"started": False, "already_running": False, "cmd": None,
                                                                   "error": "no ComfyUI was found on this PC"})
    from instai.providers.base import ProviderError

    with pytest.raises(ProviderError) as e:
        launcher.ensure_running(timeout=1)
    assert e.value.code == "not_ready" and "cannot start it" in str(e.value)
    settings_store.set_setting("comfyui_url", "")


def test_downloader_reuses_what_comfyui_and_nmarketing_already_have(owner_pc, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import download_models as dm

        d = scan_owner(owner_pc, monkeypatch)
        dm._FOUND["value"] = d
        size = (owner_pc["comfy"] / "models" / "loras" / LORA).stat().st_size
        assert dm.comfy_dir() == d["comfyui"]["selected"]
        item = {"id": "t:lora", "kind": "file", "dest": "{COMFYUI}\\models\\loras\\" + LORA, "size": size}
        assert Path(dm.reuse_path(item)) == owner_pc["comfy"] / "models" / "loras" / LORA
        sub = {"id": "t:lo", "kind": "file", "dest": "{COMFYUI}\\models\\diffusion_models\\" + WAN_LO.upper(), "size": size}
        assert Path(dm.reuse_path(sub)) == owner_pc["comfy"] / "models" / "diffusion_models" / "wan" / WAN_LO, "any sub-folder, any letter case"
        assert dm.reuse_path({**item, "size": size + 1}) is None, "a file of another size is not the same file"
        extra = {"id": "t:ani", "kind": "file", "dest": "{COMFYUI}\\models\\unet\\" + ANISORA_HI, "size": size}
        assert Path(dm.reuse_path(extra)) == owner_pc["shared"] / "models" / "unet" / ANISORA_HI, "extra_model_paths.yaml counts"
        alias = {"id": "t:flux", "kind": "file", "dest": "{COMFYUI}\\models\\checkpoints\\flux1-dev-fp8.safetensors", "size": 17246524772, "aliases": [FLUX]}
        assert Path(dm.reuse_path(alias)) == owner_pc["comfy"] / "models" / "checkpoints" / FLUX, "the owner's FLUX file under its other name"
        voice = {"id": "t:v", "kind": "file", "dest": "{MODELS}\\moss-tts\\persian-lora\\ref.wav", "size": 16}
        assert Path(dm.reuse_path(voice)) == owner_pc["ps"] / "models" / "moss-tts" / "persian-lora" / "ref.wav", "NMarketing's voice files count"
        piper_voice = {"id": "t:pv", "kind": "file", "dest": "{MODELS}\\piper\\fa_IR-gyro-medium.onnx", "size": 63122309}
        assert Path(dm.reuse_path(piper_voice)) == owner_pc["piper"] / "voices" / "fa_IR-gyro-medium.onnx", "the voice kit's Piper voice counts"
        engine = {"id": "t:pe", "kind": "zip", "dest": "{TOOLS}\\piper-not-here", "marker": "piper\\piper.exe", "reuse_found": "piper_exe"}
        assert dm.is_installed(engine)[0] is True
        d["comfyui"]["api"]["names"] = {"remote.safetensors": "sub/remote.safetensors"}
        assert dm.reuse_path({"id": "t:r", "kind": "file", "dest": "{COMFYUI}\\models\\loras\\remote.safetensors", "size": 5}).startswith("ComfyUI lists")
        # the GGUF node package: python package inside ComfyUI's own Python
        pip_item = {"id": "t:gguf", "kind": "comfy_pip", "module": "gguf", "dest": "{COMFYUI}"}
        assert dm.comfy_python() and dm.is_installed(pip_item)[0] is False
        touch(owner_pc["portable"] / "python_embeded" / "Lib" / "site-packages" / "gguf" / "__init__.py", b"")
        assert dm.is_installed(pip_item)[0] is True
    finally:
        sys.path.remove(str(ROOT / "scripts"))
        sys.modules.pop("download_models", None)


def test_zip_with_one_top_folder_is_unpacked_into_dest(tmp_path, monkeypatch):
    import hashlib
    import http.server
    import threading
    import zipfile
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ComfyUI-GGUF-abc/", "")
        z.writestr("ComfyUI-GGUF-abc/nodes.py", "# node")
        z.writestr("ComfyUI-GGUF-abc/tools/convert.py", "# tool")
    payload = buf.getvalue()

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import download_models as dm

        dest = tmp_path / "custom_nodes" / "ComfyUI-GGUF"
        monkeypatch.setattr(dm, "DATA", str(tmp_path / "data"))
        item = {"id": "t:zip", "kind": "zip", "strip": True, "marker": "nodes.py", "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "urls": [f"http://127.0.0.1:{srv.server_address[1]}/node.zip"], "dest": str(dest)}
        monkeypatch.setattr(dm, "dest_of", lambda it: it["dest"])
        assert dm.install(item, None) and (dest / "nodes.py").read_text() == "# node" and (dest / "tools" / "convert.py").exists()
    finally:
        srv.shutdown()
        sys.path.remove(str(ROOT / "scripts"))
        sys.modules.pop("download_models", None)


def test_models_api_paths_and_confirmed_downloads(owner_pc, api):
    r = api.put("/api/models/paths", {"paths": [str(owner_pc["desk"]), str(owner_pc["desk"] / "missing-folder")]}, format="json")
    assert r.status_code == 400 and r.json()["error"]["details"]["paths"]
    r = api.put("/api/models/paths", {"paths": [str(owner_pc["desk"])]}, format="json", HTTP_X_LANG="en")
    assert r.status_code == 200 and r.json()["manual"] == [str(owner_pc["desk"])]
    assert any(i["found"] for i in r.json()["items"] if i["id"] == "comfy:" + WAN_HI)
    assert api.post("/api/models/rescan", {}, format="json").json()["comfyui"]["selected"] == str(owner_pc["comfy"])
    # an optional model is never downloaded without the owner's confirmation
    r = api.post("/api/models/offers/anisora/download", {}, format="json", HTTP_X_LANG="en")
    assert r.status_code == 400 and "confirm" in r.json()["error"]["message"]
    assert api.post("/api/models/offers/nope/download", {"confirm": True}, format="json").status_code == 404
    r = api.post("/api/models/offers/anisora/download", {"confirm": True}, format="json")
    assert r.status_code == 202, r.content
    from instai.jobs.models import Job

    job = Job.objects.get(pk=r.json()["job"]["id"])
    assert job.kind == "downloads.run" and job.payload["packages"][-1] == "anisora" and "comfy-gguf" in job.payload["packages"]
    assert job.payload["offer"] == "anisora" and job.payload["confirmed_at"]


def test_hardware_and_checklist_report_found_but_stopped_comfyui(owner_pc, api):
    from instai.core import hardware, model_status, settings_store
    from instai.core.checklist import _line

    settings_store.set_setting("model_paths", [str(owner_pc["desk"])])
    model_status.current(force=True)
    hardware._CACHE.update(at=0.0, value=None)
    items = {i["id"]: i for i in api.get("/api/system/hardware?refresh=1").json()["items"]}
    assert items["comfyui"]["status"] == "warn" and Path(items["comfyui"]["data"]["dir"]) == owner_pc["comfy"]
    assert items["models_found"]["data"]["comfy_files_found"] >= 6 and items["models_found"]["data"]["voice"]["moss"] is True
    line = _line(items["comfyui"])
    assert "found at" in line and line.isascii()
    assert _line(items["models_found"]).startswith("  [") and _line(items["models_found"]).isascii()


def test_default_roots_never_include_network_drives(monkeypatch):
    from instai.core import discovery

    monkeypatch.setattr(discovery, "fixed_drives", lambda: ["C:\\", "D:\\"])
    groups = discovery.scan_roots(env={"INSTAI_SCAN_DEFAULTS": "1"})
    assert groups[-1] == [("C:\\", 3), ("D:\\", 3)] and len(groups) == 4
    assert discovery.scan_roots(env={"INSTAI_SCAN_DEFAULTS": "0"})[0][0][0] == discovery.ROOT and len(discovery.scan_roots(env={"INSTAI_SCAN_DEFAULTS": "0"})) == 1
    if sys.platform.startswith("win"):
        import ctypes

        monkeypatch.undo()
        for d in discovery.fixed_drives():
            assert ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(d)) == 3, d
