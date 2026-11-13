"""Self-update (version 0.8.0): START.bat / START-WORKER.bat bring the latest InstAI from GitHub's main. The owner's folder is a GitHub ZIP download (not a
git clone), so the ZIP route is the main one; a real clone is updated by fast-forward. Every problem ends with "continuing" (exit 1): an
update must never stop InstAI from starting. GitHub is replaced by a local HTTP server that serves a ZIP laid out like codeload's."""
from __future__ import annotations

import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SU = ROOT / "scripts" / "self_update.py"
sys.path.insert(0, str(ROOT / "scripts"))
import self_update as su  # noqa: E402

SHA_A = "a" * 40
SHA_B = "b" * 40


def make_zip(files: dict[str, str | bytes], top: str = "Instai-main", comment: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(f"{top}/{name}", data)
        z.comment = comment.encode()
    return buf.getvalue()


def release(version: str, **extra) -> dict[str, str]:
    base = {"VERSION": version + "\n", "manage.py": "# manage\n", "instai/__init__.py": "", "scripts/self_update.py": SU.read_text(encoding="utf-8"),
            "START.bat": f"@echo off\r\nrem start {version}\r\n", "README.md": f"readme {version}\n", "instai/core.py": f"V = '{version}'\n"}
    base.update(extra)
    return {k: v for k, v in base.items() if v is not None}


class Upstream:
    """A fake GitHub: serves /main.zip and the commit sha (like api.github.com/repos/<repo>/commits/main)."""

    def __init__(self):
        self.zip = b""
        self.sha = SHA_A
        self.hits: list[str] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hits.append(self.path)
                if self.path.endswith("/main.zip"):
                    body, ctype = outer.zip, "application/zip"
                elif "/commits/" in self.path:
                    body, ctype = outer.sha.encode(), "text/plain"
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def publish(self, files: dict, sha: str):
        self.zip, self.sha = make_zip(files), sha

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def up():
    u = Upstream()
    yield u
    u.close()


@pytest.fixture
def home(tmp_path, monkeypatch, up):
    """The owner's folder: a name with spaces, parentheses and Persian letters, an old release, and everything that is HIS."""
    h = tmp_path / "Instai-main (نسخه ۱)" / "V2 test"
    for rel, data in release("0.6.0").items():
        (h / rel).parent.mkdir(parents=True, exist_ok=True)
        (h / rel).write_text(data if isinstance(data, str) else "", encoding="utf-8", newline="")
    (h / "scripts" / "self_update.py").write_text(SU.read_text(encoding="utf-8"), encoding="utf-8")
    for rel, data in {".env": "INSTAI_PORT=8765\nSECRET=mine\n", "data/db.sqlite3": "my episodes", "data-worker/w.txt": "w", "models/big.bin": "weights",
                      ".venv/Scripts/python.exe": "py", ".venv2/x": "x", "tools/ffmpeg/ffmpeg.exe": "ff", "media/a.mp4": "video", "logs/old.log": "log"}.items():
        (h / rel).parent.mkdir(parents=True, exist_ok=True)
        (h / rel).write_text(data, encoding="utf-8")
    monkeypatch.setattr(su, "ROOT", str(h))
    monkeypatch.setenv("INSTAI_UPDATE_ZIP", up.url + "/main.zip")
    monkeypatch.setenv("INSTAI_UPDATE_API", up.url)
    monkeypatch.setenv("INSTAI_UPDATE_FAST", "1")
    monkeypatch.setenv("INSTAI_PORT", "1")                 # nothing listens: the server is "not running"
    for k in ("INSTAI_NO_UPDATE", "INSTAI_AUTO_UPDATE"):
        monkeypatch.delenv(k, raising=False)
    return h


MINE = {".env": "INSTAI_PORT=8765\nSECRET=mine\n", "data/db.sqlite3": "my episodes", "data-worker/w.txt": "w", "models/big.bin": "weights",
        ".venv/Scripts/python.exe": "py", ".venv2/x": "x", "tools/ffmpeg/ffmpeg.exe": "ff", "media/a.mp4": "video", "logs/old.log": "log"}


def mine_untouched(h: Path):
    for rel, data in MINE.items():
        assert (h / rel).read_text(encoding="utf-8") == data, f"{rel} is the owner's and must not change"


def log_text(h: Path) -> str:
    return (h / "data" / "logs" / "update.log").read_text(encoding="utf-8")


def test_a_newer_release_replaces_the_code_and_keeps_everything_that_is_his(home, up):
    up.publish(release("0.7.0", **{"docs/NEW.md": "new file", "instai/core.py": "V = 'new'\n", ".env": "SECRET=the-repo-must-never-write-this", "data/evil": "x",
                                   "models/evil.bin": "x"}), SHA_B)
    assert su.main([]) == 10, "START.bat changed: exit code 10 = start again from the top"
    assert (home / "VERSION").read_text().strip() == "0.7.0"
    assert (home / "instai" / "core.py").read_text() == "V = 'new'\n" and (home / "docs" / "NEW.md").read_text() == "new file"
    assert (home / "START.bat").read_bytes() == b"@echo off\r\nrem start 0.7.0\r\n"
    mine_untouched(home)
    assert not (home / "data" / "evil").exists() and not (home / "models" / "evil.bin").exists(), "protected folders are never written from the archive"
    st = json.loads((home / "data" / "update" / "state.json").read_text())
    assert st["commit"] == SHA_B and st["version"] == "0.7.0" and st["from_version"] == "0.6.0"
    backups = list((home / "data" / "update").glob("backup-*.zip"))
    assert len(backups) == 1 and "START.bat" in zipfile.ZipFile(backups[0]).namelist(), "the replaced files were saved first"
    assert "updated InstAI v0.6.0 -> v0.7.0" in log_text(home)
    assert not list(home.rglob("*.upd-new")) and not (home / "data" / "update" / "main.zip").exists(), "no temporary files are left"


def test_nothing_is_downloaded_twice_for_the_same_commit(home, up):
    up.publish(release("0.7.0"), SHA_B)
    assert su.main([]) == 10
    up.hits.clear()
    assert su.main([]) == 0, "same commit: up to date"
    assert not any(h.endswith("main.zip") for h in up.hits), "only the cheap commit check is made"
    assert "up to date" in log_text(home)


def test_scripts_unchanged_means_exit_zero_and_a_deleted_upstream_file_goes_away_after_a_backup(home, up):
    up.publish(release("0.7.0", **{"instai/old_module.py": "x = 1\n"}), SHA_A)
    (home / "START.bat").write_text("@echo off\r\nrem start 0.7.0\r\n", encoding="utf-8", newline="")
    assert su.main([]) == 0, "START.bat itself did not change: no restart"
    assert (home / "instai" / "old_module.py").exists()
    up.publish(release("0.7.1"), SHA_B)                                 # old_module.py is gone upstream
    (home / "my_own_script.py").write_text("keep me", encoding="utf-8")   # a file InstAI never shipped
    assert su.main([]) in (0, 10)
    assert not (home / "instai" / "old_module.py").exists(), "shipped earlier, gone upstream: removed"
    assert (home / "my_own_script.py").read_text() == "keep me", "a file InstAI never shipped is never deleted"
    assert any("instai/old_module.py" in zipfile.ZipFile(b).namelist() for b in (home / "data" / "update").glob("backup-*.zip")), "...but backed up first"


def test_no_downgrade_unless_forced(home, up):
    up.publish(release("0.5.0"), SHA_B)
    assert su.main([]) == 0
    assert (home / "VERSION").read_text().strip() == "0.6.0" and "not going back" in log_text(home)
    assert su.main(["--force"]) in (0, 10)
    assert (home / "VERSION").read_text().strip() == "0.5.0"


def test_a_broken_archive_is_refused_and_the_folder_is_untouched(home, up):
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    up.publish(release("0.7.0", **{"instai/core.py": "def broken(:\n"}), SHA_B)
    assert su.main([]) == 1
    assert "does not compile" in log_text(home)
    up.publish(release("0.7.0", **{"manage.py": None}), SHA_B)
    assert su.main([]) == 1 and "no manage.py" in log_text(home)
    up.zip = b"<html>rate limited</html>"
    assert su.main([]) == 1
    after = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file() and "logs" not in p.parts and "update" not in p.parts}
    assert {k: v for k, v in before.items() if "logs" not in k.parts} == after, "nothing changed"


def test_offline_or_blocked_github_never_stops_the_start(home, monkeypatch):
    monkeypatch.setenv("INSTAI_UPDATE_ZIP", "http://127.0.0.1:9/main.zip")
    monkeypatch.setenv("INSTAI_UPDATE_API", "http://127.0.0.1:9")
    assert su.main([]) == 1
    assert "continuing with v0.6.0" in log_text(home)
    assert (home / "VERSION").read_text().strip() == "0.6.0"


def test_a_running_server_is_not_updated_under_its_feet(home, up, monkeypatch):
    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    hs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=hs.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("INSTAI_PORT", str(hs.server_address[1]))
        up.publish(release("0.7.0"), SHA_B)
        assert su.main([]) == 0
        assert (home / "VERSION").read_text().strip() == "0.6.0" and "already running" in log_text(home)
        assert su.main(["--worker"]) == 10, "PC B (START-WORKER.bat) has no server of its own to look for"
    finally:
        hs.shutdown()


def test_switches_turn_the_update_off(home, up, monkeypatch):
    up.publish(release("0.7.0"), SHA_B)
    monkeypatch.setenv("INSTAI_NO_UPDATE", "1")
    assert su.main([]) == 0 and (home / "VERSION").read_text().strip() == "0.6.0"
    monkeypatch.delenv("INSTAI_NO_UPDATE")
    (home / ".env").write_text("INSTAI_AUTO_UPDATE=0\n", encoding="utf-8")
    assert su.main([]) == 0 and (home / "VERSION").read_text().strip() == "0.6.0"


def test_check_only_does_not_touch_anything(home, up):
    up.publish(release("0.7.0"), SHA_B)
    assert su.main(["--check"]) == 0
    assert "an update is available: v0.6.0 -> v0.7.0" in log_text(home) and (home / "VERSION").read_text().strip() == "0.6.0"


def test_copy_failing_half_way_puts_the_old_files_back(home, up, monkeypatch):
    up.publish(release("0.7.0", **{"instai/core.py": "V = 'new'\n", "docs/NEW.md": "new"}), SHA_B)
    real, calls = os.replace, {"n": 0}

    def flaky(src, dst, *a, **k):
        if str(dst).endswith((".py", ".md", ".bat", "VERSION")) and ".upd-new" in str(src):
            calls["n"] += 1
            if calls["n"] == 3:
                raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(su.os, "replace", flaky)
    assert su.main([]) == 1
    monkeypatch.setattr(su.os, "replace", real)
    assert (home / "VERSION").read_text().strip() == "0.6.0" and (home / "instai" / "core.py").read_text() == "V = '0.6.0'\n"
    assert not (home / "docs" / "NEW.md").exists() and "the old files are back" in log_text(home)
    mine_untouched(home)


def test_archive_paths_cannot_escape_the_folder():
    z = zipfile.ZipFile(io.BytesIO(make_zip({"ok.txt": "1", "../evil.txt": "2", "a/../../evil2.txt": "3", "C:/evil3.txt": "4"})))
    assert list(su.archive_files(z)) == ["ok.txt"]
    with pytest.raises(ValueError):
        su.archive_files(zipfile.ZipFile(io.BytesIO(_two_tops())))


def _two_tops() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("one/a", "1")
        z.writestr("two/b", "2")
    return buf.getvalue()


def test_the_command_line_entry_point_works_from_a_path_with_spaces_and_persian(home, up, tmp_path):
    up.publish(release("0.7.0"), SHA_B)
    env = {**os.environ, "INSTAI_PORT": "1", "PYTHONIOENCODING": "cp1252"}
    p = subprocess.run([sys.executable, str(home / "scripts" / "self_update.py")], capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert p.returncode == 10, p.stdout + p.stderr
    assert "updated InstAI v0.6.0 -> v0.7.0" in p.stdout and (home / "VERSION").read_text().strip() == "0.7.0"


@pytest.mark.skipif(not shutil.which("git"), reason="git is not installed")
def test_a_real_git_clone_is_updated_by_fast_forward_and_local_edits_stop_it(tmp_path, monkeypatch):
    def git(cwd, *a):
        return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", *a], cwd=str(cwd), capture_output=True, text=True, check=True)

    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    for rel, data in release("0.6.0").items():
        (origin / rel).parent.mkdir(parents=True, exist_ok=True)
        (origin / rel).write_text(data, encoding="utf-8", newline="")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "v0.6.0")
    clone = tmp_path / "my clone (فارسی)"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    for rel, data in release("0.7.0", **{"docs/NEW.md": "n"}).items():
        (origin / rel).parent.mkdir(parents=True, exist_ok=True)
        (origin / rel).write_text(data, encoding="utf-8", newline="")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "v0.7.0")
    monkeypatch.setattr(su, "ROOT", str(clone))
    monkeypatch.setenv("INSTAI_PORT", "1")
    (clone / "README.md").write_text("I edited this", encoding="utf-8")
    assert su.main([]) == 1 and "files of the program were changed" in log_text(clone), "local edits in tracked files are never overwritten"
    assert (clone / "VERSION").read_text().strip() == "0.6.0"
    git(clone, "checkout", "--", "README.md")
    assert su.main([]) == 10, "START.bat changed in the new commit"
    assert (clone / "VERSION").read_text().strip() == "0.7.0" and (clone / "docs" / "NEW.md").exists()
    assert su.main([]) == 0 and "up to date (git)" in log_text(clone)


def test_the_start_scripts_call_the_updater_before_anything_else_and_never_loop():
    for name, flag in (("START.bat", ""), ("START-WORKER.bat", " --worker")):
        text = (ROOT / name).read_text(encoding="utf-8")
        call = f'".venv\\Scripts\\python.exe" scripts\\self_update.py{flag} & if errorlevel 10 (goto) 2>nul & set "INSTAI_NO_UPDATE=1" & call "%~dp0{name}" & exit /b'
        assert call in text, f"{name}: the one-line restart trick is missing"
        assert text.index("self_update.py") < text.index("bootstrap.py"), "update first, then packages / UI / database"
        assert 'if "%INSTAI_NO_UPDATE%"=="1" goto after_update' in text, "the restarted copy must not update again (no loop)"
        assert all(ord(c) < 128 for c in text), "console text in .bat files is ASCII"
