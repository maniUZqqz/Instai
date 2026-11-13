"""Windows path handling (0.8.0): the folder of InstAI and its data folder may contain spaces, parentheses and Persian letters
(`C:\\Users\\QQz\\Desktop\\Instai-main (نسخهٔ ۲)\\data`). Everything that runs in another process (the start scripts' helpers, the downloader, the setup) is
started here from such a folder, and the media folder is written and read back."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ODD = "پوشهٔ آزمون (نسخهٔ ۲) with spaces"


@pytest.fixture
def odd_root(tmp_path):
    """A copy of the scripts and manifests in a folder with an awkward name: the scripts find their files relative to their own location."""
    base = tmp_path / ODD / "Instai-main"
    (base / "scripts").mkdir(parents=True)
    for name in ("setup_remotion.py", "download_models.py", "self_update.py", "wait_ready.py"):
        shutil.copy(ROOT / "scripts" / name, base / "scripts" / name)
    shutil.copytree(ROOT / "manifests", base / "manifests")
    shutil.copytree(ROOT / "instai", base / "instai", ignore=shutil.ignore_patterns("static", "__pycache__", "migrations"))
    (base / "VERSION").write_text("0.8.0\n", encoding="utf-8")
    (base / "remotion").mkdir()
    return base


def run(base: Path, *args: str, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "PYTHONIOENCODING": "utf-8", "INSTAI_DATA_DIR": str(base / "data"), "INSTAI_TOOLS_DIR": str(base / "tools"), "INSTAI_MODELS_DIR": str(base / "models"),
         "INSTAI_SCAN_DEFAULTS": "0", **env}
    return subprocess.run([sys.executable, *args], cwd=str(base.parent), env=e, capture_output=True, text=True, encoding="utf-8", timeout=120)


def test_the_downloader_lists_the_curated_library_from_an_awkward_folder(odd_root):
    p = run(odd_root, str(odd_root / "scripts" / "download_models.py"), "--status", "--detail")
    assert p.returncode == 0, p.stderr
    st = json.loads(p.stdout)
    assert {"flux-schnell", "flux-parts", "sdxl-base", "pulid-flux", "rife", "piper-fa-voices"} <= set(st)
    assert all(row["details"] for pid, row in st.items() if pid in ("rife", "flux-parts"))


def test_the_remotion_setup_check_runs_from_an_awkward_folder(odd_root):
    p = run(odd_root, str(odd_root / "scripts" / "setup_remotion.py"), "--check", INSTAI_NODE_EXE=str(odd_root / "nope.exe"))
    assert p.returncode in (0, 1) and json.loads(p.stdout)["ready"] in (True, False), p.stdout + p.stderr
    p = run(odd_root, str(odd_root / "scripts" / "setup_remotion.py"), "--background", INSTAI_REMOTION_AUTO="0")
    assert p.returncode == 0 and "switched off" in p.stdout
    assert (odd_root / "data" / "logs" / "remotion-setup.log").read_text(encoding="utf-8").count("switched off") == 1, "the log is written in the Persian-named data folder"


def test_the_update_check_runs_from_an_awkward_folder(odd_root):
    p = run(odd_root, str(odd_root / "scripts" / "self_update.py"), "--check", INSTAI_UPDATE_ZIP="http://127.0.0.1:9/x.zip", INSTAI_UPDATE_API="http://127.0.0.1:9", INSTAI_UPDATE_FAST="1")
    assert p.returncode == 1 and "continuing with v0.8.0" in p.stdout, p.stdout + p.stderr


def test_media_is_registered_and_served_from_a_data_folder_with_persian_letters(tmp_path):
    """A real Django process whose data folder has spaces and Persian letters registers a picture as an Asset and reads it back over HTTP."""
    base = tmp_path / ODD
    code = (
        "import os, sys, json\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "os.environ['DJANGO_SETTINGS_MODULE'] = 'instai.settings'\n"
        "import django; django.setup()\n"
        "from django.core.management import call_command; call_command('migrate', verbosity=0)\n"
        "from pathlib import Path\nfrom PIL import Image\n"
        "from instai.assets import storage\n"
        "src = Path(os.environ['INSTAI_DATA_DIR']) / 'تصویر آزمون.png'\n"
        "Image.new('RGB', (32, 20), (10, 120, 200)).save(src)\n"
        "a = storage.register(src, 'remotion/۱/نمونه (۱).png', kind='image', role='preview')\n"
        "from django.test import Client\n"
        "from urllib.parse import quote\n"
        "r = Client().get(quote(a.url))\n"
        "body = b''.join(r.streaming_content) if getattr(r, 'streaming', False) else r.content\n"
        "print(json.dumps({'path': a.path, 'size': a.size_bytes, 'w': a.width, 'status': r.status_code, 'bytes': len(body), 'exists': storage.storage.path_for(a.path).is_file()}))\n"
    )
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "INSTAI_DATA_DIR": str(base / "داده"), "INSTAI_TESTING": "1", "INSTAI_SECRET_KEY": "x" * 40}
    p = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["exists"] and out["size"] > 50 and out["w"] == 32 and out["path"] == "remotion/۱/نمونه (۱).png"
    assert out["status"] == 200 and out["bytes"] == out["size"], "the picture comes back over HTTP under its Persian, space-and-parenthesis name"
