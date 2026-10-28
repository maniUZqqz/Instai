"""Tiny .env reader/writer (no python-dotenv). Secrets live only in <project>/.env, which git ignores."""
from __future__ import annotations

import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def read_env(path: Path = ENV_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if m:
            v = m.group(2)
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def load_env(path: Path = ENV_PATH) -> None:
    """Real environment variables win over the file."""
    for k, v in read_env(path).items():
        os.environ.setdefault(k, v)


def write_env_value(key: str, value: str, path: Path = ENV_PATH) -> None:
    """Set one key in .env (keeps comments and other keys) and in the running process."""
    if "\n" in value or "\r" in value:
        raise ValueError("value must be a single line")
    lines = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        pass
    new_line = f"{key}={value}"
    for i, line in enumerate(lines):
        m = _LINE.match(line)
        if m and m.group(1) == key and not line.lstrip().startswith("#"):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value
