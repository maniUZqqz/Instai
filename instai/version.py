"""The ONE place that knows the version: the `VERSION` file at the project root (a single line such as `0.6.0`).

Everything else reads it from here: the Django setting, `/api/version`, the badge in the corner of every screen, the title of the
.bat windows (they read the same file), the worker agent and the console banners. `CHANGELOG.json` holds the plain-language
"what is new" for every version (both languages); tests/test_platform_version.py keeps the two in step.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "InstAI"
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def read_version() -> str:
    try:
        v = (ROOT / "VERSION").read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return "0.0.0"
    return v if _SEMVER.match(v) else "0.0.0"


def git_commit() -> str:
    """Short commit of the checkout without running git (a GPU PC may not have it): .git/HEAD -> ref -> object name."""
    try:
        git = ROOT / ".git"
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(None, 1)[1].strip()
            p = git / ref
            if p.is_file():
                return p.read_text(encoding="utf-8").strip()[:7]
            packed = git / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split()[0][:7]
            return ""
        return head[:7]
    except OSError:
        return ""


def build_info() -> dict:
    """{"name", "version", "commit"}  - what the badge shows and the worker reports."""
    return {"name": NAME, "version": read_version(), "commit": git_commit()}


def changelog() -> list[dict]:
    """[{version, date, title: {fa, en}, items: [{fa, en}]}], newest first. A broken file gives an empty list, never an error."""
    try:
        data = json.loads((ROOT / "CHANGELOG.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and e.get("version")] if isinstance(data, list) else []


def tuple_of(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


VERSION = read_version()
