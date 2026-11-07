"""0.6.0 version: ONE `VERSION` file, shown in the corner of every screen (studio and /lab), in every .bat / console window and reported by
the worker PC; a plain-language "what is new" in both languages for every version."""
from __future__ import annotations

import re
from pathlib import Path

from instai import version as ver

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src"
PERSIAN = re.compile(r"[؀-ۿ]")


def test_one_version_file_feeds_everything(api):
    v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", v) and ver.read_version() == v
    from django.conf import settings

    assert settings.VERSION == v
    j = api.get("/api/version").json()
    assert j["version"] == v and j["name"] == "InstAI" and "commit" in j
    assert api.get("/api/health").json()["version"] == v


def test_changelog_matches_the_version_and_has_both_languages():
    entries = ver.changelog()
    assert entries and entries[0]["version"] == ver.read_version(), "the newest entry is the current version"
    seen = set()
    for e in entries:
        assert re.fullmatch(r"\d+\.\d+\.\d+", e["version"]) and e["version"] not in seen and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"])
        seen.add(e["version"])
        assert e["title"]["fa"] and e["title"]["en"] and e["items"]
        assert PERSIAN.search(e["title"]["fa"]) and not PERSIAN.search(e["title"]["en"]), e["version"]
        for it in e["items"]:
            assert PERSIAN.search(it["fa"]) and it["en"] and not PERSIAN.search(it["en"]), (e["version"], it)
    versions = [ver.tuple_of(e["version"]) for e in entries]
    assert versions == sorted(versions, reverse=True), "newest first"


def test_changelog_endpoint_and_a_broken_file_gives_an_empty_list_not_an_error(api, monkeypatch, tmp_path):
    j = api.get("/api/version/changelog").json()
    assert j["current"] == ver.read_version() and j["entries"][0]["version"] == ver.read_version()
    bad = tmp_path / "CHANGELOG.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(ver, "ROOT", tmp_path)
    assert ver.changelog() == [] and ver.read_version() == "0.0.0", "a missing VERSION file must not crash the server"


def test_every_console_window_shows_the_version():
    for name in ("START.bat", "START-WORKER.bat", "Test-GPU.bat", "Download-Models.bat", "STOP.bat"):
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        assert "VERSION" in text and "IVER" in text, name
    for name in ("run-server.bat", "run-worker.bat"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8", errors="replace")
        assert "VERSION" in text and "IVER" in text, name
    # STOP.bat closes windows by title: the titles it looks for must still match the ones with a version in them
    stop = (ROOT / "STOP.bat").read_text(encoding="utf-8", errors="replace")
    assert 'WINDOWTITLE eq InstAI server*' in stop and 'WINDOWTITLE eq InstAI worker*' in stop
    assert "title InstAI server" in (ROOT / "scripts" / "run-server.bat").read_text(encoding="utf-8", errors="replace")
    assert "title InstAI worker" in (ROOT / "scripts" / "run-worker.bat").read_text(encoding="utf-8", errors="replace")


def test_bat_files_read_the_same_file_the_server_reads(tmp_path):
    """`set /p IVER=<VERSION` takes the first line: the file must be exactly one clean line."""
    raw = (ROOT / "VERSION").read_bytes()
    assert raw.strip() == raw.rstrip(b"\r\n") and b"\n" not in raw.rstrip(b"\r\n")


def test_the_badge_is_in_the_app_root_so_it_shows_on_every_screen():
    app = (SRC / "App.tsx").read_text(encoding="utf-8")
    assert "VersionBadge" in app and "<Routes>" in app
    assert app.index("<VersionBadge") > app.index("</Routes>"), "outside <Routes>: studio, /lab and not-found pages all get it"
    badge = (SRC / "components" / "VersionBadge.tsx").read_text(encoding="utf-8")
    assert "/api/version" in badge and "/whats-new" in badge and "data-testid" in badge
    assert "whats-new" in app, "the page the badge opens exists"
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert ".version-badge" in css


def test_the_built_ui_contains_the_badge_and_the_new_pages():
    """The committed build is what the GPU PC serves (no Node there): it must contain the new screens."""
    app = ROOT / "instai" / "static" / "app"
    js = "".join(p.read_text(encoding="utf-8", errors="replace") for p in (app / "assets").glob("*.js"))
    for marker in ("version-badge", "/api/version", "whats-new", "/queue", "/report", "/downloads"):
        assert marker in js, f"{marker} is missing from the built UI: run  python scripts/build_ui.py --force"
    h = (app / ".build-hash").read_text().strip()
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import build_ui

    assert build_ui.source_hash() == h, "the committed build is older than the sources"


def test_the_worker_agent_reports_its_version_and_logs_to_the_main_pc():
    text = (ROOT / "instai" / "remote" / "agent.py").read_text(encoding="utf-8")
    assert '"instai": read_version()' in text and "LogShipper" in text and '"stats": hardware.node_stats()' in text
