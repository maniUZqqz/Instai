"""Audit batch "ia_core", second pass (2026-11-15): the pages a browser sweep found with English or Latin digits after 0.15.0, at desktop and phone width, in Persian.

* /lab/compare (the model notes and licences, no command line, a link to the Downloads page) and /lab/automation (why automatic posting is off);
* the home page, the workspace, the series and the episode pages: the titles the program writes carry Persian digits;
* the history tab of a page and the events tab of an episode: the reasons are Persian sentences, not English words;
* the episode's production tab: the quality check's numbers are Persian.
Run:  python -m pytest tests_ui/test_core_pages2.py -q   (see tests_ui/conftest.py)."""
from __future__ import annotations

import pytest

from tests_ui.test_core_pages import JS_TEXT, violations
from tests_ui.test_qa_sweep import routes, visit

SIZES = ["desktop", "phone"]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("path", ["/lab/compare", "/lab/automation"])
def test_lab_pages_are_plain_persian(browser, server, seeded, path, size):
    ctx, page, _ = visit(browser, server, path, size, "fa")
    try:
        page.wait_for_timeout(1200)
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], f"{path} ({size}): " + "\n".join(bad[:20])
        if path == "/lab/compare":
            assert "Download-Models" not in page.inner_text("main")
            assert page.get_by_role("link", name="باز کردنِ دانلودها").count() >= 1       # a link to the page that installs, not a command
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("name", ["/", "workspace", "workspace/episodes", "series", "explainer-series"])
def test_the_pages_that_list_episodes_have_persian_digits(browser, server, seeded, name, size):
    path = routes(seeded)[name]
    ctx, page, _ = visit(browser, server, path, size, "fa", wait="domcontentloaded")
    try:
        page.wait_for_timeout(2500)
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], f"{name} ({size}): " + "\n".join(bad[:20])
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_the_history_tab_gives_the_reasons_in_persian(browser, server, seeded, size):
    path = routes(seeded)["workspace/history"]
    ctx, page, _ = visit(browser, server, path, size, "fa", wait="domcontentloaded")
    try:
        page.wait_for_timeout(2500)
        text = page.inner_text("main")
        assert "script ready" not in text and "assets ready" not in text and "series plan" not in text, text[:400]
        assert "فیلم‌نامه آماده شد" in text or "طرحِ سری" in text, text[:400]
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], "\n".join(bad[:20])
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_the_episode_events_and_production_tabs_are_plain_persian(browser, server, seeded, size):
    path = routes(seeded)["episode"]
    ctx, page, _ = visit(browser, server, path, size, "fa", wait="domcontentloaded")
    try:
        page.wait_for_timeout(2500)
        page.get_by_role("tab", name="رویدادها").click()
        page.wait_for_timeout(1500)
        text = page.inner_text("main")
        assert "script ready" not in text and "render finished" not in text and "assets ready" not in text, text[:400]
        assert "آماده شد" in text or "تمام شد" in text, text[:400]
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], "events: " + "\n".join(bad[:20])
        page.get_by_role("tab", name="تولید و خروجی").click()
        page.wait_for_timeout(1500)
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], "production: " + "\n".join(bad[:20])                       # «15.0 فریم بر ثانیه», «مدت 21.6 ثانیه», «0 رشته‌ی باز» became Persian digits
    finally:
        ctx.close()


def _running_job(text_fa: str, text_en: str) -> dict:
    """A running job as the API sends it (what `describe.activity` builds is pinned by tests/test_core_audit_progress.py)."""
    return {"id": 9001, "kind": "prod.final", "resource": "cpu", "title": "ساخت نسخهٔ نهایی", "status": "running", "payload": {}, "result": {}, "progress": 0.4,
            "progress_text": text_en, "priority": 0, "attempts": 1, "max_attempts": 3, "cancel_requested": False, "error": "", "error_code": "", "waiting_reason": "",
            "created_at": "2026-11-15T10:00:00Z", "started_at": "2026-11-15T10:00:05Z", "finished_at": None, "duration_sec": None, "gpu_seconds": 0, "estimated_sec": None,
            "page": None, "episode": None,
            "activity": {"title_fa": "ساخت نسخهٔ نهایی", "title_en": "Building the final version", "for_fa": "", "for_en": "", "phase": "running", "model": "", "device": "",
                         "device_fa": "", "device_en": "", "warn": False, "line_fa": text_fa, "line_en": text_en, "note_fa": text_fa, "note_en": text_en,
                         "step": None, "steps": None, "tokens": None, "tps": None, "eta_sec": None}}


@pytest.mark.parametrize("size", SIZES)
def test_a_running_job_on_the_home_page_shows_its_progress_line_in_persian(browser, server, seeded, size):
    def fake(route):
        data = route.fetch().json()
        data["active_jobs"] = [_running_job("کلیپِ شاتِ ۳ از ۵", "shot clip 3/5")]
        route.fulfill(json=data)

    from tests_ui.test_qa_sweep import VIEWPORTS

    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR", has_touch=(size == "phone"))
    ctx.add_init_script("try { localStorage.setItem('instai.lang', 'fa'); } catch (e) {}")
    page = ctx.new_page()
    try:
        page.route("**/api/dashboard*", fake)
        page.goto(server + "/", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        text = page.inner_text("main")
        assert "کلیپِ شاتِ ۳ از ۵" in text, text[:500]
        assert "shot clip" not in text, text[:500]
        assert violations(page.evaluate(JS_TEXT)) == []
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1
    finally:
        ctx.close()
