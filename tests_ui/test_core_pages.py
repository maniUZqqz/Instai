"""Audit batch "ia_core" (2026-11-14): the Persian pages carry no command line, no English sentence and no Latin digit next to Persian words.

* /system, /lab/voices, /settings, /downloads, /models, /report, /queue, /monitor, /choice/<id> at desktop and phone width, in Persian;
* the owner reads Persian only and never types a command: no «Download-Models.bat --only ...», «pip install ...», «piper.exe ...» in any visible text;
* technical text (a version, a host name, a command kept for the «اطلاعات فنی» toggle) lives in `.ltr` / `code` / `details` / `[dir=ltr]` and is skipped;
* the system page shows an install BUTTON where it used to show a command; the update badge appears when GitHub has a newer version (a fake status);
* the episode page: the shot list names a shot that becomes a still, and «ساخت پیش‌نمایش» offers the one-click puppet.
Run:  python -m pytest tests_ui/test_core_pages.py -q   (see tests_ui/conftest.py)."""
from __future__ import annotations

import re

import pytest

from tests_ui.test_qa_sweep import visit

PERSIAN = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
COMMAND = re.compile(r"Download-Models|pip install|\.exe\b|--[a-z]|python -m|npm |tools\\|\w+\\\w+")
WORD = r"[a-z][a-z'\-]{2,}"
ENGLISH = re.compile(rf"(?<![\w])({WORD})(?![\w'\-])(?:[\s,;:/()+]+{WORD}(?![\w'\-]))+")
NUMBER = re.compile(r"^[0-9]+(?:[.,][0-9]+)?$")        # ASCII digits only: Python's \d also matches the Persian ones
PAGES = ["/system", "/lab/voices", "/settings", "/downloads", "/models", "/report", "/queue", "/monitor"]

JS_TEXT = """() => {
  const out = []
  const w = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT)
  let n
  while ((n = w.nextNode())) {
    const t = n.nodeValue.replace(/\\s+/g, ' ').trim()
    const el = n.parentElement
    if (!t || !el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(el.tagName)) continue
    if (el.closest('code, pre, details, .ltr, [dir=ltr], .log-view, .mono, svg, option')) continue
    const cs = getComputedStyle(el)
    if (cs.display === 'none' || cs.visibility === 'hidden') continue
    out.push(t)
  }
  return out
}"""


def violations(texts: list[str]) -> list[str]:
    bad = []
    for t in texts:
        if COMMAND.search(t):
            bad.append("command: " + t[:100])
        elif ENGLISH.search(t):
            bad.append("english: " + t[:100])
        toks = t.split()
        for i, tok in enumerate(toks):
            if not NUMBER.match(tok):
                continue
            if i and LATIN.search(toks[i - 1]):                # «Wan 2.2», «RTX 3060», «FFmpeg 7.1»: the number belongs to a Latin product name
                continue
            if any(PERSIAN.search(x) for x in toks[max(0, i - 1):i] + toks[i + 1:i + 2]):
                bad.append("latin digit: " + t[:100])
                break
    return bad


@pytest.mark.parametrize("size", ["desktop", "phone"])
@pytest.mark.parametrize("path", PAGES)
def test_persian_pages_have_no_command_line_english_sentence_or_latin_digit(browser, server, seeded, path, size):
    ctx, page, problems = visit(browser, server, path, size, "fa")
    try:
        bad = violations(page.evaluate(JS_TEXT))
        assert bad == [], f"{path} ({size}): " + "\n".join(bad[:25])
    finally:
        ctx.close()


def test_choice_editor_names_posts_in_persian(browser, server, seeded):
    api = seeded["api"]
    sid = api.post(f"/api/pages/{seeded['recurring_character']['page']}/choice-stories", {"template": "prison_escape", "title": "فرار"})["id"]
    ctx, page, _ = visit(browser, server, f"/choice/{sid}", "desktop", "fa")
    try:
        assert violations(page.evaluate(JS_TEXT)) == []
        labels = page.evaluate("() => [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label')).filter(x => /post \\d/.test(x))")
        assert labels == [], labels                                 # «پست ۱» not «post 1»
    finally:
        ctx.close()


def test_system_page_offers_an_install_button_instead_of_a_command(browser, server):
    ctx, page, _ = visit(browser, server, "/system", "desktop", "fa")
    try:
        page.wait_for_selector("text=MOSS-TTS", timeout=20000)
        card = page.locator(".card", has_text="MOSS-TTS").first
        assert card.get_by_role("button", name="نصب").count() >= 1
        assert "Download-Models" not in card.inner_text()
        card.locator("summary", has_text="اطلاعات فنی").first.click()           # the command is still there for whoever needs it
        assert "Download-Models" in card.inner_text()
    finally:
        ctx.close()


def test_update_badge_shows_when_a_newer_version_exists(browser, server):
    ctx, page, _ = visit(browser, server, "/", "desktop", "fa", wait="domcontentloaded")
    try:
        page.route("**/api/update/status*", lambda r: r.fulfill(json={"available": True, "current": "0.13.0", "latest": "9.9.9", "checked_at": None, "error": "",
                                                                      "disabled": False, "running_jobs": 0, "applying": False}))
        page.reload(wait_until="networkidle")
        badge = page.get_by_test_id("update-badge")
        badge.wait_for(timeout=10000)
        assert "نسخهٔ تازه آماده است" in badge.inner_text()
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1
    finally:
        ctx.close()


def test_update_badge_is_absent_when_up_to_date(browser, server):
    ctx, page, _ = visit(browser, server, "/", "phone", "fa", wait="domcontentloaded")
    try:
        page.route("**/api/update/status*", lambda r: r.fulfill(json={"available": False, "current": "0.13.0", "latest": "0.13.0", "checked_at": None, "error": "",
                                                                      "disabled": False, "running_jobs": 0, "applying": False}))
        page.reload(wait_until="networkidle")
        assert page.get_by_test_id("update-badge").count() == 0
    finally:
        ctx.close()


def fresh_puppet_episode(api) -> int:
    """A new recurring-character page (so no puppet exists yet, however often this runs against the same app) whose first shot is a puppet shot."""
    strat = api.wait_job(api.post("/api/strategy", {"page_name": "نمونهٔ بدون عروسک", "format": "recurring_character", "language": "fa", "idea": "ایده"}))["result"]["strategy"]
    page = api.post("/api/pages", {"name": "نمونهٔ بدون عروسک", "format": "recurring_character", "languages": ["fa"], "idea": "ایده", "strategy": strat,
                                   "series": {**strat["series_ideas"][0], "episodes": 2}, "profiles": {"production": {"episode_length_sec": 20}}})
    sid = api.get(f"/api/pages/{page['id']}/series")[0]["id"]
    plan = api.wait_job(api.post(f"/api/series/{sid}/plan", {"episodes_count": 2}))["result"]["plan"]
    ep = api.post(f"/api/series/{sid}/apply-plan", {"plan": plan})["episodes"][0]["id"]
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-script"))
    api.wait_job(api.post(f"/api/episodes/{ep}/approve-script")["job"])
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-storyboard"))
    shots = [x for sc in api.get(f"/api/episodes/{ep}")["scenes"] for x in sc["shots"]]
    api.patch(f"/api/shots/{shots[0]['id']}", {"technique": "puppet_2d"})
    return ep


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_episode_page_warns_about_a_shot_that_becomes_a_still_and_offers_the_puppet(browser, server, size):
    from tests_ui.conftest import Api

    api = Api(server)
    ep = fresh_puppet_episode(api)
    assert api.get(f"/api/episodes/{ep}/preflight")["needs_rig"], "the new page must have no puppet yet"
    ctx, page, _ = visit(browser, server, f"/episodes/{ep}#storyboard", size, "fa")
    try:
        banner = page.locator(".notice", has_text="عروسک").first
        banner.wait_for(timeout=15000)
        assert "تصویر ثابت با حرکت دوربین" in banner.inner_text().replace("تصویرِ ثابت", "تصویر ثابت")
        assert banner.get_by_role("button", name="ساخت عروسکِ چوبیِ خودکار").count() == 1
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1
        page.get_by_role("tab", name="تولید و خروجی").click()
        page.get_by_role("button", name="ساخت پیش‌نمایش").first.click()
        dlg = page.get_by_role("dialog")
        dlg.wait_for(timeout=10000)
        assert "عروسکِ شخصیت‌ها آماده نیست" in dlg.inner_text()
        assert dlg.get_by_role("button", name="بساز و ادامه بده").count() == 1 and dlg.get_by_role("button", name="بدون عروسک ادامه بده").count() == 1
        dlg.get_by_role("button", name="بساز و ادامه بده").click()
        for _ in range(40):                                            # the rig is made by a request the page just sent: poll, never a fixed wait (a busy machine needs longer)
            if api.get(f"/api/episodes/{ep}/preflight")["needs_rig"] == []:
                break
            page.wait_for_timeout(500)
        assert api.get(f"/api/episodes/{ep}/preflight")["needs_rig"] == []
    finally:
        ctx.close()


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_series_page_shows_the_idea_the_project_started_from(browser, server, size):
    from tests_ui.conftest import Api

    api = Api(server)
    idea = next(i for i in api.get("/api/ideas")["ideas"] if i["format"] == "recurring_character")
    out = api.post(f"/api/ideas/{idea['key']}/start", {"page_name": "صفحهٔ از ایده", "language": "fa"})
    ctx, page, _ = visit(browser, server, f"/series/{out['series_id']}", size, "fa")
    try:
        card = page.locator(".card", has_text="ایدهٔ شروعِ این پروژه").first
        card.wait_for(timeout=15000)
        text = card.inner_text()
        assert idea["title_fa"] in text and idea["logline_fa"][:30] in text
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1
    finally:
        ctx.close()
