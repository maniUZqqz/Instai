"""Audit round ia_regress: the «نسخهٔ تازه آماده است» badge must never push a page sideways.

The independent check of 2026-11-15 found that, once GitHub has a newer InstAI, the badge's sentence (about 240 px) made the top bar 565 px wide on a 390 px
phone: every page scrolled sideways and the left edge was clipped. The earlier tests only looked at the badge on a desktop, and the QA sweep runs with the
update check switched off, so none of them saw it.

* the status is FAKED to "a newer version exists", so the badge is on screen in every check below;
* the viewport is a REAL 390 px one (a plain narrow window, not a mobile emulator: an emulator widens `window.innerWidth` to the content width and hides the very
  scroll this test looks for), so `innerWidth` is asserted too;
* every screen of the sidebar and of the sweep (and any screen another feature adds to the sidebar) at 390 px, in Persian and English;
* the sizes in between (320 ... 1024) on the home page, and the worst top bar (queue badge + running jobs + the update badge) at 320 / 390 / 430;
* at a desktop width the sentence is still shown in full; on a phone it collapses to the icon but keeps its name (`aria-label`, `title`) and stays pressable.
Run:  python -m pytest tests_ui/test_update_badge_layout.py -q   (see tests_ui/conftest.py; INSTAI_UI_BASE=http://127.0.0.1:PORT drives a running app)."""
from __future__ import annotations

import re

import pytest

from tests_ui.test_qa_sweep import STATIC

STATUS = {"available": True, "current": "0.22.0", "latest": "10.23.10", "checked_at": None, "error": "", "disabled": False, "running_jobs": 0, "applying": False}
QUEUE = {"running": 2, "queued": 3, "waiting_node": 1, "waiting_service": 1, "scheduled": 0, "waiting_turn": 1, "waiting": 3, "offline_nodes": []}
JOBS = [{"id": 900 + i, "kind": "episode.produce", "status": "running", "progress": 0.4, "title": "", "activity": None, "waiting_reason": ""} for i in range(3)]
SENTENCE = "نسخهٔ تازه آماده است"
SKIP = ("/no-such-screen",)

TOPBAR_JS = """() => {
  const de = document.documentElement
  const tb = document.querySelector('header.topbar')
  const kids = [...tb.children].filter(e => { const q = e.getBoundingClientRect(); return q.width > 0 && q.height > 0 })
  return {
    iw: window.innerWidth, cw: de.clientWidth, sw: de.scrollWidth, bodySw: document.body.scrollWidth,
    topbarSw: tb.scrollWidth, topbarCw: tb.clientWidth,
    outside: kids.filter(e => { const q = e.getBoundingClientRect(); return q.left < -0.5 || q.right > window.innerWidth + 0.5 })
                 .map(e => (e.getAttribute('data-testid') || e.className || e.tagName) + ' ' + Math.round(e.getBoundingClientRect().left) + '..' + Math.round(e.getBoundingClientRect().right)),
  }
}"""


def open_page(browser, base: str, path: str, width: int, lang: str = "fa", worst: bool = False):
    """A new context with a plain window `width` px wide (no mobile emulation), the update status faked to «available»; `worst` adds the other top-bar badges."""
    ctx = browser.new_context(viewport={"width": width, "height": 780}, locale="fa-IR" if lang == "fa" else "en-US", has_touch=width < 500)
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); }} catch (e) {{}}")
    ctx.route(re.compile(r"/api/update/status"), lambda r: r.fulfill(json=STATUS))
    if worst:
        ctx.route(re.compile(r"/api/queue/summary"), lambda r: r.fulfill(json=QUEUE))
        ctx.route(re.compile(r"/api/jobs\?status=queued(,|%2C)running"), lambda r: r.fulfill(json=JOBS))
    page = ctx.new_page()
    page.goto(base + path, wait_until="networkidle")
    page.get_by_test_id("update-badge").wait_for(timeout=15000)
    page.wait_for_timeout(300)
    return ctx, page


def assert_inside(page, where: str, width: int) -> dict:
    m = page.evaluate(TOPBAR_JS)
    assert m["iw"] == width, f"{where}: the window is {m['iw']} px, not {width}: a mobile emulator hides sideways scroll"
    assert m["sw"] <= m["cw"] and m["bodySw"] <= m["cw"], f"{where}: the page scrolls sideways (scrollWidth {m['sw']} > {m['cw']})"
    assert m["topbarSw"] <= m["topbarCw"], f"{where}: the top bar is wider than the screen ({m['topbarSw']} > {m['topbarCw']})"
    assert m["outside"] == [], f"{where}: top-bar items outside the screen: {m['outside']}"
    return m


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_every_screen_fits_a_390px_phone_with_the_update_badge_on(browser, server, lang):
    ctx, page = open_page(browser, server, "/", 390, lang)
    try:
        links = page.evaluate("[...document.querySelectorAll('nav a[href]')].map(a => a.getAttribute('href'))")
    finally:
        ctx.close()
    paths = [p for p in dict.fromkeys([*STATIC, *links]) if p not in SKIP and p.startswith("/")]
    assert len(paths) >= 20, paths
    failures: list[str] = []
    for path in paths:
        ctx, page = open_page(browser, server, path, 390, lang)
        try:
            assert_inside(page, f"{lang} {path}", 390)
            box = page.get_by_test_id("update-badge").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390 + 0.5 and box["height"] >= 32, (path, box)
        except AssertionError as e:
            failures.append(str(e))
        finally:
            ctx.close()
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("width", [320, 360, 390, 430, 560, 640, 768, 960, 1024])
def test_the_home_page_fits_every_width_with_the_update_badge_on(browser, server, width):
    ctx, page = open_page(browser, server, "/", width)
    try:
        assert_inside(page, f"home at {width}", width)
    finally:
        ctx.close()


@pytest.mark.parametrize("width", [320, 390, 430, 640])
def test_the_busiest_top_bar_fits_too(browser, server, width):
    """The update badge next to the queue badge, a running-jobs counter, the bell, the language and theme buttons: the bar wraps instead of leaving the screen."""
    ctx, page = open_page(browser, server, "/", width, worst=True)
    try:
        assert page.get_by_test_id("queue-badge").count() == 1, "the faked queue badge is not shown: the check would not mean anything"
        assert_inside(page, f"busiest top bar at {width}", width)
    finally:
        ctx.close()


def test_the_badge_keeps_its_sentence_on_a_desktop_and_its_name_on_a_phone(browser, server):
    ctx, page = open_page(browser, server, "/", 1280)
    try:
        badge = page.get_by_test_id("update-badge")
        text = badge.locator(".upd-badge-text")
        assert text.is_visible() and SENTENCE in badge.inner_text()
        assert text.evaluate("e => e.scrollWidth <= e.clientWidth"), "the sentence is cut off on a desktop"
        assert "v10.23.10" in badge.inner_text()
    finally:
        ctx.close()
    ctx, page = open_page(browser, server, "/", 390)
    try:
        badge = page.get_by_test_id("update-badge")
        assert not badge.locator(".upd-badge-text").is_visible(), "on a phone the sentence collapses to the icon"
        assert SENTENCE in (badge.get_attribute("aria-label") or ""), "the collapsed badge keeps its name for a screen reader"
        assert SENTENCE in (badge.get_attribute("title") or ""), "... and for a long-press / hover"
        assert badge.is_enabled() and badge.bounding_box()["width"] >= 36
    finally:
        ctx.close()
