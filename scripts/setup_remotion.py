#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remotion toolchain for InstAI (code-to-video page): makes sure this PC can render the compositions in remotion/, by itself.

Python 3.8+ standard library only (it runs before / beside the app). Console text is English / ASCII; progress is also written to
data/remotion/status.json (the Remotion page shows it) and data/logs/remotion-setup.log. Every step is idempotent: running it again
when everything is ready takes a second and changes nothing.

  python scripts/setup_remotion.py                     install what is missing (Node.js, the npm packages, a browser) and check it
  python scripts/setup_remotion.py --check             exit 0 when everything is ready (prints the status as JSON), else 1; installs nothing
  python scripts/setup_remotion.py --background        START.bat: start the installation detached when something is missing, return at once

Steps
  1. Node.js >= 18: INSTAI_NODE_EXE, tools/node, the PC's own Node (PATH, Program Files). Missing -> the portable Node zip (about 38 MB, Windows
     x64) from nodejs.org, else the npmmirror.com mirror; the zip's sha256 is pinned here (checked against nodejs.org's SHASUMS256.txt on 2026-11-13).
     It is unpacked into tools/node (nothing is installed system-wide, nothing in PATH is changed).
  2. The npm packages of remotion/package.json (remotion, @remotion/bundler, @remotion/renderer, react, react-dom; ~300 MB) with the npm that
     belongs to that Node: `npm ci` when package-lock.json exists, else `npm install`; registry.npmjs.org first, then registry.npmmirror.com.
  3. A browser for the renderer: Chrome or Edge already on the PC (Windows 11 always has Edge), else the "chrome-headless-shell" from the
     npmmirror.com mirror of Chrome for Testing (storage.googleapis.com, where Remotion itself would download from, is blocked in Iran).
  4. `node remotion/render.mjs --probe` proves the packages load.
Switch off the automatic start-up run with INSTAI_REMOTION_AUTO=0 (environment or .env); the Remotion page can still run it by a button.
Licence (LICENSE.md of remotion-dev/remotion, read 2026-11-13): free for an individual, a for-profit organisation with up to 3 employees, a non-profit,
or while evaluating; any larger company needs a Company License (https://github.com/remotion-dev/remotion/blob/main/LICENSE.md);
the packages are installed from npm on the owner's PC, nothing of Remotion is copied into the InstAI repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_VERSION = "24.22.1"
NODE_ZIP = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_SHA256 = "d2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5"
NODE_URLS = [f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ZIP}", f"https://cdn.npmmirror.com/binaries/node/v{NODE_VERSION}/{NODE_ZIP}",
             f"https://registry.npmmirror.com/-/binary/node/v{NODE_VERSION}/{NODE_ZIP}"]
REGISTRIES = ["https://registry.npmjs.org", "https://registry.npmmirror.com"]
HEADLESS_VERSION = "157.0.8103.78"
HEADLESS_URLS = [f"https://cdn.npmmirror.com/binaries/chrome-for-testing/{HEADLESS_VERSION}/win64/chrome-headless-shell-win64.zip",
                 f"https://registry.npmmirror.com/-/binary/chrome-for-testing/{HEADLESS_VERSION}/win64/chrome-headless-shell-win64.zip"]
MIN_NODE = 18
MIN_FREE_GB = 1.5
UA = "InstAI-remotion-setup/1.0"
LOCK_STALE_SECONDS = 2 * 3600
WIN = os.name == "nt"


# ------------------------------------------------------------------ folders, log, status

def folders() -> dict:
    data = os.environ.get("INSTAI_DATA_DIR") or os.path.join(ROOT, "data")
    tools = os.environ.get("INSTAI_TOOLS_DIR") or os.path.join(ROOT, "tools")
    return {"root": ROOT, "data": data, "tools": tools, "project": os.path.join(ROOT, "remotion"), "work": os.path.join(data, "remotion"),
            "status": os.path.join(data, "remotion", "status.json"), "log": os.path.join(data, "logs", "remotion-setup.log"),
            "lock": os.path.join(data, "remotion", "setup.lock")}


def say(tag: str, msg: str) -> None:
    line = f"  [{tag}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    f = folders()
    try:
        os.makedirs(os.path.dirname(f["log"]), exist_ok=True)
        with open(f["log"], "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"{tag} {msg}\n")
    except OSError:
        pass


def read_status() -> dict:
    try:
        with open(folders()["status"], encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write_status(**fields) -> dict:
    """Merge `fields` into data/remotion/status.json (atomic). The page polls this file."""
    f = folders()
    st = read_status()
    st.update(fields)
    st["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(f["work"], exist_ok=True)
    tmp = f["status"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, f["status"])
    return st


def env_value(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8-sig") as fh:
            for line in fh:
                m = re.match(r"^\s*%s\s*=\s*(.*?)\s*$" % re.escape(name), line)
                if m:
                    return m.group(1).strip("\"'")
    except OSError:
        pass
    return ""


# ------------------------------------------------------------------ 1. Node.js

def node_version(exe: str) -> str:
    try:
        out = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return out if re.fullmatch(r"v\d+\.\d+\.\d+", out) else ""


def node_ok(version: str) -> bool:
    m = re.match(r"v(\d+)\.", version or "")
    return bool(m and int(m.group(1)) >= MIN_NODE)


def find_node() -> dict | None:
    """{path, version, source} of a usable Node.js (>= 18) or None. Order: INSTAI_NODE_EXE, tools/node (ours), the PC's own."""
    f = folders()
    exe = "node.exe" if WIN else "node"
    cands: list[tuple[str, str]] = []
    if env_value("INSTAI_NODE_EXE"):
        cands.append((env_value("INSTAI_NODE_EXE"), "setting"))
    for base in (os.path.join(f["tools"], "node"), f["tools"]):
        if os.path.isdir(base):
            for rel in (exe, os.path.join("bin", exe)):
                cands.append((os.path.join(base, rel), "portable"))
            for sub in sorted(os.listdir(base)):
                if sub.startswith("node-v"):
                    cands.append((os.path.join(base, sub, exe), "portable"))
    which = shutil.which("node")
    if which:
        cands.append((which, "system"))
    if WIN:
        for pf in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
            if pf:
                cands.append((os.path.join(pf, "nodejs", "node.exe"), "system"))
    seen = set()
    for path, source in cands:
        key = os.path.normcase(path)
        if key in seen or not os.path.isfile(path):
            continue
        seen.add(key)
        v = node_version(path)
        if node_ok(v):
            return {"path": path, "version": v, "source": source}
    return None


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(urls: list[str], dest: str, *, sha256: str | None = None, label: str = "file", retries: int = 3) -> bool:
    """Download with the links in rotation (a blocked host costs one failed try, not minutes); resumes the .part file; checks the sha256."""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    live = list(urls)
    for attempt in range(1, retries * max(1, len(urls)) + 1):
        if not live:
            break
        url = live[(attempt - 1) % len(live)]
        start = os.path.getsize(part) if os.path.exists(part) else 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": f"bytes={start}-"} if start else {})})
            with urllib.request.urlopen(req, timeout=45) as r:
                if start and getattr(r, "status", 200) != 206:
                    start = 0
                total = int(r.headers.get("Content-Length") or 0) + start
                done, step = start, -1
                with open(part, "ab" if start else "wb") as fh:
                    while True:
                        chunk = r.read(1 << 18)
                        if not chunk:
                            break
                        fh.write(chunk)
                        done += len(chunk)
                        if total and done * 10 // total != step:
                            step = done * 10 // total
                            say("..", f"downloading {label}: {done * 100 // total}% ({done // (1 << 20)} MB)")
            if sha256 and sha256_file(part).lower() != sha256.lower():
                os.replace(part, part + ".bad")
                say("!!", f"{label}: the downloaded file does not match its checksum (from {url.split('//')[1].split('/')[0]}); trying another link")
                live.remove(url)
                continue
            os.replace(part, dest)
            return True
        except urllib.error.HTTPError as e:
            say("..", f"{label}: HTTP {e.code} from {url.split('//')[1].split('/')[0]}")
            if e.code in (401, 403, 404):
                live.remove(url)
        except Exception as e:  # noqa: BLE001
            say("..", f"{label}: attempt {attempt} failed ({type(e).__name__}) on {url.split('//')[1].split('/')[0]}")
            time.sleep(0 if os.environ.get("INSTAI_SETUP_FAST") else min(10, attempt))
    return False


def ensure_node() -> dict:
    """A usable Node.js; downloads the portable zip into tools/node when the PC has none. Raises RuntimeError with a plain reason."""
    found = find_node()
    if found:
        say("OK", f"Node.js {found['version']} ({found['source']}): {found['path']}")
        return found
    if not WIN and not os.environ.get("INSTAI_NODE_ZIP_URL"):
        raise RuntimeError("Node.js 18 or newer was not found (the automatic portable download is for Windows). Install Node.js from nodejs.org.")
    urls = [os.environ["INSTAI_NODE_ZIP_URL"]] if os.environ.get("INSTAI_NODE_ZIP_URL") else NODE_URLS
    want = os.environ.get("INSTAI_NODE_ZIP_SHA256") or NODE_SHA256
    f = folders()
    check_space(f["tools"], 0.3)
    zpath = os.path.join(f["work"], "cache", NODE_ZIP)
    say("..", f"Node.js was not found; downloading the portable Node.js {NODE_VERSION} (about 38 MB, once) ...")
    write_status(phase="node", message_fa="در حال دانلود Node.js قابل‌حمل (حدود ۳۸ مگابایت)", message_en="Downloading portable Node.js (about 38 MB)")
    if not (os.path.isfile(zpath) and sha256_file(zpath) == want) and not download(urls, zpath, sha256=want, label="Node.js"):
        raise RuntimeError("Node.js could not be downloaded (no internet, or nodejs.org and the mirror are blocked).")
    dest = os.path.join(f["tools"], "node")
    tmp = dest + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n and not n.endswith("/")]
        tops = {n.split("/", 1)[0] for n in names}
        strip = len(tops) == 1 and all("/" in n for n in names)
        for n in names:
            rel = n.split("/", 1)[1] if strip else n
            parts = rel.replace("\\", "/").split("/")
            if ".." in parts or rel.startswith("/") or ":" in parts[0]:
                continue
            out = os.path.join(tmp, *parts)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    if os.path.isdir(dest):
        shutil.rmtree(dest + ".old", ignore_errors=True)
        os.replace(dest, dest + ".old")
    os.replace(tmp, dest)
    shutil.rmtree(dest + ".old", ignore_errors=True)
    try:
        os.remove(zpath)
    except OSError:
        pass
    found = find_node()
    if not found:
        raise RuntimeError("the portable Node.js was unpacked but does not start")
    say("OK", f"portable Node.js {found['version']} installed in {os.path.relpath(dest, ROOT)}")
    return found


def check_space(path: str, need_gb: float) -> None:
    probe = path
    while probe and not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    free = shutil.disk_usage(probe or ROOT).free / (1 << 30)
    if free < need_gb:
        raise RuntimeError(f"not enough free disk space on {os.path.splitdrive(os.path.abspath(probe))[0] or '/'} ({free:.1f} GB free, {need_gb:.1f} GB needed)")


# ------------------------------------------------------------------ 2. npm packages

def project_hash(project: str) -> str:
    h = hashlib.sha256()
    for name in ("package.json", "package-lock.json"):
        p = os.path.join(project, name)
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                h.update(fh.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:20]


def packages_ready(project: str | None = None) -> bool:
    project = project or folders()["project"]
    marker = os.path.join(project, "node_modules", ".instai-installed")
    try:
        with open(marker, encoding="utf-8") as fh:
            same = fh.read().strip() == project_hash(project)
    except OSError:
        same = False
    return same and os.path.isfile(os.path.join(project, "node_modules", "remotion", "package.json")) \
        and os.path.isfile(os.path.join(project, "node_modules", "@remotion", "renderer", "package.json"))


def npm_cli(node: str) -> str | None:
    """npm's own script that belongs to this Node (run as `node npm-cli.js ...`: no .cmd files, no quoting trouble with spaces)."""
    d = os.path.dirname(os.path.abspath(node))
    for rel in (("node_modules", "npm", "bin", "npm-cli.js"), ("..", "lib", "node_modules", "npm", "bin", "npm-cli.js")):
        p = os.path.normpath(os.path.join(d, *rel))
        if os.path.isfile(p):
            return p
    return None


def run_stream(cmd: list[str], cwd: str, env: dict | None = None, timeout: float = 3600, tag: str = "npm") -> int:
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    end = time.time() + timeout
    assert p.stdout is not None
    for line in p.stdout:
        line = line.rstrip()
        if line:
            say(tag, line[:300])
        if time.time() > end:
            p.kill()
            return 124
    return p.wait()


def isolated_npmrc(registry: str) -> str:
    """A minimal npm config file of our own (data/remotion/npmrc): this registry for every package, no scope overrides, no auth, no proxy tricks."""
    f = folders()
    os.makedirs(f["work"], exist_ok=True)
    path = os.path.join(f["work"], "npmrc")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"registry={registry}/\naudit=false\nfund=false\nupdate-notifier=false\nengine-strict=false\n")
    return path


def install_packages(node: dict, project: str | None = None) -> None:
    f = folders()
    project = project or f["project"]
    if packages_ready(project):
        say("OK", "the Remotion packages are installed")
        return
    cli = npm_cli(node["path"])
    if not cli:
        raise RuntimeError("npm was not found next to Node.js")
    check_space(project, MIN_FREE_GB)
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(os.path.abspath(node["path"])) + os.pathsep + env.get("PATH", "")
    env["npm_config_update_notifier"] = "false"
    env["npm_config_fund"] = "false"
    env["npm_config_audit"] = "false"
    env["npm_config_loglevel"] = "error"
    lock = os.path.isfile(os.path.join(project, "package-lock.json"))
    write_status(phase="packages", message_fa="در حال نصب بسته‌های Remotion (حدود ۳۰۰ مگابایت؛ بار اول چند دقیقه)", message_en="Installing the Remotion packages (about 300 MB; a few minutes the first time)")
    last = 1
    for registry in ([os.environ["INSTAI_NPM_REGISTRY"]] if os.environ.get("INSTAI_NPM_REGISTRY") else REGISTRIES):
        say("..", f"installing the Remotion packages from {registry.split('//')[1]} ({'npm ci' if lock else 'npm install'}) ...")
        # npm reads the user's own ~/.npmrc too, and a PC in Iran often has per-scope mirrors there (e.g. "@webassemblyjs:registry=https://npm.xxx.ir")
        # that no longer answer: that would fail an install whose registry is fine. So npm gets OUR config file and nothing else.
        rc = isolated_npmrc(registry)
        grc = rc + "-global"                      # npm refuses the same file as both the user and the global config
        with open(grc, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("; InstAI: empty on purpose (no global npm settings are used)\n")
        env["npm_config_userconfig"] = rc
        env["npm_config_globalconfig"] = grc
        cmd = [node["path"], cli, "ci" if lock else "install", "--no-audit", "--no-fund", "--no-progress", "--registry", registry, "--userconfig", rc,
               "--globalconfig", grc, "--fetch-retries", "4", "--fetch-retry-mintimeout", "4000"]
        last = run_stream(cmd, project, env)
        if last == 0 and os.path.isfile(os.path.join(project, "node_modules", "remotion", "package.json")):
            break
        say("..", f"npm stopped with code {last}; " + ("trying the next registry" if registry != (REGISTRIES[-1]) else "giving up"))
    if last != 0:
        raise RuntimeError(f"the npm packages could not be installed (npm exit code {last}); see data/logs/remotion-setup.log")
    os.makedirs(os.path.join(project, "node_modules"), exist_ok=True)
    with open(os.path.join(project, "node_modules", ".instai-installed"), "w", encoding="utf-8") as fh:
        fh.write(project_hash(project))
    say("OK", "the Remotion packages are installed")


# ------------------------------------------------------------------ 3. the browser

def is_headless_shell(path: str) -> bool:
    b = os.path.basename(path).lower()
    return "headless" in b or "headless_shell" in b


def browser_candidates() -> list[tuple[str, str]]:
    f = folders()
    out: list[tuple[str, str]] = []
    if env_value("INSTAI_BROWSER"):
        out.append((env_value("INSTAI_BROWSER"), "setting"))
    shell = "chrome-headless-shell.exe" if WIN else "chrome-headless-shell"
    base = os.path.join(f["tools"], "chrome-headless-shell")
    if os.path.isdir(base):
        for root, _d, files in os.walk(base):
            if shell in files:
                out.append((os.path.join(root, shell), "downloaded"))
    if WIN:
        pf, pf86, local = os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("LOCALAPPDATA", "")
        for p in (os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"), os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                  os.path.join(local, "Google", "Chrome", "Application", "chrome.exe") if local else "",
                  os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"), os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe")):
            if p:
                out.append((p, "system"))
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            w = shutil.which(name)
            if w:
                out.append((w, "system"))
    return [(p, s) for p, s in out if p and os.path.isfile(p)]


def find_browser() -> dict | None:
    """{path, source, mode}: `mode` is Remotion's chromeMode: a headless-shell binary -> 'headless-shell', a normal Chrome / Edge -> 'chrome-for-testing'."""
    for p, s in browser_candidates():
        return {"path": p, "source": s, "mode": "headless-shell" if is_headless_shell(p) else "chrome-for-testing"}
    return None


def ensure_browser() -> dict:
    found = find_browser()
    if found:
        say("OK", f"browser for the renderer: {found['path']} ({found['source']})")
        return found
    if not WIN:
        raise RuntimeError("no Chrome / Chromium was found; install one or set INSTAI_BROWSER")
    f = folders()
    check_space(f["tools"], 0.6)
    say("..", f"no Chrome or Edge found; downloading Chrome headless shell {HEADLESS_VERSION} from the mirror (about 100 MB, once) ...")
    write_status(phase="browser", message_fa="در حال دانلود مرورگر بی‌سر (Chrome headless shell، حدود ۱۰۰ مگابایت)", message_en="Downloading the headless Chrome shell (about 100 MB)")
    zpath = os.path.join(f["work"], "cache", "chrome-headless-shell-win64.zip")
    if not download(HEADLESS_URLS, zpath, label="Chrome headless shell"):
        raise RuntimeError("no browser found and the headless shell could not be downloaded")
    dest = os.path.join(f["tools"], "chrome-headless-shell")
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            parts = n.replace("\\", "/").split("/")
            if n.endswith("/") or ".." in parts or ":" in parts[0]:
                continue
            out = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    try:
        os.remove(zpath)
    except OSError:
        pass
    found = find_browser()
    if not found:
        raise RuntimeError("the headless shell was unpacked but chrome-headless-shell.exe is missing")
    say("OK", f"headless Chrome installed: {found['path']}")
    return found


# ------------------------------------------------------------------ 4. proof

def probe(node: dict, project: str | None = None) -> dict:
    project = project or folders()["project"]
    p = subprocess.run([node["path"], os.path.join(project, "render.mjs"), "--probe"], cwd=project, capture_output=True, text=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), encoding="utf-8", errors="replace")
    for line in p.stdout.splitlines():
        if line.startswith("INSTAI_REMOTION "):
            try:
                j = json.loads(line[len("INSTAI_REMOTION "):])
                if j.get("event") == "probe":
                    return j
            except ValueError:
                pass
    return {"renderer": False, "error": (p.stderr or p.stdout or "no answer")[-300:]}


# ------------------------------------------------------------------ the whole run

def status_now() -> dict:
    """What is ready right now, without installing anything: {ready, node, packages, browser}."""
    node = find_node()
    pk = packages_ready()
    br = find_browser()
    return {"ready": bool(node and pk and br), "node": node, "packages": pk, "browser": br}


def lock_acquire() -> bool:
    f = folders()
    os.makedirs(f["work"], exist_ok=True)
    try:
        if os.path.exists(f["lock"]) and time.time() - os.path.getmtime(f["lock"]) < LOCK_STALE_SECONDS:
            try:
                pid = int(open(f["lock"], encoding="utf-8").read().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and pid != os.getpid() and pid_alive(pid):
                return False
        with open(f["lock"], "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        return True
    except OSError:
        return True


def pid_alive(pid: int) -> bool:
    try:
        if WIN:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=15,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def lock_release() -> None:
    try:
        os.remove(folders()["lock"])
    except OSError:
        pass


def setup() -> int:
    if not lock_acquire():
        say("..", "another Remotion setup is already running")
        return 0
    try:
        write_status(state="running", phase="start", error="", message_fa="بررسی ابزارهای Remotion ...", message_en="Checking the Remotion tools ...", started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        node = ensure_node()
        write_status(node=node)
        install_packages(node)
        browser = ensure_browser()
        write_status(browser=browser, packages=True, phase="probe", message_fa="در حال آزمایش ...", message_en="Testing ...")
        pr = probe(node)
        if not pr.get("renderer"):
            raise RuntimeError("the Remotion renderer did not load: " + str(pr.get("error", ""))[:200])
        write_status(state="ready", phase="done", ready=True, remotion=pr.get("remotion"), error="", message_fa="Remotion آماده است.", message_en="Remotion is ready.", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        say("OK", f"Remotion {pr.get('remotion')} is ready (Node {node['version']}, browser {os.path.basename(browser['path'])})")
        return 0
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:400]
        write_status(state="error", ready=False, error=msg, message_fa="نصب Remotion کامل نشد: " + msg, message_en="The Remotion setup did not finish: " + msg)
        say("!!", msg)
        return 1
    finally:
        lock_release()


def background() -> int:
    """START.bat: when something is missing, run the setup in a detached process and return at once (the start-up must not wait for 300 MB)."""
    if env_value("INSTAI_REMOTION_AUTO") in ("0", "false", "no"):
        say("..", "the automatic Remotion setup is switched off (INSTAI_REMOTION_AUTO=0)")
        return 0
    if not os.path.isdir(folders()["project"]):
        return 0
    st = status_now()
    if st["ready"]:
        say("OK", "Remotion is ready")
        return 0
    cur = read_status()
    if cur.get("state") == "running" and os.path.exists(folders()["lock"]) and time.time() - os.path.getmtime(folders()["lock"]) < LOCK_STALE_SECONDS:
        say("..", "the Remotion setup is already running in the background")
        return 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True, **({} if WIN else {"start_new_session": True}))
    say("OK", "Remotion (code-to-video) is being set up in the background; the Remotion page shows the progress")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        st = status_now()
        print(json.dumps(st, ensure_ascii=False))
        return 0 if st["ready"] else 1
    if "--background" in argv:
        return background()
    return setup()


if __name__ == "__main__":
    sys.exit(main())
