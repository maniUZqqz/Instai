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
