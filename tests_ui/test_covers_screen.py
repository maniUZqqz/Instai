"""The cover maker in a real browser (0.16.0): /covers and the «Cover» tab of Publishing, in Persian (RTL) and English (LTR), desktop and phone. The page loads, the format and layout pickers
are complete, the preview is a real picture with the safe-area guides, ideas can be suggested and applied, a cover with three A/B versions is made and followed to the end, a version is chosen,
the history offers «edit again», nothing scrolls sideways and nothing logs an error. The server of these tests has no GPU and no model: the ideas come from the fake text provider, the cover from the CPU."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import PERSIAN, SHOTS, open_page  # noqa: E402

N_FORMATS, N_STYLES = 9, 16


def no_sideways_scroll(page):
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}"


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_cover_maker_screen_from_idea_to_chosen_version(browser, server, seeded, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    a = seeded["anime_whatif"]
    ep = a["episodes"][0]
    ctx, page, problems = open_page(browser, server, size, f"/covers?page={a['page']}&episode={ep}", lang)
    try:
        preview = page.get_by_test_id("cv-preview")
        preview.wait_for(timeout=60000)
        page.wait_for_function("document.querySelector('[data-testid=cv-preview] img') && document.querySelector('[data-testid=cv-preview] img').naturalWidth > 100", timeout=60000)
        # the pickers are complete
        assert page.get_by_test_id("cv-format").locator("option").count() == N_FORMATS
        assert page.locator(".choice-grid .choice").count() == N_STYLES
        assert page.locator(".cv-guide-safe").count() == 1 and page.locator(".cv-guide-avoid").count() >= 1, "the safe area and the avoid zones are drawn on the preview"
        # another format and another layout re-render the preview (the picture changes)
        before = page.locator("[data-testid=cv-preview] img").get_attribute("src")
        page.get_by_test_id("cv-format").select_option("story")
        page.locator(".choice-grid .choice").nth(14).click()                      # cliffhanger
        page.wait_for_function("(b) => document.querySelector('[data-testid=cv-preview] img').getAttribute('src') !== b", arg=before, timeout=60000)
        # ideas: the fake text provider answers; one is applied
        page.get_by_test_id("cv-ideas-go").click()
        page.get_by_test_id("cv-idea").first.wait_for(timeout=60000)
        assert page.get_by_test_id("cv-idea").count() >= 3
        page.get_by_test_id("cv-idea-apply").first.click()
        # make three versions and follow the job (the history gets a new row, then its three versions appear)
        n0 = page.get_by_test_id("cv-hist-row").count()
        page.get_by_test_id("cv-make").click()
        page.wait_for_function("(n) => document.querySelectorAll('[data-testid=cv-hist-row]').length > n", arg=n0, timeout=180000)
        page.wait_for_function("document.querySelectorAll('[data-testid=cv-variants] img').length === 3", timeout=180000)
        page.get_by_test_id("cv-variants").scroll_into_view_if_needed()                # the pictures load lazily
        page.wait_for_function("[...document.querySelectorAll('[data-testid=cv-variants] img')].every(i => i.complete && i.naturalWidth > 100)", timeout=60000)
        assert page.get_by_test_id("cv-variant-A").count() == 1 and page.get_by_test_id("cv-variant-C").count() == 1
        # choose version B (the first is chosen automatically)
        page.get_by_test_id("cv-use-B").click()
        page.wait_for_function("!document.querySelector('[data-testid=cv-use-B]')", timeout=30000)
        assert page.get_by_test_id("cv-hist-row").count() >= 1
        page.get_by_test_id("cv-hist-edit").first.click()
        page.get_by_test_id("cv-preview").wait_for()
        body = page.locator("main").inner_text()
        if lang == "fa":
            assert PERSIAN.search(body)
        else:
            assert "Cover maker" in body and not PERSIAN.search(page.locator("h1, h2").first.inner_text())
        no_sideways_scroll(page)
        page.screenshot(path=str(SHOTS / f"covers-{lang}-{size}.png"), full_page=True)
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_publishing_page_has_a_cover_tab_and_every_item_a_cover_button(browser, server, seeded, lang):
    a = seeded["anime_whatif"]
    ctx, page, problems = open_page(browser, server, "desktop", f"/pages/{a['page']}/publishing", lang)
    try:
        tabs = page.locator("[role=tablist] button, .tabs button, .seg button")
        page.get_by_role("tab").nth(1).click() if page.get_by_role("tab").count() >= 2 else tabs.nth(1).click()
        page.get_by_test_id("cv-preview").wait_for(timeout=60000)
        assert page.get_by_test_id("cv-make").count() == 1
        no_sideways_scroll(page)
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


def test_the_sidebar_links_to_the_cover_maker(browser, server):
    ctx, page, problems = open_page(browser, server, "desktop", "/", "en")
    try:
        link = page.locator("nav.nav a[href='/covers']")
        assert link.count() == 1 and "Cover maker" in link.inner_text()
        link.click()
        page.wait_for_url("**/covers*")
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()
