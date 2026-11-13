"""Code-to-video with Remotion (0.8.0): the style kits that come from the art-style library, the compositions' catalog, the page API, the render job
(waits for the toolchain, runs the renderer, registers the file), and the automatic toolchain setup (portable Node.js, npm packages, a browser).
The Node side is faked by small Python scripts (no Node.js, no browser here); a real end-to-end render runs only where the toolchain exists
(set INSTAI_REMOTION_REAL=1 on a PC that has run scripts/setup_remotion.py)."""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import re
import shutil
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from tests.conftest import finish

ROOT = Path(__file__).resolve().parents[1]
REMOTION = ROOT / "remotion"
sys.path.insert(0, str(ROOT / "scripts"))
import setup_remotion as sr  # noqa: E402

pytestmark = pytest.mark.django_db(transaction=True)


# ------------------------------------------------------------------ the project's own files

def catalog_ids() -> list[str]:
    return re.findall(r"^\s{4}id: '([A-Za-z]+)',", (REMOTION / "src" / "catalog.ts").read_text(encoding="utf-8"), re.M)


def test_the_catalog_the_api_and_the_files_agree():
    from instai.remotion import toolchain

    assert catalog_ids() == list(toolchain.COMPOSITIONS) == ["TitleCard", "KineticText", "Explainer", "LowerThird"]
    for cid in toolchain.COMPOSITIONS:
        assert (REMOTION / "src" / "compositions" / f"{cid}.tsx").is_file()
        src = (REMOTION / "src" / "compositions" / f"{cid}.tsx").read_text(encoding="utf-8")
        assert f"export const {cid}:" in src and "useVazirmatn" in src and "normalizeKit" in src, f"{cid} uses the shared kit"
    for rel in toolchain.SHARED_FILES:
        assert (REMOTION / rel).is_file(), rel
    sizes = re.findall(r"(landscape|vertical|square): \{ w: (\d+), h: (\d+)", (REMOTION / "src" / "catalog.ts").read_text(encoding="utf-8"))
    assert {k: (int(w), int(h)) for k, w, h in sizes} == toolchain.SIZES


def test_every_animation_style_of_the_library_has_its_own_motion():
    """The ten ways a style can move (instai/styles/schema.py ANIMATIONS) each have a motion personality in remotion/src/kit/motion.ts."""
    from instai.styles import schema

    motion = (REMOTION / "src" / "kit" / "motion.ts").read_text(encoding="utf-8")
    declared = set(re.findall(r"^  ([a-z_0-9]+): \{ ease:", motion, re.M))
    assert declared == set(schema.ANIMATIONS), (declared ^ set(schema.ANIMATIONS))


def test_every_family_of_the_library_has_a_stage_background():
    from instai.styles import schema

    stage = (REMOTION / "src" / "kit" / "Stage.tsx").read_text(encoding="utf-8")
    handled = set(re.findall(r"kit\.family === '([a-z_0-9]+)'", stage))
    assert handled | {"graphic"} == set(schema.FAMILIES), "graphic is the fallback of the stage"


def test_the_font_and_its_licence_are_in_the_project():
    fonts = REMOTION / "public" / "fonts"
    assert (fonts / "Vazirmatn-Regular.woff2").stat().st_size > 10000 and (fonts / "Vazirmatn-Bold.woff2").stat().st_size > 10000 and (fonts / "OFL.txt").is_file()


def test_the_package_pins_are_exact_and_agree():
    pkg = json.loads((REMOTION / "package.json").read_text(encoding="utf-8"))
    deps = pkg["dependencies"]
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in deps.values()), "exact versions only"
    assert len({deps["remotion"], deps["@remotion/bundler"], deps["@remotion/renderer"]}) == 1, "all Remotion packages share one version"
    front = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    assert front["remotion"] == front["@remotion/player"] == deps["remotion"], "the preview and the render run the same Remotion"


# ------------------------------------------------------------------ the style kit

def test_every_style_of_the_library_becomes_a_valid_kit():
    from instai.remotion import kit
    from instai.styles import library, schema

    kits = kit.all_kits()
    assert len(kits) == len(library.list_presets("style")) and len(kits) >= 20
    for k in kits:
        assert list(k["palette"]) == schema.PALETTE_ROLES and all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in k["palette"].values()), k["key"]
        assert k["animation"] in schema.ANIMATIONS and k["family"] in schema.FAMILIES and 4 <= k["fps_feel"] <= 60
        assert k["typography"]["title_animation"] in schema.TITLE_ANIMATIONS and k["typography"]["title_weight"] in schema.TITLE_WEIGHTS
        assert k["name_fa"] and k["animation_fa"] and k["animation_en"]
    assert {k["animation"] for k in kits} == set(schema.ANIMATIONS), "the library offers every way of moving"


def test_a_theme_gives_the_typography_and_an_unknown_style_falls_back():
    from instai.remotion import kit

    a = kit.style_kit("noir_bw")
    b = kit.style_kit("noir_bw", "warm_sunset")
    assert b["theme_key"] == "warm_sunset" and b["typography"]["title_animation"] == "pop" and a["theme_key"] == "mono_noir"
    assert kit.style_kit("does_not_exist")["key"] == kit.DEFAULT_KEY
    assert kit.style_kit(None)["key"] == kit.DEFAULT_KEY


# ------------------------------------------------------------------ the page API

def test_status_code_and_kits_endpoints(api):
    s = api.get("/api/remotion/status").json()
    assert set(s) >= {"ready", "node", "packages", "browser", "state", "project", "auto"} and s["project"] is True
    code = api.get("/api/remotion/code").json()
    assert [c["id"] for c in code["compositions"]] == ["TitleCard", "KineticText", "Explainer", "LowerThird"]
    assert all(len(c["code"]) > 800 and "useCurrentFrame" in c["code"] for c in code["compositions"])
    assert {x["name"] for x in code["shared"]} == {"theme.ts", "motion.ts", "Stage.tsx", "catalog.ts", "render.mjs"}
    kits = api.get("/api/remotion/kits").json()
    assert len(kits["kits"]) >= 20 and kits["default"] == "cinematic_realistic"
    one = api.get("/api/remotion/kit", {"style": kits["kits"][3]["key"]}).json()
    assert one["key"] == kits["kits"][3]["key"]
    assert api.get("/api/remotion/kit", {"style": "../../etc"}).status_code == 400


def test_the_code_view_cannot_read_other_files():
    from instai.remotion import toolchain

    for bad in ("../frontend/package.json", "node_modules/remotion/package.json", "src/../../.env", "/etc/passwd"):
        with pytest.raises(FileNotFoundError):
            toolchain.read_file(bad)
    assert "registerRoot" in toolchain.read_file("src/index.ts")


def post_render(api, **kw):
    body = {"composition": "TitleCard", "props": {"title": "عنوان"}, "style": "cinematic_realistic", "size": "square", **kw}
    return api.post("/api/remotion/render", body, format="json")


def test_render_requests_are_validated_and_cleaned(api):
    from instai.jobs.models import Job

    assert post_render(api, composition="Nope").status_code == 404
    assert post_render(api, size="huge").status_code == 400
    assert post_render(api, style="a b").status_code == 400
    assert post_render(api, still=-1).status_code == 400
    assert post_render(api, props={"title": ""}).status_code == 400
    assert post_render(api, props={"title": "x" * 401}).status_code == 400
    assert post_render(api, composition="KineticText", props={"lines": []}).status_code == 400
    assert post_render(api, composition="KineticText", props={"lines": ["a"] * 41}).status_code == 400
    assert post_render(api, composition="Explainer", props={"title": "t", "steps": [{"title": "s"}] * 13}).status_code == 400
    assert post_render(api, composition="Explainer", props={"title": "t", "steps": []}).status_code == 400
    r = post_render(api, composition="Explainer", props={"title": "چطور؟", "steps": [{"title": "یک", "body": "دو"}, {"title": "سه"}], "outro": "تمام", "evil": "<script>", "kit": {"x": 1}})
    assert r.status_code == 202, r.content
    j = Job.objects.get(pk=r.json()["job"]["id"])
    assert j.kind == "remotion.render" and j.resource == "cpu"
    assert j.payload["props"] == {"title": "چطور؟", "steps": [{"title": "یک", "body": "دو"}, {"title": "سه", "body": ""}], "outro": "تمام"}, "unknown fields are dropped"
    s = post_render(api, still=42)
    assert s.status_code == 202 and Job.objects.get(pk=s.json()["job"]["id"]).payload["still"] == 42


# ------------------------------------------------------------------ the render job (the Node side is a Python stand-in)

FAKE_RENDER = r'''
import json, os, sys
job = json.load(open(sys.argv[1], encoding="utf-8"))
def ev(**k): print("INSTAI_REMOTION " + json.dumps(k), flush=True)
if os.environ.get("FAKE_FAIL"):
    ev(event="error", message=os.environ["FAKE_FAIL"]); sys.exit(1)
ev(event="phase", phase="bundling"); ev(event="bundle", progress=100)
ev(event="composition", id=job["composition"], width=1080, height=1080, fps=30, frames=150)
for i in (50, 100, 150):
    ev(event="progress", rendered=i, encoded=i, frames=150, progress=i / 150)
os.makedirs(os.path.dirname(job["out"]), exist_ok=True)
open(job["out"], "wb").write(b"\x00" * 2048 if job["out"].endswith("mp4") else b"\x89PNG\r\n")
open(os.path.join(os.path.dirname(job["out"]), "seen.json"), "w").write(json.dumps({"props": job["props"], "browser": job.get("browser"), "mode": job.get("chrome_mode")}))
ev(event="done", out=job["out"], width=1080, height=1080, fps=30, frames=150, seconds=1.2)
'''


@pytest.fixture
def fake_toolchain(tmp_path, monkeypatch):
    from instai.remotion import toolchain
    from instai.jobs.handlers import remotion as h

    proj = tmp_path / "remotion"
    proj.mkdir()
    (proj / "render.mjs").write_text(FAKE_RENDER, encoding="utf-8")
    ready = {"v": True}
    monkeypatch.setattr(toolchain, "PROJECT", proj)
    monkeypatch.setattr(toolchain, "status", lambda: {"ready": ready["v"], "node": {"path": sys.executable, "version": "v24.0.0", "source": "portable"},
                                                      "browser": {"path": "C:\\Edge\\msedge.exe", "source": "system", "mode": "chrome-for-testing"},
                                                      "packages": True, "state": "ready" if ready["v"] else "running", "message_fa": "در حال نصب ...", "message_en": "installing ..."})
    kicks = []
    monkeypatch.setattr(h, "kick_setup", lambda: kicks.append(1))
    monkeypatch.delenv("FAKE_FAIL", raising=False)
    return {"ready": ready, "kicks": kicks, "proj": proj}


def test_a_render_waits_for_the_setup_and_then_runs_by_itself(api, worker, fake_toolchain):
    from instai.jobs.models import Job

    fake_toolchain["ready"]["v"] = False
    r = post_render(api)
    jid = r.json()["job"]["id"]
    worker.drain(5)
    j = Job.objects.get(pk=jid)
    assert j.status == Job.QUEUED and j.wait_code == "remotion_setup" and j.attempts == 0, "waiting is not failing"
    assert "Remotion" in j.waiting_reason and fake_toolchain["kicks"], "the setup is started in the background"
    fake_toolchain["ready"]["v"] = True
    Job.objects.filter(pk=jid).update(run_after=Job.objects.get(pk=jid).created_at)
    worker.drain(5)
    j = Job.objects.get(pk=jid)
    assert j.status == Job.SUCCEEDED, (j.status, j.error)


def test_a_render_runs_the_renderer_and_registers_the_video(api, worker, fake_toolchain):
    from instai.assets.models import Asset

    r = post_render(api, composition="LowerThird", props={"name": "نام", "role": "سمت"}, style="cinematic_realistic", size="vertical")
    j = finish(api, worker, r)
    res = j["result"]
    assert res["kind"] == "mp4" and res["url"].startswith("/media/remotion/") and res["url"].endswith("LowerThird.mp4") and res["width"] == 1080 and res["frames"] == 150
    a = Asset.objects.get(pk=res["asset_id"])
    assert a.kind == "video" and a.role == "export" and a.provenance["engine"] == "remotion" and a.provenance["composition"] == "LowerThird" and a.provenance["style"] == "cinematic_realistic"
    from django.conf import settings

    seen = json.loads((Path(settings.DATA_DIR) / "remotion" / "jobs" / str(j["id"]) / "seen.json").read_text())
    assert seen["props"]["name"] == "نام" and seen["props"]["size"] == "vertical" and seen["props"]["kit"]["key"] == "cinematic_realistic", "the kit is resolved by the server"
    assert seen["browser"].endswith("msedge.exe") and seen["mode"] == "chrome-for-testing", "the browser InstAI found is the one that is used (never a download)"
    assert j["progress"] == 1.0 and j["resource"] == "cpu"


def test_a_frame_is_rendered_as_a_picture(api, worker, fake_toolchain):
    j = finish(api, worker, post_render(api, still=30))
    assert j["result"]["kind"] == "png" and j["result"]["url"].endswith(".png")
    from instai.assets.models import Asset

    assert Asset.objects.get(pk=j["result"]["asset_id"]).kind == "image"


def test_a_failed_render_says_why_in_persian(api, worker, fake_toolchain, monkeypatch):
    monkeypatch.setenv("FAKE_FAIL", "Failed to launch the browser process: spawn C:\\x ENOENT")
    j = finish(api, worker, post_render(api), expect="failed")
    assert "مرورگر" in j["error"] and "Failed to launch" in j["error"]
    monkeypatch.setenv("FAKE_FAIL", "something nobody knew")
    j = finish(api, worker, post_render(api, props={"title": "دوباره"}), expect="failed")
    assert "ساخت ویدئو با Remotion کامل نشد" in j["error"] and "something nobody knew" in j["error"]


def test_the_renders_list_names_files_and_errors(api, worker, fake_toolchain):
    finish(api, worker, post_render(api))
    rows = api.get("/api/remotion/renders").json()["renders"]
    assert rows[0]["status"] == "succeeded" and rows[0]["url"].endswith(".mp4") and rows[0]["composition"] == "TitleCard" and rows[0]["bytes"] == 2048


def test_the_setup_job_waits_while_the_background_setup_of_start_bat_runs(api, worker, tmp_path, monkeypatch):
    from instai.jobs.handlers import remotion as h
    from instai.jobs.models import Job
    from instai.remotion import toolchain

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "setup_remotion.py").write_text("print('another Remotion setup is already running')", encoding="utf-8")
    monkeypatch.setattr(h, "ROOT", tmp_path)
    state = {"s": {"ready": False, "state": "running", "error": ""}}
    monkeypatch.setattr(toolchain, "status", lambda: state["s"])
    jid = api.post("/api/remotion/setup", {}, format="json").json()["job"]["id"]
    worker.drain(3)
    j = Job.objects.get(pk=jid)
    assert j.status == Job.QUEUED and j.wait_code == "remotion_setup" and j.attempts == 0, "the lock is held by the run START.bat started: wait, do not report done"
    state["s"] = {"ready": True, "state": "ready", "error": ""}
    Job.objects.filter(pk=jid).update(run_after=j.created_at)
    worker.drain(3)
    j = Job.objects.get(pk=jid)
    assert j.status == Job.SUCCEEDED and j.result == {"ready": True}


def test_the_job_kinds_have_their_titles(api):
    from instai.jobs.describe import KIND_TEXT

    assert KIND_TEXT["remotion.render"][1] and KIND_TEXT["remotion.setup"][0]
    fa = (ROOT / "frontend" / "src" / "i18n" / "packs" / "remotion.ts").read_text(encoding="utf-8")
    assert "'job.kind.remotion.render'" in fa and "'job.kind.remotion.setup'" in fa


# ------------------------------------------------------------------ the automatic setup (stdlib script)

@pytest.fixture
def box(tmp_path, monkeypatch):
    """A fake PC: its own data / tools folders and no Node.js of its own."""
    monkeypatch.setenv("INSTAI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INSTAI_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("INSTAI_SETUP_FAST", "1")
    for k in ("INSTAI_NODE_EXE", "INSTAI_BROWSER", "INSTAI_NODE_ZIP_URL", "INSTAI_NODE_ZIP_SHA256", "INSTAI_NPM_REGISTRY", "INSTAI_REMOTION_AUTO"):
        monkeypatch.delenv(k, raising=False)
    for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):          # a real Windows PC would find its own Node.js / Chrome there
        monkeypatch.setenv(k, str(tmp_path / "nothing-here" / k))
    monkeypatch.setattr(sr.shutil, "which", lambda name: None)
    monkeypatch.setattr(sr, "node_version", lambda exe: "v24.1.0" if os.path.isfile(exe) else "")
    monkeypatch.setattr(sr, "WIN", True)
    return tmp_path


def node_zip(top: str = "node-v24.22.1-win-x64") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{top}/node.exe", "MZ fake")
        z.writestr(f"{top}/node_modules/npm/bin/npm-cli.js", "// npm")
        z.writestr(f"{top}/../evil.txt", "no")
    return buf.getvalue()


class Mirror:
    def __init__(self, files: dict[str, bytes], broken: tuple[str, ...] = ()):
        self.hits: list[str] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                if any(self.path.startswith(b) for b in broken) or self.path not in files:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = files[self.path]
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_the_portable_node_is_downloaded_verified_unpacked_once(box, monkeypatch):
    data = node_zip()
    m = Mirror({"/ok/node.zip": data})
    try:
        monkeypatch.setenv("INSTAI_NODE_ZIP_URL", m.url + "/ok/node.zip")
        monkeypatch.setenv("INSTAI_NODE_ZIP_SHA256", hashlib.sha256(data).hexdigest())
        found = sr.ensure_node()
        dest = box / "tools" / "node"
        assert found["source"] == "portable" and (dest / "node.exe").is_file() and (dest / "node_modules" / "npm" / "bin" / "npm-cli.js").is_file()
        assert not (box / "tools" / "evil.txt").exists() and not (box / "evil.txt").exists(), "a path that climbs out of the folder is dropped"
        assert sr.npm_cli(found["path"]).endswith("npm-cli.js")
        n = len(m.hits)
        assert sr.ensure_node()["path"] == found["path"] and len(m.hits) == n, "idempotent: nothing is downloaded the second time"
        assert (box / "data" / "logs" / "remotion-setup.log").read_text(encoding="utf-8").count("Node.js was not found") == 1
    finally:
        m.close()


def test_a_wrong_checksum_is_never_installed_and_a_dead_link_falls_through(box, monkeypatch):
    data = node_zip()
    m = Mirror({"/b/node.zip": data})
    try:
        monkeypatch.setenv("INSTAI_NODE_ZIP_URL", m.url + "/b/node.zip")
        monkeypatch.setenv("INSTAI_NODE_ZIP_SHA256", "0" * 64)
        with pytest.raises(RuntimeError, match="could not be downloaded"):
            sr.ensure_node()
        assert not (box / "tools" / "node").exists()
        # rotation: the first link is dead (404), the second serves the file
        dest = str(box / "x" / "n.zip")
        assert sr.download([m.url + "/dead.zip", m.url + "/b/node.zip"], dest, sha256=hashlib.sha256(data).hexdigest(), label="node") and Path(dest).read_bytes() == data
    finally:
        m.close()


def test_the_pcs_own_node_is_used_when_it_exists(box, monkeypatch, tmp_path):
    own = tmp_path / "Program Files" / "nodejs"
    own.mkdir(parents=True)
    (own / "node.exe").write_text("x")
    monkeypatch.setenv("INSTAI_NODE_EXE", str(own / "node.exe"))
    f = sr.ensure_node()
    assert f["source"] == "setting" and not (box / "tools").exists(), "nothing is downloaded when Node.js is there"


FAKE_NPM = r'''
import json, os, sys
args = sys.argv[1:]
open(os.path.join(os.path.dirname(__file__), "calls.txt"), "a").write(" ".join(args) + "\n")
reg = args[args.index("--registry") + 1]
if "npmjs" in reg and os.environ.get("NPMJS_BLOCKED"):
    print("npm error network timeout"); sys.exit(1)
cwd = os.getcwd()
for pkg in ("remotion", "@remotion/renderer", "@remotion/bundler", "react"):
    d = os.path.join(cwd, "node_modules", *pkg.split("/")); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "package.json"), "w").write(json.dumps({"name": pkg, "version": "4.0.538"}))
print("added 400 packages")
'''


def test_npm_packages_install_once_and_fall_back_to_the_mirror_registry(box, monkeypatch, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "package.json").write_text('{"name":"x","dependencies":{"remotion":"4.0.538"}}', encoding="utf-8")
    cli = tmp_path / "fakenpm.js"
    cli.write_text(FAKE_NPM, encoding="utf-8")
    monkeypatch.setattr(sr, "npm_cli", lambda node: str(cli))
    monkeypatch.setenv("NPMJS_BLOCKED", "1")
    node = {"path": sys.executable, "version": "v24.1.0", "source": "portable"}
    # the fake "node" is Python: the script is a Python file, which is all the runner needs
    sr.install_packages(node, str(proj))
    calls = (tmp_path / "calls.txt").read_text().splitlines()
    assert len(calls) == 2 and "registry.npmjs.org" in calls[0] and "registry.npmmirror.com" in calls[1] and calls[0].startswith("install"), "no lock file: npm install; the mirror after npmjs failed"
    assert sr.packages_ready(str(proj))
    rc = Path(box / "data" / "remotion" / "npmrc")
    assert "--userconfig" in calls[1] and str(rc) in calls[1] and "--globalconfig" in calls[1] and str(rc) + "-global" in calls[1], "npm gets our own config, never the user's ~/.npmrc (per-scope mirrors there may be dead)"
    assert rc.read_text(encoding="utf-8").startswith("registry=https://registry.npmmirror.com/") and "@" not in rc.read_text(encoding="utf-8")
    sr.install_packages(node, str(proj))
    assert len((tmp_path / "calls.txt").read_text().splitlines()) == 2, "idempotent: nothing runs the second time"
    (proj / "package.json").write_text('{"name":"x","dependencies":{"remotion":"4.0.539"}}', encoding="utf-8")
    assert not sr.packages_ready(str(proj)), "a changed package.json asks for a new install"
    (proj / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("NPMJS_BLOCKED")
    sr.install_packages(node, str(proj))
    assert (tmp_path / "calls.txt").read_text().splitlines()[-1].startswith("ci"), "with a lock file: npm ci"


def test_the_browser_is_the_pcs_own_chrome_or_edge_else_the_headless_shell(box, monkeypatch, tmp_path):
    edge = tmp_path / "Edge" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_text("x")
    monkeypatch.setenv("INSTAI_BROWSER", str(edge))
    assert sr.find_browser() == {"path": str(edge), "source": "setting", "mode": "chrome-for-testing"}
    shell = tmp_path / "tools" / "chrome-headless-shell" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe"
    shell.parent.mkdir(parents=True)
    shell.write_text("x")
    monkeypatch.setenv("INSTAI_BROWSER", str(shell))
    assert sr.find_browser()["mode"] == "headless-shell"
    monkeypatch.delenv("INSTAI_BROWSER")
    monkeypatch.setenv("INSTAI_TOOLS_DIR", str(tmp_path / "tools"))
    assert sr.find_browser()["source"] == "downloaded" and sr.find_browser()["mode"] == "headless-shell"
    assert sr.is_headless_shell("C:\\x\\chrome-headless-shell.exe") and not sr.is_headless_shell("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")


def test_status_check_and_the_background_start(box, monkeypatch, capsys):
    assert sr.main(["--check"]) == 1 and json.loads(capsys.readouterr().out)["ready"] is False
    spawned = []
    monkeypatch.setattr(sr.subprocess, "Popen", lambda *a, **k: spawned.append(a) or None)
    monkeypatch.setattr(sr, "folders", lambda: {**_folders(box), "project": str(box)})
    assert sr.background() == 0 and len(spawned) == 1, "something is missing: the setup starts detached and START.bat goes on"
    monkeypatch.setenv("INSTAI_REMOTION_AUTO", "0")
    assert sr.background() == 0 and len(spawned) == 1, "switched off: nothing starts"
    monkeypatch.delenv("INSTAI_REMOTION_AUTO")
    monkeypatch.setattr(sr, "status_now", lambda: {"ready": True, "node": {}, "packages": True, "browser": {}})
    assert sr.background() == 0 and len(spawned) == 1, "ready: nothing starts"


def _folders(box: Path) -> dict:
    data = str(box / "data")
    return {"root": str(ROOT), "data": data, "tools": str(box / "tools"), "project": str(REMOTION), "work": os.path.join(data, "remotion"),
            "status": os.path.join(data, "remotion", "status.json"), "log": os.path.join(data, "logs", "remotion-setup.log"), "lock": os.path.join(data, "remotion", "setup.lock")}


def test_the_whole_setup_end_to_end_with_stand_ins(box, monkeypatch, tmp_path):
    """Node.js (portable zip) -> npm packages -> browser -> proof: the status file the page reads says ready, and a second run changes nothing."""
    data = node_zip()
    m = Mirror({"/n.zip": data})
    edge = tmp_path / "Edge" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_text("x")
    cli = tmp_path / "fakenpm.js"
    cli.write_text(FAKE_NPM, encoding="utf-8")
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    try:
        monkeypatch.setenv("INSTAI_NODE_ZIP_URL", m.url + "/n.zip")
        monkeypatch.setenv("INSTAI_NODE_ZIP_SHA256", hashlib.sha256(data).hexdigest())
        monkeypatch.setenv("INSTAI_BROWSER", str(edge))
        monkeypatch.setattr(sr, "folders", lambda: {**_folders(box), "project": str(proj)})
        monkeypatch.setattr(sr, "npm_cli", lambda node: str(cli))
        monkeypatch.setattr(sr, "probe", lambda node, project=None: {"renderer": True, "remotion": "4.0.538"})
        # the "node" that runs the fake npm script is Python: point the portable node entry at it for the run
        real_find = sr.find_node
        monkeypatch.setattr(sr, "find_node", lambda: (lambda f: {**f, "path": sys.executable} if f else None)(real_find()))
        assert sr.setup() == 0
        st = sr.read_status()
        assert st["state"] == "ready" and st["ready"] is True and st["remotion"] == "4.0.538" and st["node"]["version"] == "v24.1.0" and st["browser"]["path"] == str(edge)
        assert sr.status_now()["ready"] is True
        hits = len(m.hits)
        assert sr.setup() == 0 and len(m.hits) == hits and len((tmp_path / "calls.txt").read_text().splitlines()) == 1, "idempotent"
        assert not Path(_folders(box)["lock"]).exists(), "the lock is released"
    finally:
        m.close()


def test_a_failed_setup_is_written_for_the_page_and_the_next_run_can_continue(box, monkeypatch, tmp_path):
    monkeypatch.setattr(sr, "folders", lambda: {**_folders(box), "project": str(tmp_path / "proj")})
    monkeypatch.setattr(sr, "ensure_node", lambda: (_ for _ in ()).throw(RuntimeError("Node.js could not be downloaded (no internet)")))
    assert sr.setup() == 1
    st = sr.read_status()
    assert st["state"] == "error" and "no internet" in st["error"] and st["message_fa"].startswith("نصب Remotion") and st["ready"] is False
    from instai.remotion import toolchain

    monkeypatch.setattr(toolchain, "setup_module", lambda: sr)
    assert toolchain.status()["state"] == "error" and "no internet" in toolchain.status()["error"]


def test_start_scripts_start_the_background_setup():
    for name in ("START.bat",):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert 'scripts\\setup_remotion.py --background' in text, "START.bat starts the Remotion setup by itself"
        assert text.index("setup_remotion.py") > text.index("bootstrap.py"), "after the packages are installed"


# ------------------------------------------------------------------ the real thing (only where the toolchain exists)

@pytest.mark.skipif(os.environ.get("INSTAI_REMOTION_REAL") != "1", reason="set INSTAI_REMOTION_REAL=1 on a PC that has run scripts/setup_remotion.py")
@pytest.mark.slow
def test_real_render_of_every_composition(api, worker):
    from instai.remotion import toolchain

    st = toolchain.status()
    assert st["ready"], st
    for comp, props in (("TitleCard", {"title": "چغر", "subtitle": "مربی ورزشی همراه شما"}), ("KineticText", {"lines": ["*یک* ایده", "دو ایده"]}),
                        ("Explainer", {"title": "سه گام", "steps": [{"title": "یک", "body": "الف"}, {"title": "دو", "body": "ب"}], "outro": "تمام"}), ("LowerThird", {"name": "نام", "role": "سمت"})):
        j = finish(api, worker, post_render(api, composition=comp, props=props, still=20, size="square"))
        assert j["result"]["kind"] == "png" and j["result"]["bytes"] > 5000, (comp, j["result"])
    j = finish(api, worker, post_render(api, composition="TitleCard", props={"title": "ویدئو"}, size="square"))
    assert j["result"]["kind"] == "mp4" and j["result"]["bytes"] > 20000 and j["result"]["frames"] == 150
