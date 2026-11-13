"""The curated, verified model library of the Downloads page (0.8.0): every package of the owner's list is there with exact repository /
commit / path, size, sha256, licence and ComfyUI folder; non-commercial or unclear licences are never default and need a confirmation;
files ComfyUI already has (same name, another name, another folder) are not downloaded again; a blocked host falls through to the mirror."""
from __future__ import annotations

import hashlib
import http.server
import json
import re
import sys
import threading
from pathlib import Path

import pytest

from tests.test_discovery import owner_pc, scan_owner, touch  # noqa: F401  (fixtures of the fake owner PC)

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.django_db(transaction=True)

# the owner's brief, one entry per thing he asked for (see docs/MODELS.md): package id -> what must be inside
BRIEF = {
    "flux": "FLUX.1 [dev] fp8 checkpoint",
    "flux-schnell": "FLUX.1 [schnell] fp8 checkpoint",
    "flux-parts": "t5xxl fp8 + clip_l + ae (the split FLUX loaders)",
    "sdxl-base": "SDXL base",
    "sdxl-realvis": "a permissive SDXL checkpoint",
    "ipadapter-sdxl": "IP-Adapter (consistent characters)",
    "pulid-flux": "PuLID (consistent characters)",
    "controlnet-union-sdxl": "ControlNet union",
    "upscale-ultrasharp": "4x-UltraSharp",
    "upscale-realesrgan": "RealESRGAN",
    "wan22-ti2v-5b": "Wan 2.2 TI2V-5B",
    "ltx-distilled": "LTX-Video distilled",
    "rife": "RIFE",
    "piper-fa-voices": "TTS (more Persian Piper voices)",
}
COMFY_FOLDERS = {"checkpoints", "text_encoders", "vae", "diffusion_models", "controlnet", "upscale_models", "clip_vision", "ipadapter", "pulid", "clip",
                 "frame_interpolation", "insightface", "custom_nodes", "loras", "unet"}


def load_all():
    packages, items = {}, []
    for f in sorted((ROOT / "manifests").glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        packages.update(m.get("packages", {}))
        items += m.get("items", [])
    return packages, items


def test_every_item_of_the_brief_is_in_the_library():
    packages, items = load_all()
    missing = [pid for pid in BRIEF if not (packages.get(pid) or {}).get("curated")]
    assert not missing, f"not in the curated library: {missing}"
    names = {i["dest"].replace("\\", "/").rsplit("/", 1)[-1].lower() for i in items}
    for need in ("t5xxl_fp8_e4m3fn.safetensors", "clip_l.safetensors", "ae.safetensors", "flux1-schnell-fp8.safetensors", "flux1-dev-fp8.safetensors",
                 "sd_xl_base_1.0.safetensors", "4x-ultrasharp.pth", "realesrgan_x4plus.safetensors", "wan2.2_ti2v_5b_fp16.safetensors", "rife_v4.25.safetensors"):
        assert need in names, need
    assert any("pulid" in n for n in names) and any("ip-adapter" in n for n in names) and any("controlnet" in n for n in names)
    assert any("ltxv" in n and "distilled" in n for n in names)


def test_each_file_is_pinned_sized_hashed_and_has_a_mirror():
    packages, items = load_all()
    for pid in BRIEF:
        its = [i for i in items if i.get("package") == pid]
        assert its, pid
        for it in its:
            assert it["size"] and it["size"] > 0, it["id"]
            if it["kind"] == "file":
                small_text = it["dest"].endswith(".json")
                assert re.fullmatch(r"[0-9a-f]{64}", it.get("sha256") or "") or small_text, f"{it['id']}: sha256 missing"
                if it.get("hf"):
                    assert re.fullmatch(r"[0-9a-f]{40}", it["hf"]["revision"]), it["id"]
                    assert it["hf"]["repo"] and it["hf"]["path"]
                    assert it["urls"][0].startswith("{HF}/" + it["hf"]["repo"] + "/resolve/" + it["hf"]["revision"] + "/"), "pinned to the commit, not to main"
            else:
                assert it["kind"] == "zip" and re.fullmatch(r"[0-9a-f]{64}", it["sha256"]) and "/zip/" in it["urls"][0], it["id"]
            if it["dest"].startswith("{COMFYUI}\\"):
                assert it["dest"].split("\\")[1] in ("models", "custom_nodes")
                if it["dest"].split("\\")[1] == "models":
                    assert it["dest"].split("\\")[2] in COMFY_FOLDERS, f"{it['id']} goes to an unknown ComfyUI folder {it['dest']}"


def test_licence_policy_nothing_non_commercial_is_default_or_unconfirmed():
    packages, _ = load_all()
    for pid in BRIEF:
        p = packages[pid]
        c = p["curated"]
        assert c["commercial"] in ("yes", "conditional", "unknown", "no"), pid
        assert p.get("default") is not True, f"{pid} must not be selected by default"
        assert p.get("licence") and p.get("licence_verified") is not None
    for pid in ("flux", "upscale-ultrasharp", "pulid-flux"):
        assert packages[pid]["curated"]["commercial"] == "no", pid
    assert packages["ltx-distilled"]["curated"]["commercial"] == "unknown"
    for pid in ("flux-schnell", "sdxl-base", "sdxl-realvis", "controlnet-union-sdxl", "wan22-ti2v-5b", "upscale-realesrgan", "rife"):
        assert packages[pid]["curated"]["commercial"] == "yes", pid


def test_catalog_lists_the_library_with_groups_licence_flags_and_mirrors(api):
    r = api.get("/api/downloads/catalog")
    assert r.status_code == 200
    cur = {c["id"]: c for c in r.json()["curated"]}
    assert set(BRIEF) <= set(cur), set(BRIEF) - set(cur)
    assert {c["group"] for c in cur.values()} == {"image", "control", "upscale", "video", "voice"}, "every category of the page has packages"
    assert [c["group"] for c in r.json()["curated"]][0] == "image"
    f = cur["flux-parts"]["files"]
    assert {x["name"] for x in f} == {"t5xxl_fp8_e4m3fn.safetensors", "clip_l.safetensors", "ae.safetensors"}
    assert all(x["mirror"].startswith("https://hf-mirror.com/") and x["url"].startswith("https://huggingface.co/") for x in f)
    assert all(x["folder"].startswith("ComfyUI\\models\\") for x in f) and all(len(x["sha256"]) == 64 for x in f)
    assert cur["upscale-ultrasharp"]["needs_confirm"] and cur["flux"]["needs_confirm"] and cur["pulid-flux"]["needs_confirm"] and cur["ltx-distilled"]["needs_confirm"]
    assert not cur["flux-schnell"]["needs_confirm"] and not cur["sdxl-base"]["needs_confirm"]
    assert all(c["default"] is False for c in cur.values())
    assert cur["piper-fa-voices"]["files"][0]["folder"].startswith("InstAI\\models\\piper"), "the voice folder is shown as InstAI\\models\\piper"
    # the add-a-package box of the old UI must not list curated packages twice
    assert all(p["curated"] for p in r.json()["packages"] if p["id"] in BRIEF)


def test_a_non_commercial_package_is_queued_only_after_the_licence_confirmation(api):
    r = api.post("/api/downloads", {"packages": ["upscale-ultrasharp"]}, format="json")
    assert r.status_code == 400 and r.json()["error"]["details"]["confirm_licence"] == ["upscale-ultrasharp"]
    r = api.post("/api/downloads", {"packages": ["upscale-ultrasharp"], "confirm_licence": True}, format="json")
    assert r.status_code == 202, r.content
    r = api.post("/api/downloads", {"packages": ["upscale-realesrgan"]}, format="json")
    assert r.status_code == 202, "a plainly commercial licence needs no confirmation"


def test_a_file_comfyui_already_has_is_reused_not_downloaded(owner_pc, monkeypatch, api):  # noqa: F811
    from instai.core import settings_store

    scan_owner(owner_pc, monkeypatch)
    # the owner has the T5 encoder in the bigger fp16 form (an alias) and the FLUX dev checkpoint under its own name
    touch(owner_pc["comfy"] / "models" / "text_encoders" / "t5xxl_fp16.safetensors", b"t5")
    settings_store.set_setting("comfyui_dir", str(owner_pc["comfy"]))
    cur = {c["id"]: c for c in api.get("/api/downloads/catalog").json()["curated"]}
    t5 = next(x for x in cur["flux-parts"]["files"] if x["name"].startswith("t5xxl"))
    assert t5["installed"] and t5["reused"], t5
    assert cur["flux-parts"]["reused"] >= 1 and not cur["flux-parts"]["complete"]
    flux = next(x for x in cur["flux"]["files"])
    assert flux["installed"] and flux["reused"], "the owner's 'FLUX.1 [dev] FP8.safetensors' is the same weights under another name"


@pytest.fixture
def dm(owner_pc, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("INSTAI_DL_FAST", "1")
    sys.path.insert(0, str(ROOT / "scripts"))
    import download_models

    d = scan_owner(owner_pc, monkeypatch)
    download_models._FOUND["value"] = d
    monkeypatch.setattr(download_models, "DATA", str(tmp_path / "dmdata"))
    monkeypatch.setattr(download_models, "ALIASES", str(tmp_path / "dmdata" / "downloads" / "aliases.json"))
    monkeypatch.setattr(download_models, "LOG_DIR", str(tmp_path / "dmdata" / "logs"))
    yield download_models
    sys.path.remove(str(ROOT / "scripts"))
    sys.modules.pop("download_models", None)


def test_same_weights_under_another_name_are_linked_by_content(dm, owner_pc, monkeypatch):  # noqa: F811
    data = b"weights" * 20000
    other = owner_pc["comfy"] / "models" / "unet" / "someone-elses-name.safetensors"
    touch(other, data)
    touch(owner_pc["comfy"] / "models" / "unet" / "same-size-other-content.safetensors", b"x" * len(data))
    item = {"id": "t:w", "kind": "file", "dest": "{COMFYUI}\\models\\checkpoints\\model-a.safetensors", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "urls": ["http://127.0.0.1:9/never"]}
    assert dm.find_same_weights(item, min_size=1) == str(other), "the file with the same content is found, the decoy of the same size is not"
    assert dm.find_same_weights({**item, "sha256": hashlib.sha256(b"nothing").hexdigest()}, min_size=1) is None
    assert dm.find_same_weights(item) is None, "files under 50 MB are never hashed (not worth it)"
    monkeypatch.setenv("INSTAI_DEDUP_MIN_BYTES", "1")   # the test files are tiny
    assert dm.install(item, None) is True, "nothing is downloaded: the unreachable link is never tried"
    dest = Path(dm.dest_of(item))
    assert dest.read_bytes() == data and dest.parent.name == "checkpoints"
    assert dm.is_installed(item) == (True, str(dest))


def test_a_blocked_first_host_falls_through_to_the_mirror_at_once(dm, tmp_path):
    body = b"mirror-file" * 5000
    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path.startswith("/blocked"):
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        dest = tmp_path / "out" / "m.bin"
        ok = dm.download_file([base + "/blocked/m.bin", base + "/mirror/m.bin"], str(dest), len(body), retries=3)
        assert ok and dest.read_bytes() == body
        assert hits.count("/blocked/m.bin") <= 2 and "/mirror/m.bin" in hits, hits
        gone = tmp_path / "out2" / "m.bin"
        assert dm.download_file([base + "/blocked/x", "http://127.0.0.1:9/dead"], str(gone), 5, retries=2) is False
    finally:
        srv.shutdown()


def test_status_detail_names_every_file_of_a_package(dm, owner_pc):  # noqa: F811
    packages, items = dm.load_manifests()
    st = dm.status_json(packages, items, detail=True)
    assert set(BRIEF) <= set(st)
    d = {x["id"]: x for x in st["flux-parts"]["details"]}
    assert set(d) == {"flux-parts:t5xxl-fp8", "flux-parts:clip-l", "flux-parts:ae"}
    assert not st["rife"]["complete"] and st["rife"]["missing_size"] > 0
