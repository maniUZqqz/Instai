#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InstAI self-update: START.bat / START-WORKER.bat call this first so the next double-click brings the latest version from GitHub (main).
Python 3.8+ standard library only (it runs with the project's venv, or any Python, before anything else is installed). Console text is
English / ASCII on purpose (the Windows console garbles Persian); everything is also written to data\\logs\\update.log.

  python scripts/self_update.py             update when GitHub's main is newer (never blocks start-up: every problem ends with "continuing")
  python scripts/self_update.py --check     only say whether an update is available
  python scripts/self_update.py --force     also re-apply the same version and allow a lower version number
  python scripts/self_update.py --worker    PC B (START-WORKER.bat): the same, but a running server is not looked for

How (the owner's folder is usually a GitHub "Download ZIP", not a git clone):
  * a git clone  -> `git fetch` + fast-forward only; local changes in tracked files stop the update (never overwritten);
  * anything else -> the codeload ZIP of main (the same file as "Code > Download ZIP"), unpacked in memory, checked
    (VERSION, manage.py, every .py compiles), then copied over the folder.
  Never touched, never deleted: data, data-worker, .env, .venv*, models, tools, vendor, venvs, media, logs, .git, node_modules.
  Every file that is replaced is first copied into data\\update\\backup-<time>.zip (the last 3 are kept); if copying fails half-way
  everything is put back. A file that was shipped by an earlier update and is gone upstream is removed (backed up first); files InstAI
  never shipped are never deleted. The server is not touched while it runs (replacing code under a running server window is what
  breaks things): "already running" -> the update waits for the next STOP.bat + START.bat.
  Version rule: a lower VERSION on GitHub than in the folder is not installed (no downgrade) unless --force.

Exit code: 0 = nothing to do / continue, 10 = updated AND a start script itself changed (START.bat re-runs itself), 1 = a problem (start goes on).
Environment: INSTAI_NO_UPDATE=1 (or INSTAI_AUTO_UPDATE=0 in .env) switches it off; INSTAI_UPDATE_REPO, INSTAI_UPDATE_BRANCH,
INSTAI_UPDATE_API, INSTAI_UPDATE_ZIP (tests point them at a local server).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPO = "maniUZqqz/Instai"
DEFAULT_BRANCH = "main"
UA = "InstAI-self-update/1.0"
#: top-level names that belong to the owner's PC, never to the program: never overwritten, never deleted
PROTECTED = {".git", ".venv", ".env", "data", "data-worker", "models", "tools", "vendor", "venvs", "node_modules", "logs", "media"}
KEEP_BACKUPS = 3
SELF_SCRIPTS = ("START.bat", "START-WORKER.bat")

UPDATED_SCRIPTS = 10


# ------------------------------------------------------------------ small helpers

def data_dir() -> str:
    return os.path.join(ROOT, "data")                  # not INSTAI_DATA_DIR: the worker PC has its own data folder but the same code folder


def say(tag: str, msg: str) -> None:
    line = f"  [{tag}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    try:
        os.makedirs(os.path.join(data_dir(), "logs"), exist_ok=True)
        with open(os.path.join(data_dir(), "logs", "update.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"{tag} {msg}\n")
    except OSError:
        pass


def read_env_file() -> dict:
    out: dict = {}
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name) or read_env_file().get(name) or default


def parse_version(text: str) -> tuple:
    try:
        return tuple(int(x) for x in text.strip().splitlines()[0].strip().split("."))
    except (ValueError, IndexError):
        return (0, 0, 0)


def local_version() -> str:
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return "0.0.0"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def state_path() -> str:
    return os.path.join(data_dir(), "update", "state.json")


def load_state() -> dict:
    try:
        with open(state_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(state_path()), exist_ok=True)
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, state_path())


def is_protected(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    # `node_modules` at ANY depth belongs to the owner's PC (frontend/node_modules after an `npm install`): the repository once held a symlink of
    # that name, which a ZIP turns into a 39-byte file that cannot replace a directory (the whole update then failed for ever)
    return parts[0] in PROTECTED or parts[0].startswith(".venv") or "node_modules" in parts


def server_running() -> bool:
    env = {**read_env_file(), **{k: v for k, v in os.environ.items() if k.startswith("INSTAI_")}}
    host = env.get("INSTAI_HOST", "127.0.0.1")
    host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        with urllib.request.urlopen(f"http://{host}:{env.get('INSTAI_PORT', '8765')}/api/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------ talking to GitHub

def http_get(url: str, timeout: float, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def remote_commit(repo: str, branch: str) -> str:
    """The commit GitHub's branch points at ('' when it cannot be told: offline, rate limit ...)."""
    api = setting("INSTAI_UPDATE_API", "https://api.github.com").rstrip("/")
    try:
        sha = http_get(f"{api}/repos/{repo}/commits/{branch}", 10, {"Accept": "application/vnd.github.sha"}).decode("ascii", "ignore").strip()
        return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else ""
    except Exception:  # noqa: BLE001
        return ""


def zip_urls(repo: str, branch: str) -> list[str]:
    custom = setting("INSTAI_UPDATE_ZIP")
    if custom:
        return [custom]
    return [f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}", f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"]


def download_zip(urls: list[str], dest: str) -> bool:
    for url in urls:
        for attempt in (1, 2, 3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r, open(dest + ".part", "wb") as f:
                    total = int(r.headers.get("Content-Length") or 0)
                    done, step = 0, 0
                    while True:
                        chunk = r.read(1 << 18)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and done * 10 // total > step:
                            step = done * 10 // total
                            say("..", f"downloading the update: {done * 100 // total}% ({done // 1024} KB)")
                if not zipfile.is_zipfile(dest + ".part"):
                    raise OSError("the download is not a ZIP file")
                os.replace(dest + ".part", dest)
                return True
            except urllib.error.HTTPError as e:
                say("..", f"GitHub answered HTTP {e.code} for {url.split('//')[1].split('/')[0]}"
                    + (" (the repository is private or the branch does not exist)" if e.code in (401, 403, 404) else ""))
                break
            except Exception as e:  # noqa: BLE001
                say("..", f"download attempt {attempt}/3 failed ({type(e).__name__}); " + ("retrying" if attempt < 3 else "next link"))
                time.sleep(0 if os.environ.get("INSTAI_UPDATE_FAST") else 2 * attempt)
    return False


# ------------------------------------------------------------------ reading and checking the archive

def archive_files(z: zipfile.ZipFile) -> dict:
    """{relative path: bytes} of a GitHub archive (the single top folder is stripped; directories and unsafe names are skipped)."""
    names = [n for n in z.namelist() if n and not n.endswith("/")]
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) != 1:
        raise ValueError("the archive has an unexpected layout")
    out: dict = {}
    for n in names:
        rel = n.split("/", 1)[1] if "/" in n else ""
        parts = rel.replace("\\", "/").split("/")
        if not rel or ".." in parts or rel.startswith("/") or ":" in parts[0]:
            continue
        data = z.read(n)
        if rel.lower().endswith((".bat", ".cmd")) and b"\r\n" not in data:
            data = data.replace(b"\n", b"\r\n")           # cmd.exe needs CRLF in a batch file (GitHub's ZIP already has it; this is the safety net for any other source)
        out[rel.replace("\\", "/")] = data
    return out


def check_archive(files: dict) -> str:
    """Raise ValueError when the archive is not a usable InstAI; returns its VERSION."""
    for need in ("VERSION", "manage.py", "instai/__init__.py", "scripts/self_update.py", "START.bat"):
        if need not in files:
            raise ValueError(f"the archive has no {need}")
    version = files["VERSION"].decode("utf-8", "ignore").strip().splitlines()[0].strip()
    if parse_version(version) == (0, 0, 0):
        raise ValueError("the archive's VERSION is not valid")
    with tempfile.TemporaryDirectory(prefix="instai-upd-") as tmp:
        for rel, data in files.items():
            if rel.endswith(".py"):
                p = os.path.join(tmp, "f.py")
                with open(p, "wb") as f:
                    f.write(data)
                try:
                    py_compile.compile(p, cfile=os.path.join(tmp, "f.pyc"), doraise=True)
                except py_compile.PyCompileError as e:
                    raise ValueError(f"{rel} does not compile: {str(e).splitlines()[-1][:120]}") from e
    return version


# ------------------------------------------------------------------ applying

def make_backup(paths: list[str]) -> str | None:
    """Zip the files that are about to be replaced / removed into data\\update\\backup-<time>.zip; keep the last KEEP_BACKUPS."""
    paths = [p for p in paths if os.path.isfile(os.path.join(ROOT, *p.split("/")))]
    if not paths:
        return None
    folder = os.path.join(data_dir(), "update")
    os.makedirs(folder, exist_ok=True)
    name = os.path.join(folder, time.strftime("backup-%Y%m%d-%H%M%S") + ".zip")
    with zipfile.ZipFile(name, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(os.path.join(ROOT, *p.split("/")), p)
    old = sorted(f for f in os.listdir(folder) if f.startswith("backup-") and f.endswith(".zip"))
    for f in old[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(folder, f))
        except OSError:
            pass
    return name


def apply_files(files: dict, state: dict) -> tuple[list[str], list[str], list[str]]:
    """Copy the new files over the folder. Returns (written, removed, scripts_changed). Rolls everything back on an error."""
    changed = []
    for rel, data in files.items():
        if is_protected(rel):
            continue
        dest = os.path.join(ROOT, *rel.split("/"))
        if os.path.isdir(dest):
            say("..", f"{rel} is a folder on this PC (the update brings a file of that name); left alone")
            continue
        if os.path.isfile(dest) and sha256_bytes(data) == sha256_file(dest):
            continue
        changed.append(rel)
    shipped = state.get("files") or {}
    gone = [rel for rel in shipped if rel not in files and not is_protected(rel) and os.path.isfile(os.path.join(ROOT, *rel.split("/")))]
    backup = make_backup(changed + gone)
    if backup:
        say("..", f"the files that are replaced were saved in {os.path.relpath(backup, ROOT)}")
    saved = set(zipfile.ZipFile(backup).namelist()) if backup else set()
    done: list[str] = []
    try:
        for rel in changed:
            dest = os.path.join(ROOT, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            tmp = dest + ".upd-new"
            with open(tmp, "wb") as f:
                f.write(files[rel])
            os.replace(tmp, dest)
            done.append(rel)
        removed = []
        for rel in gone:
            os.remove(os.path.join(ROOT, *rel.split("/")))
            removed.append(rel)
    except Exception:
        say("!!", "copying failed half-way; putting the old files back")
        if backup:
            with zipfile.ZipFile(backup) as z:
                for rel in z.namelist():
                    dest = os.path.join(ROOT, *rel.split("/"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(z.read(rel))
        for rel in done:                                  # files that did not exist before: take them away again
            if rel not in saved:
                try:
                    os.remove(os.path.join(ROOT, *rel.split("/")))
                except OSError:
                    pass
        raise
    return changed, removed, [r for r in changed if r in SELF_SCRIPTS]


# ------------------------------------------------------------------ the two ways to update

def update_with_git(branch: str, check_only: bool, force: bool) -> tuple[str, int]:
    """('done'|'current'|'skip'|'error', exit code) - a git clone is updated by fast-forward only."""
    git = shutil.which("git")
    if not git:
        return "skip", 0

    def run(*args, timeout=120):
        return subprocess.run([git, "-C", ROOT, *args], capture_output=True, text=True, timeout=timeout)

    try:
        top = run("rev-parse", "--show-toplevel")
        if top.returncode != 0 or os.path.normcase(os.path.realpath(top.stdout.strip())) != os.path.normcase(os.path.realpath(ROOT)):
            return "skip", 0                              # not a clone of its own (a ZIP folder that happens to sit inside another repository)
        f = run("fetch", "--quiet", "origin", branch, timeout=180)
        if f.returncode != 0:
            say("..", "git could not reach GitHub (" + (f.stderr.strip().splitlines() or ["?"])[-1][:100] + "); continuing with the current version")
            return "error", 1
        head, new = run("rev-parse", "HEAD").stdout.strip(), run("rev-parse", "FETCH_HEAD").stdout.strip()
        if head == new:
            say("OK", f"InstAI v{local_version()} is up to date (git)")
            return "current", 0
        if run("merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD").returncode == 0:
            say("OK", f"InstAI v{local_version()}: this folder is ahead of GitHub's {branch}; nothing to update")
            return "current", 0
        remote_version = run("show", "FETCH_HEAD:VERSION").stdout.strip()
        if parse_version(remote_version) < parse_version(local_version()) and not force:
            say("..", f"GitHub has v{remote_version}, this folder v{local_version()}; not going back")
            return "current", 0
        if check_only:
            say("OK", f"an update is available: v{local_version()} -> v{remote_version}")
            return "done", 0
        if run("status", "--porcelain", "--untracked-files=no").stdout.strip():
            say("!!", "files of the program were changed in this folder; not updating by git (save or undo those changes first)")
            return "error", 1
        names = run("diff", "--name-only", "HEAD", "FETCH_HEAD").stdout.split()
        m = run("merge", "--ff-only", "--quiet", "FETCH_HEAD")
        if m.returncode != 0:
            say("!!", "git could not fast-forward (" + (m.stderr.strip().splitlines() or ["?"])[-1][:100] + "); continuing with the current version")
            return "error", 1
        say("OK", f"updated by git: v{remote_version} ({len(names)} files changed)")
        return "done", UPDATED_SCRIPTS if any(n in SELF_SCRIPTS for n in names) else 0
    except (OSError, subprocess.SubprocessError) as e:
        say("..", f"git update skipped ({type(e).__name__})")
        return "error", 1


def update_with_zip(repo: str, branch: str, args) -> int:
    state = load_state()
    sha = remote_commit(repo, branch)
    lv = local_version()
    if sha and state.get("commit") == sha and not args.force:
        say("OK", f"InstAI v{lv} is up to date (GitHub commit {sha[:7]})")
        return 0
    stage = os.path.join(data_dir(), "update")
    os.makedirs(stage, exist_ok=True)
    zpath = os.path.join(stage, "main.zip")
    say("..", "checking GitHub for a newer InstAI ...")
    if not download_zip(zip_urls(repo, branch), zpath):
        say("..", f"could not download the update (no internet or GitHub is blocked); continuing with v{lv}")
        return 1
    try:
        with zipfile.ZipFile(zpath) as z:
            commit = (z.comment or b"").decode("ascii", "ignore").strip()
            files = archive_files(z)
        version = check_archive(files)
    except (ValueError, zipfile.BadZipFile, KeyError) as e:
        say("!!", f"the downloaded update is not usable ({e}); continuing with v{lv}")
        return 1
    finally:
        try:
            os.remove(zpath)
        except OSError:
            pass
    commit = sha or (commit if len(commit) == 40 else "")
    if commit and state.get("commit") == commit and not args.force:
        say("OK", f"InstAI v{lv} is up to date (GitHub commit {commit[:7]})")
        return 0
    if parse_version(version) < parse_version(lv) and not args.force:
        say("..", f"GitHub has v{version}, this folder v{lv}; not going back (use --force to allow it)")
        save_state({**state, "commit": commit, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        return 0
    if args.check:
        say("OK", f"an update is available: v{lv} -> v{version}")
        return 0
    try:
        changed, removed, scripts = apply_files(files, state)
    except Exception as e:  # noqa: BLE001
        say("!!", f"the update could not be copied ({type(e).__name__}: {str(e)[:100]}); the old files are back; continuing with v{lv}")
        return 1
    shipped = {rel: sha256_bytes(data) for rel, data in files.items() if not is_protected(rel)}
    save_state({"repo": repo, "branch": branch, "commit": commit, "version": version, "from_version": lv, "files": shipped,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "changed": len(changed), "removed": len(removed)})
    say("OK", f"updated InstAI v{lv} -> v{version} ({len(changed)} files changed, {len(removed)} removed; your data, .env and models were not touched)")
    return UPDATED_SCRIPTS if scripts else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="InstAI self-update from GitHub")
    ap.add_argument("--check", action="store_true", help="only say whether an update is available")
    ap.add_argument("--force", action="store_true", help="re-apply and allow a lower version")
    ap.add_argument("--worker", action="store_true", help="PC B: do not look for a running server")
    args = ap.parse_args(argv)
    if setting("INSTAI_NO_UPDATE") in ("1", "true", "yes") or setting("INSTAI_AUTO_UPDATE") in ("0", "false", "no"):
        say("..", "automatic update is switched off (INSTAI_NO_UPDATE / INSTAI_AUTO_UPDATE)")
        return 0
    repo, branch = setting("INSTAI_UPDATE_REPO", DEFAULT_REPO), setting("INSTAI_UPDATE_BRANCH", DEFAULT_BRANCH)
    if not args.worker and not args.check and server_running():
        newer = remote_commit(repo, branch)
        news = bool(newer and newer != load_state().get("commit"))
        say("OK", f"InstAI v{local_version()} is already running; an update waits for the next STOP.bat + START.bat"
            + (" (GitHub has a newer InstAI: run STOP.bat, then START.bat to install it)" if news else ""))
        return 0
    try:
        mode, code = update_with_git(branch, args.check, args.force)
        if mode != "skip":
            return code
        return update_with_zip(repo, branch, args)
    except Exception as e:  # noqa: BLE001 - an update problem must never stop the program from starting
        say("..", f"update check failed ({type(e).__name__}: {str(e)[:100]}); continuing with v{local_version()}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
