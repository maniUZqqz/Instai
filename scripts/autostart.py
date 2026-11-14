#!/usr/bin/env python3
"""InstAI starts by itself when the owner logs in to Windows (0.12.0). Standard library only; English console text (the Windows console garbles Persian).

START.bat runs `autostart.py --ensure` on every start: the first time it puts a shortcut to `scripts\\START-AUTO.bat` in the CURRENT USER's Startup
folder (%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup) - minimized, no administrator rights, nothing system-wide. START-AUTO.bat is
START.bat without the browser window and without the "press a key" pause. At logon START.bat then does what it always does: updates itself from
GitHub (never blocks: offline = "continuing"), repairs the environment, starts the server and the worker.

  * idempotent: nothing happens when the shortcut already points at THIS folder; a moved folder gets its shortcut rewritten;
  * the OFF switch (any one of them): double-click Autostart-Off.bat (writes data\\autostart.off and removes the shortcut), or INSTAI_AUTOSTART=0
    (environment or .env). Deleting the shortcut by hand is NOT a switch: the next START.bat writes it again;
  * Autostart-On.bat is the way back (it beats the off marker);
  * a PowerShell-made .lnk is used (WindowStyle 7 = minimized); if PowerShell cannot do it a small .cmd with `start /min` is written instead;
  * nothing happens on a system that is not Windows (the tests pass a fake Startup folder).

The NMarketing node agent does the same for its own START.bat (processing/autostart.py); the two shortcuts are independent and the two programs
share the PC as described in docs/COEXISTENCE.md."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "InstAI"
LAUNCHER = os.path.join("scripts", "START-AUTO.bat")
OFF_WORDS = ("0", "off", "false", "no")


def say(tag: str, msg: str) -> None:
    print(f"  [{tag}] {msg}", flush=True)


def is_windows() -> bool:
    return sys.platform.startswith("win")


def data_dir(root: str = ROOT) -> str:
    return os.path.join(root, "data")


def startup_folder(env: dict | None = None) -> str:
    env = os.environ if env is None else env
    base = env.get("APPDATA") or ""
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs", "Startup") if base else ""


def read_env_file(root: str = ROOT) -> dict:
    out: dict = {}
    try:
        with open(os.path.join(root, ".env"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def disabled(root: str = ROOT, env: dict | None = None) -> str:
    """Why the owner switched it off ('' when he did not)."""
    env = os.environ if env is None else env
    if str(env.get("INSTAI_AUTOSTART", "")).strip().lower() in OFF_WORDS:
        return "INSTAI_AUTOSTART=0"
    if str(read_env_file(root).get("INSTAI_AUTOSTART", "")).strip().lower() in OFF_WORDS:
        return "INSTAI_AUTOSTART=0 in .env"
    if os.path.isfile(os.path.join(data_dir(root), "autostart.off")):
        return "data\\autostart.off (Autostart-Off.bat)"
    return ""


def _record_path(root: str) -> str:
    return os.path.join(data_dir(root), "autostart.json")


def _read_record(root: str) -> dict:
    try:
        with open(_record_path(root), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def make_lnk(lnk: str, target: str, workdir: str, run=None) -> bool:
    """Create the shortcut with PowerShell / WScript.Shell; True when the file exists afterwards."""
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);$s.TargetPath=%s;$s.WorkingDirectory=%s;"
          "$s.WindowStyle=7;$s.Description='InstAI (starts when you log in to Windows)';$s.Save()") % (_ps_quote(lnk), _ps_quote(target), _ps_quote(workdir))
    try:
        (run or subprocess.run)(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.isfile(lnk)


def make_cmd(path: str, target: str, workdir: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
            fh.write('@echo off\ncd /d "%s"\nstart "InstAI" /min "%s"\n' % (workdir, target))
        return True
    except OSError:
        return False


def status(root: str = ROOT, env: dict | None = None) -> dict:
    folder = startup_folder(env)
    rec = _read_record(root)
    path = rec.get("path") or ""
    return {"supported": is_windows() or bool(folder) and os.path.isdir(folder), "folder": folder, "path": path,
            "registered": bool(path and os.path.isfile(path) and rec.get("target") == os.path.join(root, LAUNCHER)), "disabled": disabled(root, env)}


def _remove_entries(root: str, folder: str) -> bool:
    removed = False
    old = _read_record(root).get("path") or ""
    for p in {old, os.path.join(folder, NAME + ".lnk"), os.path.join(folder, NAME + ".cmd")}:
        if p and os.path.isfile(p):
            try:
                os.remove(p)
                removed = True
            except OSError:
                pass
    try:
        if os.path.isfile(_record_path(root)):
            os.remove(_record_path(root))
    except OSError:
        pass
    return removed


def ensure(root: str = ROOT, enabled: bool = True, env: dict | None = None, run=None, plat_windows: bool | None = None, force: bool = False) -> dict:
    """Make the Startup entry match `enabled`. `force` = the owner said «on» explicitly (Autostart-On.bat): it beats the off marker.
    Returns {"state": registered | removed | unchanged | disabled | unsupported | failed, ...}."""
    win = is_windows() if plat_windows is None else plat_windows
    folder = startup_folder(env)
    if not win or not folder:
        return {"state": "unsupported", "detail": "autostart is for Windows (no Startup folder)"}
    data = data_dir(root)
    off_marker = os.path.join(data, "autostart.off")
    if enabled and force:
        try:
            os.remove(off_marker)
        except OSError:
            pass
    reason = disabled(root, env)
    if not enabled or reason:
        removed = _remove_entries(root, folder)
        if not enabled and not reason:
            try:
                os.makedirs(data, exist_ok=True)
                with open(off_marker, "w", encoding="utf-8") as fh:
                    fh.write("switched off with Autostart-Off.bat\n")
            except OSError:
                pass
        return {"state": "removed" if removed else "disabled", "detail": reason or "switched off"}
    target = os.path.join(root, LAUNCHER)
    if not os.path.isfile(target):
        return {"state": "failed", "detail": "%s was not found (the folder is incomplete; START.bat updates it)" % LAUNCHER}
    rec = _read_record(root)
    old = rec.get("path") or ""
    if old and os.path.isfile(old) and rec.get("target") == target:
        return {"state": "unchanged", "path": old}
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        pass
    lnk = os.path.join(folder, NAME + ".lnk")
    path = lnk if make_lnk(lnk, target, root, run) else ""
    if not path:
        cmd = os.path.join(folder, NAME + ".cmd")
        path = cmd if make_cmd(cmd, target, root) else ""
    if not path:
        return {"state": "failed", "detail": "could not write into %s" % folder}
    try:
        os.makedirs(data, exist_ok=True)
        with open(_record_path(root), "w", encoding="utf-8") as fh:
            json.dump({"path": path, "target": target, "kind": os.path.splitext(path)[1][1:]}, fh)
    except OSError:
        pass
    return {"state": "registered", "path": path}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="InstAI: start by itself when you log in to Windows")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ensure", action="store_true", help="register the shortcut unless it is switched off (what START.bat does)")
    g.add_argument("--on", action="store_true", help="switch it on (beats the off marker)")
    g.add_argument("--off", action="store_true", help="switch it off and remove the shortcut")
    g.add_argument("--status", action="store_true", help="print the state")
    args = ap.parse_args(argv)
    if args.status:
        st = status(ROOT)
        say("OK" if st["registered"] else "..", "starts when you log in to Windows" if st["registered"] else
            ("switched off: " + st["disabled"]) if st["disabled"] else "not registered yet" if st["supported"] else "not supported on this system")
        return 0
    res = ensure(ROOT, enabled=not args.off, force=args.on)
    state = res["state"]
    if state == "registered":
        say("OK", "InstAI will start by itself when you log in to Windows (Autostart-Off.bat switches it off)")
    elif state == "removed":
        say("OK", "InstAI will no longer start by itself when you log in (Autostart-On.bat brings it back)")
    elif state == "disabled":
        say("..", "start at logon is switched off (%s); Autostart-On.bat switches it on" % res.get("detail"))
    elif state == "failed":
        say("..", "start at logon could not be set up: %s" % res.get("detail"))
    return 0                                                    # never stops START.bat


if __name__ == "__main__":
    sys.exit(main())
