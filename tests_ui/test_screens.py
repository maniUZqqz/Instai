"""Main screens in Persian at desktop and phone width: renders, RTL, no console errors, no failed requests, no horizontal page scroll,
bundled font loaded, touch targets reachable, language/theme toggles, and the real flows (wizard strategy, episode video)."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}
SHOTS = Path(os.environ.get("INSTAI_UI_SHOTS", tempfile.gettempdir())) / "instai-ui-shots"
PERSIAN = re.compile(r"[؀-ۿ]")


def open_page(browser, base, size, path, lang="fa"):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR", has_touch=(size == "phone"))
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); }} catch (e) {{}}")
    page = ctx.new_page()
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_timeout(600)
    return ctx, page, problems


def routes(seeded):
    a = seeded["anime_whatif"]
    return {
        "dashboard": "/", "pages": "/pages", "wizard": "/pages/new", "workspace": f"/pages/{a['page']}", "characters": f"/pages/{a['page']}/characters",
        "series": f"/series/{a['series']}", "episode": f"/episodes/{a['episodes'][0]}", "monitor": "/monitor", "system": "/system", "settings": "/settings",
        "explainer": f"/series/{seeded['concept_explainer']['series']}",
    }


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_every_main_screen_renders_in_persian_rtl(browser, server, seeded, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, path in routes(seeded).items():
        ctx, page, problems = open_page(browser, server, size, path)
        try:
            html = page.locator("html")
            if html.get_attribute("dir") != "rtl" or not (html.get_attribute("lang") or "").startswith("fa"):
                failures.append(f"{name}: html dir/lang = {html.get_attribute('dir')}/{html.get_attribute('lang')}")
            text = page.locator("main, #root").first.inner_text()
            if not PERSIAN.search(text):
                failures.append(f"{name}: no Persian text rendered")
            if page.locator("main, [role=main]").count() == 0:
                failures.append(f"{name}: no <main> landmark")
            sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
            if sw > iw + 1:
                failures.append(f"{name}: horizontal scroll ({sw} > {iw})")
            if not page.evaluate("document.fonts.check('16px Vazirmatn')"):
                failures.append(f"{name}: Vazirmatn font not loaded")
            if page.locator("text=Something went wrong").count() or page.locator("[data-error-boundary]").count():
                failures.append(f"{name}: error boundary shown")
            failures += [f"{name}: {p}" for p in problems]
            page.screenshot(path=str(SHOTS / f"{size}-{name}.png"), full_page=False)
        finally:
            ctx.close()
    assert not failures, "\n".join(failures)


def test_language_and_theme_toggles(browser, server):
    ctx, page, problems = open_page(browser, server, "desktop", "/")
    try:
        page.get_by_role("button", name=re.compile("تغییر زبان")).click()
        page.wait_for_timeout(400)
        assert page.locator("html").get_attribute("dir") == "ltr" and page.locator("html").get_attribute("lang") == "en"
        assert page.locator("text=Dashboard").count() > 0
        page.get_by_role("button", name=re.compile("Switch language")).click()
        page.wait_for_timeout(400)
        assert page.locator("html").get_attribute("dir") == "rtl"
        before = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.get_by_role("button", name=re.compile("حالت تیره|حالت روشن")).click()
        page.wait_for_timeout(300)
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") != before
        assert not problems, problems
    finally:
        ctx.close()


def test_phone_menu_opens_and_navigates(browser, server):
    ctx, page, problems = open_page(browser, server, "phone", "/")
    try:
        page.get_by_role("button", name="منو").click()
        page.wait_for_timeout(300)
        page.get_by_role("link", name=re.compile("سیستم")).first.click()
        page.wait_for_url(re.compile(r"/system$"))
        assert page.locator("text=nvidia").count() + page.locator("text=GPU").count() + page.locator("text=کارت گرافیک").count() > 0
        assert not problems, problems
    finally:
        ctx.close()


def test_dashboard_shows_real_data_and_demo_banner(browser, server, seeded):
    ctx, page, problems = open_page(browser, server, "desktop", "/")
    try:
        body = page.locator("body").inner_text()
        for fmt in ("anime_whatif", "recurring_character", "concept_explainer"):
            assert f"نمونه {fmt}" in body, f"page card for {fmt}"
        assert "آزمایشی" in body, "demo-mode banner is visible"
        assert not problems, problems
    finally:
        ctx.close()


def test_wizard_idea_to_strategy_creates_a_page(browser, server):
    from tests_ui.conftest import Api

    ctx, page, problems = open_page(browser, server, "desktop", "/pages/new")
    try:
        page.get_by_label(re.compile("^نام صفحه")).first.fill("صفحه‌ی ویزارد")
        assert page.get_by_text("حق تجاری").count() > 0, "the fan-content notice is shown for the anime format"
        for _ in range(6):  # walk the steps until the idea step
            if page.get_by_role("button", name="پیشنهاد استراتژی").count():
                break
            page.get_by_role("button", name="بعدی", exact=True).click()
            page.wait_for_timeout(250)
        page.get_by_label(re.compile("^ایده")).first.fill("اگر قهرمان تصمیم دیگری می‌گرفت")
        page.get_by_role("button", name="پیشنهاد استراتژی").click()
        page.get_by_text("ستون‌های محتوا").first.wait_for(timeout=90000)  # the editable proposal appears
        page.get_by_role("button", name=re.compile("^ساخت صفحه")).first.click()
        page.wait_for_url(re.compile(r"/pages/\d+"), timeout=30000)
        names = [p["name"] for p in Api(server).get("/api/pages")]
        assert "صفحه‌ی ویزارد" in names
        assert not problems, problems
    finally:
        ctx.close()


def test_episode_page_plays_the_rendered_preview(browser, server, seeded):
    api = seeded["api"]
    ep = seeded["anime_whatif"]["episodes"][0]
    detail = api.get(f"/api/episodes/{ep}")
    if not detail["videos"]:
        pytest.skip("no ffmpeg on this machine: no video was rendered")
    ctx, page, problems = open_page(browser, server, "desktop", f"/episodes/{ep}")
    try:
        video = page.locator("video").first
        video.wait_for(timeout=15000)
        page.wait_for_function("document.querySelector('video').readyState >= 1", timeout=15000)
        assert page.evaluate("document.querySelector('video').duration") > 3
        assert (page.evaluate("document.querySelector('video').videoHeight")) > page.evaluate("document.querySelector('video').videoWidth"), "9:16"
        page.screenshot(path=str(SHOTS / "desktop-episode-video.png"))
        assert not problems, problems
    finally:
        ctx.close()
