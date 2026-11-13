"""The art/animation style library (groups, suitability, search by the names people use, preview pictures, the «تمِ رنگی» tab) and the idea bank
(search, filters, favourites, «شروعِ پروژه از این ایده») in Persian (RTL) AND English (LTR), at desktop and phone width."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import PERSIAN, SHOTS, open_page  # noqa: E402
from tests_ui.test_studio_screens import check_shell, exact, stray_persian, tx  # noqa: E402


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_style_library_groups_suitability_search_and_color_theme_tab(browser, server, size, lang):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_page(browser, server, size, "/library", lang)
    failures: list[str] = []
    try:
        page.locator(".style-card").first.wait_for(timeout=15000)
        n = page.locator(".style-card").count()
        assert n >= 100, f"{n} styles"
        assert page.locator(".filter-chip").count() == 9, "all + the eight art groups"
        # the previews are drawn pictures, not empty boxes
        assert page.locator(".style-card .swatch").first.evaluate("e => getComputedStyle(e).backgroundImage").startswith("url(")
        page.locator(".filter-chip").nth(4).click()
        page.wait_for_timeout(200)
        n2 = page.locator(".style-card").count()
        assert 0 < n2 < n, "a group narrows the gallery"
        page.locator(".filter-chip").first.click()
        # "suits video" narrows too
        page.get_by_role("button", name=exact(tx("lib.suits_character", lang))).click()
        page.wait_for_timeout(200)
        n3 = page.locator(".style-card").count()
        assert 0 < n3 < n
        page.get_by_role("button", name=exact(tx("lib.suits_any", lang))).click()
        # a name people search by finds the generic look
        box = page.get_by_role("searchbox")
        box.fill("lego")
        page.wait_for_timeout(250)
        assert page.locator(".style-card").count() == 1
        page.locator(".style-card").first.click()
        page.get_by_role("button", name=exact(tx("lib.duplicate", lang))).wait_for(timeout=5000)
        main = page.locator("main").inner_text()
        assert "Lego-like bricks" in page.locator("[data-testid=known-as]").inner_text(), "the name the owner knows it by is shown as an 'inspired by' caption"
        assert page.locator(".style-card .known-as").first.inner_text().startswith("≈"), "and on the card itself"
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-styles-v2.png"))
        if lang == "en" and stray_persian(main):
            failures.append("styles (en): stray Persian text: " + str(stray_persian(main)))
        check_shell(page, lang, f"styles {size} {lang}", failures)
        # the colour theme tab carries its new name
        page.get_by_role("tab", name=exact(tx("lib.tab_themes", lang))).click()
        page.wait_for_timeout(250)
        assert page.locator(".theme-card").count() >= 24
        assert tx("lib.tab_themes", lang) in ("تمِ رنگی", "Color themes")
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_idea_bank_search_filters_and_start_a_project(browser, server, size, lang):
    from tests_ui.conftest import Api

    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_page(browser, server, size, "/ideas", lang)
    failures: list[str] = []
    try:
        page.locator(".idea-card").first.wait_for(timeout=15000)
        n = page.locator(".idea-card").count()
        assert n >= 100, f"{n} ideas"
        chips = page.locator('[role=group] .filter-chip')
        assert chips.count() >= 7, "all + six categories + tags"
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-ideas.png"))
        main = page.locator("main").inner_text()
        if lang == "en" and stray_persian(main):
            failures.append("ideas (en): stray Persian text: " + str(stray_persian(main)))
        if lang == "fa" and not PERSIAN.search(main):
            failures.append("ideas (fa): no Persian text")
        check_shell(page, lang, f"ideas {size} {lang}", failures)
        # search in either language reaches the owner's teleportation idea
        page.locator("#idea-q").fill("teleport")
        page.wait_for_timeout(250)
        assert page.locator(".idea-card").count() == 1
        page.locator("#idea-q").fill("تلپورت")
        page.wait_for_timeout(250)
        assert page.locator(".idea-card").count() == 1
        # star it, then "only starred" shows just that one
        star = page.get_by_role("button", name=exact(tx("ideas.fav", lang)))
        if star.count():                       # (an earlier run of this session may have starred it already)
            star.click()
            page.wait_for_timeout(400)
        assert page.get_by_role("button", name=exact(tx("ideas.unfav", lang))).count() == 1
        page.locator("#idea-q").fill("")
        page.get_by_label(tx("ideas.only_fav", lang)).check()
        page.wait_for_timeout(250)
        assert page.locator(".idea-card").count() == 1
        page.get_by_label(tx("ideas.only_fav", lang)).uncheck()
        # start a project from the idea: the look is picked once, then the series opens
        page.locator("#idea-q").fill("teleport")
        page.wait_for_timeout(250)
        page.get_by_role("button", name=exact(tx("ideas.start", lang))).click()
        page.get_by_role("button", name=exact(tx("ideas.start_go", lang))).wait_for(timeout=5000)
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-idea-start.png"))
        assert page.locator(".idea-card .style-card.selected").count() == 1, "the idea's own best-fitting style is already selected"
        page.get_by_role("button", name=exact(tx("ideas.start_go", lang))).click()
        page.wait_for_url(re.compile(r".*/series/\d+"), timeout=20000)
        sid = int(page.url.rsplit("/", 1)[1])
        series = Api(server).get(f"/api/series/{sid}")
        assert series["look"].get("style_key"), "the project carries its own look"
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()
