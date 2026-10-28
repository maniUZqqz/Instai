#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""InstAI downloader: ONE tool for every model/tool InstAI can use. Python 3.10+ standard library only
(it must run before the virtual environment exists). Console text is English on purpose (Windows console garbles Persian).

Design adapted from Qasem processing-server/download_models.py (manifest driven, resumable, verified, mirrors, reuse of files
ComfyUI already has, nothing is ever deleted: a file that fails verification is renamed, not removed).

    Download-Models.bat                    the default set (asks once)
    Download-Models.bat --list             what would be downloaded, with sizes and what is already here
    Download-Models.bat --check            test every link without downloading
    Download-Models.bat --only wan22       one package or item id (comma separated, repeatable)
    Download-Models.bat --skip piper       leave a package out
    Download-Models.bat --all              also optional packages
    Download-Models.bat --status           JSON: installed/missing per package (no network)
    Download-Models.bat --hf-mirror https://hf-mirror.com
Manifests: manifests\\*.json.  Log: data\\logs\\download-models.log.  Verification: a missing sha256 means "unverified" - the
computed hash is recorded in data\\downloads\\verified.json the first time (trust on first use) and checked afterwards.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("INSTAI_DATA_DIR") or os.path.join(ROOT, "data")
MODELS = os.environ.get("INSTAI_MODELS_DIR") or os.path.join(ROOT, "models")
TOOLS = os.environ.get("INSTAI_TOOLS_DIR") or os.path.join(ROOT, "tools")
MANIFESTS = os.path.join(ROOT, "manifests")
LOG_DIR = os.path.join(DATA, "logs")
VERIFIED = os.path.join(DATA, "downloads", "verified.json")
HF = "https://huggingface.co"
HF_MIRROR = "https://hf-mirror.com"
UA = "InstAI-downloader/1.0"
CHUNK = 1 << 20


def log(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "download-models.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def human(n) -> str:
    if n is None:
        return "?"
    n = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return ("%.0f %s" if u in ("B", "KB") else "%.2f %s") % (n, u)
        n /= 1024


# ------------------------------------------------------------------ manifests

def load_manifests() -> tuple[dict, list]:
    packages: dict[str, dict] = {}
    items: list[dict] = []
    for path in sorted(glob.glob(os.path.join(MANIFESTS, "*.json"))):
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        for pid, p in m.get("packages", {}).items():
            packages[pid] = p if isinstance(p, dict) else {"title": p}
            packages[pid].setdefault("group", m.get("group", ""))
        for it in m.get("items", []):
            it.setdefault("group", m.get("group", ""))
            items.append(it)
    return packages, items


def comfy_dir() -> str:
    d = os.environ.get("COMFYUI_DIR", "").strip()
    if d:
        return d
    try:  # the value saved from the Settings page lives in the database; read it without Django
        import sqlite3

        db = os.path.join(DATA, "db.sqlite3")
        if os.path.exists(db):
            row = sqlite3.connect(db).execute("select value from core_appsetting where key='comfyui_dir'").fetchone()
            if row and row[0]:
                return str(json.loads(row[0]))
    except Exception:  # noqa: BLE001
        pass
    return ""


def expand(s: str, hf: str) -> str:
    return (s.replace("{HF}", hf).replace("{MODELS}", MODELS).replace("{TOOLS}", TOOLS).replace("{HOME}", ROOT)
             .replace("{COMFYUI}", comfy_dir() or os.path.join(ROOT, "models", "comfyui")))


def dest_of(item: dict) -> str:
    return os.path.normpath(expand(item["dest"], HF))


def reuse_path(item: dict) -> str | None:
    """A file with the same name and size anywhere under ComfyUI's models folder counts as installed."""
    cd = comfy_dir()
    if not cd or "{COMFYUI}" not in item.get("dest", "") or item.get("kind", "file") != "file":
        return None
    name = os.path.basename(dest_of(item))
    for found in glob.glob(os.path.join(cd, "models", "**", name), recursive=True):
        if item.get("size") in (None, os.path.getsize(found)):
            return found
    return None


def load_verified() -> dict:
    try:
        with open(VERIFIED, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_verified(d: dict) -> None:
    os.makedirs(os.path.dirname(VERIFIED), exist_ok=True)
    with open(VERIFIED, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def is_installed(item: dict) -> tuple[bool, str]:
    kind = item.get("kind", "file")
    d = dest_of(item)
    if kind == "pypi_member":
        return os.path.isfile(d), d
    if kind == "zip":
        marker = os.path.join(d, item.get("marker", ""))
        return (os.path.isfile(marker), d) if item.get("marker") else (os.path.isdir(d) and bool(os.listdir(d)), d)
    if kind == "python":
        return (os.path.isfile(os.path.join(d, "python.exe")), d)
    if os.path.isfile(d):
        size = item.get("size")
        return (size is None or os.path.getsize(d) == size), d
    r = reuse_path(item)
    return (True, r) if r else (False, d)


# ------------------------------------------------------------------ transfer

def open_url(url: str, start: int = 0, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": f"bytes={start}-"} if start else {})})
    return urllib.request.urlopen(req, timeout=timeout)


def urls_for(item: dict, mirror: str | None) -> list[str]:
    urls = [expand(u, HF) for u in item.get("urls", [])]
    mirrors = [expand(u, mirror or HF_MIRROR) for u in item.get("urls", []) if "{HF}" in u]
    return urls + [m for m in mirrors if m not in urls]


def head(url: str) -> tuple[bool, int | None, str]:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            n = r.headers.get("Content-Length")
            return True, int(n) if n else None, str(r.status)
    except urllib.error.HTTPError as e:
        return (e.code in (301, 302, 307, 308, 405), None, f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        return False, None, type(e).__name__


def download_file(urls: list[str], dest: str, size: int | None, retries: int = 12) -> bool:
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if size and os.path.exists(part) and os.path.getsize(part) == size:  # finished earlier, only the rename was missing
        os.replace(part, dest)
        return True
    for url in urls:
        for attempt in range(1, retries + 1):
            start = os.path.getsize(part) if os.path.exists(part) else 0
            try:
                with open_url(url, start) as r:
                    code = getattr(r, "status", 200)
                    if start and code != 206:  # server ignored Range: start over
                        start = 0
                    total = size or (int(r.headers.get("Content-Length", 0)) + start) or None
                    t0, last, done = time.time(), 0.0, start
                    with open(part, "ab" if start else "wb") as f:
                        while True:
                            buf = r.read(CHUNK)
                            if not buf:
                                break
                            f.write(buf)
                            done += len(buf)
                            if time.time() - last > 5:
                                last = time.time()
                                sp = (done - start) / max(0.1, time.time() - t0)
                                pct = " %5.1f%%" % (100.0 * done / total) if total else ""
                                log("  %s%s  %s/s" % (human(done), pct, human(sp)))
                if size and os.path.getsize(part) != size:
                    raise OSError("size mismatch %d != %d" % (os.path.getsize(part), size))
                os.replace(part, dest)
                return True
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code == 416 and os.path.exists(part):  # bad range: start over
                    os.remove(part)
                    continue
                if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404):
                    log("  %s -> HTTP %d (skipping this link)" % (url.split("//")[-1][:60], e.code))
                    break
                wait = min(30, 2 ** min(attempt, 5))
                log("  attempt %d/%d failed (%s); retry in %ds" % (attempt, retries, type(e).__name__, wait))
                time.sleep(wait)
    return False


def verify(item: dict, path: str) -> bool:
    want = (item.get("sha256") or "").lower()
    got = sha256_of(path)
    if want:
        if got != want:
            os.replace(path, path + ".bad-" + time.strftime("%Y%m%d%H%M%S"))
            log("  sha256 mismatch - file moved aside (%s...)" % got[:12])
            return False
        return True
    ver = load_verified()
    prev = ver.get(item["id"])
    if prev and prev != got:
        log("  WARNING: sha256 differs from the one recorded on the first download (%s...)" % prev[:12])
        return False
    ver[item["id"]] = got
    save_verified(ver)
    log("  unverified in manifest; recorded sha256 %s... (trust on first use)" % got[:12])
    return True


def install_pypi_member(item: dict, dest: str) -> bool:
    """Take one file out of a wheel on PyPI (PyPI is far more reachable from Iran than GitHub release assets).
    The wheel's sha256 comes from PyPI's own JSON API, so the download is verified without a hash in the manifest."""
    spec = item["pypi"]
    try:
        with urllib.request.urlopen(urllib.request.Request("https://pypi.org/pypi/%s/%s/json" % (spec["name"], spec["version"]),
                                                           headers={"User-Agent": UA}), timeout=60) as r:
            info = json.load(r)
    except Exception as e:  # noqa: BLE001
        log("  PyPI metadata not reachable (%s)" % type(e).__name__)
        return False
    files = [u for u in info["urls"] if spec["wheel_contains"] in u["filename"]]
    if not files:
        log("  no matching wheel on PyPI")
        return False
    wheel = files[0]
    cache = os.path.join(DATA, "downloads", "cache")
    arch = os.path.join(cache, wheel["filename"])
    if not (os.path.isfile(arch) and os.path.getsize(arch) == wheel["size"]):
        if not download_file([wheel["url"]], arch, wheel["size"]):
            return False
    if sha256_of(arch) != wheel["digests"]["sha256"]:
        os.replace(arch, arch + ".bad-" + time.strftime("%Y%m%d%H%M%S"))
        log("  wheel sha256 mismatch - moved aside")
        return False
    with zipfile.ZipFile(arch) as z:
        member = next((m for m in z.namelist() if m.endswith(spec["member_suffix"])), None)
        if not member:
            log("  file not found inside the wheel")
            return False
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with z.open(member) as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(tmp, dest)
    try:
        os.remove(arch)
    except OSError:
        pass
    return True


def install(item: dict, mirror: str | None) -> bool:
    kind = item.get("kind", "file")
    dest = dest_of(item)
    if kind == "pypi_member":
        return install_pypi_member(item, dest)
    urls = urls_for(item, mirror)
    if kind == "file":
        if not download_file(urls, dest, item.get("size")):
            return False
        return verify(item, dest)
    cache = os.path.join(DATA, "downloads", "cache")
    arch = os.path.join(cache, os.path.basename(urls[0].split("?")[0]))
    if not (os.path.isfile(arch) and (not item.get("size") or os.path.getsize(arch) == item["size"])):
        if not download_file(urls, arch, item.get("size")):
            return False
    if not verify(item, arch):
        return False
    if kind == "python":
        import subprocess

        log("  installing Python per-user into %s" % dest)
        rc = subprocess.call([arch, "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0",
                              "Include_doc=0", "Shortcuts=0", "TargetDir=" + dest])
        return rc == 0
    if kind == "zip":
        pick = item.get("pick")  # {"inner/path.exe": "outname.exe"}; keeps the disk footprint small
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(arch) as z:
            if pick:
                for member in z.namelist():
                    for suffix, out in pick.items():
                        if member.endswith(suffix) and not member.endswith("/"):
                            with z.open(member) as src, open(os.path.join(dest, out), "wb") as dst:
                                shutil.copyfileobj(src, dst)
            else:
                z.extractall(dest)
        if not item.get("keep_archive"):
            try:
                os.remove(arch)
            except OSError:
                pass
        return is_installed(item)[0]
    log("  unknown kind %s" % kind)
    return False


# ------------------------------------------------------------------ main

def select(packages: dict, items: list, args) -> list[dict]:
    only = {x.strip() for v in (args.only or []) for x in v.split(",") if x.strip()}
    skip = {x.strip() for v in (args.skip or []) for x in v.split(",") if x.strip()}
    chosen = []
    for it in items:
        pkg = it.get("package", "")
        if it.get("fallback_for"):
            continue  # only tried when the primary item failed (see fallbacks_for)
        if only:
            if not (pkg in only or it["id"] in only or it.get("group") in only):
                continue
        else:
            if not packages.get(pkg, {}).get("default", False) and not args.all:
                continue
            if it.get("optional") and not args.all:
                continue
        if pkg in skip or it["id"] in skip:
            continue
        chosen.append(it)
    return chosen


def fallbacks_for(items: list, failed: list[str], skip_ids: set) -> list[dict]:
    return [i for i in items if i.get("fallback_for") in failed and i["id"] not in skip_ids]


def status_json(packages: dict, items: list) -> dict:
    out: dict = {}
    for pid, p in packages.items():
        its = [i for i in items if i.get("package") == pid]
        have = [i for i in its if is_installed(i)[0]]
        out[pid] = {"title": p.get("title", pid), "default": bool(p.get("default")), "licence": p.get("licence", ""),
                    "licence_verified": bool(p.get("licence_verified")), "size": sum(i.get("size") or 0 for i in its),
                    "items": len(its), "installed": len(have), "complete": bool(its) and len(have) == len(its),
                    "note": p.get("note", "")}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="InstAI model downloader")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--only", action="append")
    ap.add_argument("--skip", action="append")
    ap.add_argument("--hf-mirror", default=os.environ.get("HF_ENDPOINT"))
    args = ap.parse_args(argv)
    packages, items = load_manifests()
    if args.status:
        print(json.dumps(status_json(packages, items)))
        return 0
    chosen = select(packages, items, args)
    todo = []
    total = 0
    for it in chosen:
        ok, where = is_installed(it)
        if ok:
            log("[have] %-44s %s" % (it["id"], where if where != dest_of(it) else ""))
        else:
            todo.append(it)
            total += it.get("size") or 0
            log("[need] %-44s %s" % (it["id"], human(it.get("size"))))
    log("%d item(s) missing, about %s" % (len(todo), human(total)))
    if args.list:
        return 0
    if args.check:
        bad = 0
        for it in todo:
            for u in urls_for(it, args.hf_mirror)[:1]:
                ok, n, info = head(u)
                log("  %s %-40s %s %s" % ("OK " if ok else "BAD", it["id"], human(n), info))
                bad += 0 if ok else 1
        return 1 if bad else 0
    if not todo:
        log("Nothing to download.")
        return 0
    free = shutil.disk_usage(os.path.dirname(MODELS) if os.path.isdir(os.path.dirname(MODELS)) else ROOT).free
    if total and free < total + 2 * 1024 ** 3:
        log("Not enough free disk space: need %s + 2 GB safety, have %s." % (human(total), human(free)))
        return 2
    if not args.yes and sys.stdin.isatty():
        if input("Download %s now? [Y/n] " % human(total)).strip().lower() in ("n", "no"):
            return 1
    failed = []
    for it in todo:
        log("== %s" % it["id"])
        try:
            if not install(it, args.hf_mirror):
                failed.append(it["id"])
        except Exception as e:  # noqa: BLE001
            log("  error: %s: %s" % (type(e).__name__, e))
            failed.append(it["id"])
    for it in fallbacks_for(items, failed, set()):
        log("== %s (fallback)" % it["id"])
        try:
            if install(it, args.hf_mirror):
                failed = [f for f in failed if f != it["fallback_for"]]
        except Exception as e:  # noqa: BLE001
            log("  error: %s: %s" % (type(e).__name__, e))
    log("Done." if not failed else "Failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
