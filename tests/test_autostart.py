"""Start at Windows logon (0.12.0): START.bat puts a shortcut in the owner's Startup folder by itself (no administrator), there is an off switch,
START.bat updates itself from GitHub first (it already did), and the updater can no longer be broken by a `node_modules` symlink in the repository.
Windows is replaced by a fake Startup folder and a fake PowerShell that creates the .lnk file."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import autostart as au  # noqa: E402
import self_update as su  # noqa: E402


class Home:
    """A pretend InstAI folder and a pretend Windows user."""

    def __init__(self, tmp: Path):
        self.root = tmp / "Instai folder (v2)"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / "scripts" / "START-AUTO.bat").write_text("@echo off\r\n", encoding="utf-8")
        self.appdata = tmp / "AppData"
        self.env = {"APPDATA": str(self.appdata)}
        self.ps_calls: list[list[str]] = []
        self.ps_works = True

    @property
    def folder(self) -> Path:
        return self.appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    def run(self, cmd, **kw):
        """Fake PowerShell: creates the shortcut file named in the script."""
        self.ps_calls.append(cmd)
        if self.ps_works:
            m = re.search(r"CreateShortcut\('((?:[^']|'')*)'\)", cmd[-1])
            Path(m.group(1).replace("''", "'")).write_text("lnk", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    def ensure(self, **kw):
        return au.ensure(str(self.root), env=self.env, run=self.run, plat_windows=True, **kw)


@pytest.fixture
def home(tmp_path):
    return Home(tmp_path)


def test_the_first_start_registers_a_minimized_shortcut_in_the_users_startup_folder(home):
    res = home.ensure()
    assert res["state"] == "registered"
    assert Path(res["path"]) == home.folder / "InstAI.lnk" and Path(res["path"]).is_file()
    script = home.ps_calls[0][-1]
    assert "WindowStyle=7" in script and "START-AUTO.bat" in script and "WorkingDirectory" in script
    assert "powershell" in home.ps_calls[0][0].lower() and "-ExecutionPolicy" in home.ps_calls[0]


def test_it_is_idempotent_and_a_moved_folder_gets_its_shortcut_rewritten(home):
    assert home.ensure()["state"] == "registered"
    assert home.ensure()["state"] == "unchanged" and len(home.ps_calls) == 1
    rec = home.root / "data" / "autostart.json"                                   # the folder was moved: the record still names the old place
    data = json.loads(rec.read_text(encoding="utf-8"))
    data["target"] = r"C:\old place\scripts\START-AUTO.bat"
    rec.write_text(json.dumps(data), encoding="utf-8")
    assert home.ensure()["state"] == "registered" and len(home.ps_calls) == 2
    assert str(home.root) in home.ps_calls[1][-1]


def test_no_autostart_when_the_launcher_is_missing_and_never_an_error(home):
    (home.root / "scripts" / "START-AUTO.bat").unlink()
    assert home.ensure()["state"] == "failed"


def test_the_off_switches_remove_the_shortcut_and_are_obeyed(home, monkeypatch):
    home.ensure()
    # 1. Autostart-Off.bat (the marker)
    assert home.ensure(enabled=False)["state"] == "removed"
    assert (home.root / "data" / "autostart.off").is_file() and not list(home.folder.glob("InstAI.*"))
    assert home.ensure()["state"] == "disabled" and not list(home.folder.glob("InstAI.*")), "START.bat must not bring it back by itself"
    # 2. Autostart-On.bat beats the marker
    assert home.ensure(force=True)["state"] == "registered" and not (home.root / "data" / "autostart.off").exists()
    # 3. the environment variable and .env
    home.env["INSTAI_AUTOSTART"] = "0"
    assert home.ensure()["state"] == "removed"
    home.env.pop("INSTAI_AUTOSTART")
    assert home.ensure()["state"] == "registered"
    (home.root / ".env").write_text("INSTAI_PORT=8765\nINSTAI_AUTOSTART=off\n", encoding="utf-8")
    assert home.ensure()["state"] == "removed"
    (home.root / ".env").write_text("INSTAI_AUTOSTART=1\n", encoding="utf-8")
    assert home.ensure()["state"] == "registered"


def test_a_powershell_that_cannot_make_the_shortcut_falls_back_to_a_small_cmd_file(home):
    home.ps_works = False
    res = home.ensure()
    assert res["state"] == "registered" and res["path"].endswith("InstAI.cmd")
    text = Path(res["path"]).read_bytes().decode("utf-8")
    assert "start \"InstAI\" /min" in text and "START-AUTO.bat" in text and "\r\n" in text


def test_nothing_is_done_on_a_system_that_is_not_windows(home):
    assert au.ensure(str(home.root), env=home.env, plat_windows=False)["state"] == "unsupported"
    assert au.ensure(str(home.root), env={}, plat_windows=True)["state"] == "unsupported"      # no APPDATA
    assert not home.folder.exists()


def test_the_command_line_entry_never_stops_start_bat(home, monkeypatch, capsys):
    monkeypatch.setattr(au, "ROOT", str(home.root))
    monkeypatch.setattr(au, "startup_folder", lambda env=None: str(home.folder))
    monkeypatch.setattr(au, "is_windows", lambda: True)
    monkeypatch.setattr(au, "make_lnk", lambda lnk, target, workdir, run=None: (Path(lnk).write_text("x"), True)[1])
    (home.root / "scripts" / "START-AUTO.bat").unlink()
    assert au.main(["--ensure"]) == 0                                           # failed state: still exit code 0
    (home.root / "scripts" / "START-AUTO.bat").write_text("@echo off\r\n", encoding="utf-8")
    assert au.main(["--ensure"]) == 0 and "will start by itself" in capsys.readouterr().out
    assert au.main(["--off"]) == 0 and "no longer start by itself" in capsys.readouterr().out
    assert au.main(["--status"]) == 0 and "switched off" in capsys.readouterr().out
    assert au.main(["--on"]) == 0 and "will start by itself" in capsys.readouterr().out
    assert au.main(["--status"]) == 0 and "starts when you log in" in capsys.readouterr().out


def test_the_batch_files_are_wired_the_way_the_docs_say():
    start = (ROOT / "START.bat").read_bytes().decode("utf-8")
    assert "\r\n" in start and "scripts\\autostart.py --ensure" in start
    assert start.index("scripts\\self_update.py") < start.index("scripts\\autostart.py") < start.index("wait_ready.py --once"), \
        "the shortcut is made after the self-update step (START.bat may be replaced there) and before the server is started"
    auto = (ROOT / "scripts" / "START-AUTO.bat").read_bytes().decode("utf-8")
    assert "\r\n" in auto and 'set "INSTAI_NO_BROWSER=1"' in auto and 'set "INSTAI_NO_PAUSE=1"' in auto and 'call "%~dp0..\\START.bat"' in auto
    for name, flag in (("Autostart-Off.bat", "--off"), ("Autostart-On.bat", "--on")):
        text = (ROOT / name).read_bytes().decode("utf-8")
        assert "\r\n" in text and "scripts\\autostart.py " + flag in text and ".venv\\Scripts\\python.exe" in text
        assert all(ord(c) < 128 for c in text), "console text of a .bat is ASCII"
    assert "INSTAI_AUTOSTART=0" in start                                         # documented in the header of START.bat


def test_start_bat_still_updates_itself_from_github_before_anything_else():
    start = (ROOT / "START.bat").read_text(encoding="utf-8")
    line = next(ln for ln in start.splitlines() if "self_update.py" in ln and "errorlevel 10" in ln)
    assert 'call "%~dp0START.bat" & exit /b' in line, "the one-line re-run trick must stay on ONE line"
    assert "INSTAI_NO_UPDATE" in start


# ------------------------------------------------------------------ the updater keeps working for the owner's folder

def test_node_modules_at_any_depth_is_never_touched_by_the_updater():
    assert su.is_protected("frontend/node_modules")
    assert su.is_protected("frontend/node_modules/react/index.js")
    assert su.is_protected("node_modules/x")
    assert su.is_protected(".venv/Scripts/python.exe") and su.is_protected("data/db.sqlite3")
    assert not su.is_protected("frontend/src/App.tsx") and not su.is_protected("instai/api.py")


def test_a_folder_where_the_update_has_a_file_never_fails_the_update(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "ROOT", str(tmp_path))
    monkeypatch.setattr(su, "data_dir", lambda: str(tmp_path / "data"))
    (tmp_path / "frontend" / "dist").mkdir(parents=True)
    (tmp_path / "frontend" / "dist" / "keep.txt").write_text("mine")
    (tmp_path / "VERSION").write_text("0.1.0\n")
    files = {"frontend/dist": b"a file of the same name", "VERSION": b"0.2.0\n", "new.txt": b"hello"}
    changed, removed, scripts = su.apply_files(files, {})
    assert sorted(changed) == ["VERSION", "new.txt"] and (tmp_path / "frontend" / "dist" / "keep.txt").read_text() == "mine"
    assert (tmp_path / "VERSION").read_text() == "0.2.0\n"


def test_the_repository_holds_no_symlink_and_ignores_node_modules_in_every_form():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s"], capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    links = [ln for ln in out.stdout.splitlines() if ln.startswith("120000")]
    assert links == [], "a symlink in the repository breaks the ZIP update of every owner's folder: %s" % links
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "node_modules" in ignore and "/frontend/node_modules" in ignore
