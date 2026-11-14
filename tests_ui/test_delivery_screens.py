"""Delivery on screen (0.16), in Persian (RTL) and English (LTR), desktop and phone: the audio settings (loudness profiles), the networks of a page, the delivery plan and the caption
check under a publication, and the sound rows of the quality panel. The server of these tests has fake services and no GPU; the seeded anime episode has a rendered preview."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import PERSIAN, SHOTS, open_page  # noqa: E402


def api_of(seeded):
    return seeded["api"]


def episode_ready(seeded) -> int:
    a = seeded["anime_whatif"]
    ep = api_of(seeded).get(f"/api/episodes/{a['episodes'][0]}")
    if ep["state"] not in ("ready_for_approval", "approved", "scheduled", "published"):
        pytest.skip("the seeded episode has no rendered preview here (no ffmpeg?)")
    return a["episodes"][0]


@pytest.fixture(scope="module")
def publication(server, seeded):
    """Two networks on the page (one fits the 9:16 episode, one does not), and a publication whose caption has a broken number and a glued hashtag."""
    api = api_of(seeded)
    ep = episode_ready(seeded)
    page = seeded["anime_whatif"]["page"]
    for platform in ("ig_reel", "yt_wide"):
        api.post(f"/api/pages/{page}/targets", {"platform": platform})
    pub = api.post(f"/api/pages/{page}/publications", {"episode": ep, "caption": "۵۰ سکه = ۶۰۰٬۰۰ تومان", "hashtags": ["سریالکوتاه", "انیمیشن"]})
    return {"page": page, "pub": pub["id"], "episode": ep}


def no_scroll(page):
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}"


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_publishing_tab_shows_the_networks_the_plan_and_the_caption_check(browser, server, publication, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_page(browser, server, size, f"/pages/{publication['page']}/publishing", lang)
    try:
        page.get_by_test_id("networks-card").wait_for(timeout=30000)
        card = page.get_by_test_id(f"delivery-{publication['pub']}")
        card.wait_for(timeout=30000)
        page.wait_for_selector(f"[data-testid=delivery-{publication['pub']}] [data-testid=delivery-net-ig_reel]", timeout=30000)
        fits, wide = card.get_by_test_id("delivery-net-ig_reel"), card.get_by_test_id("delivery-net-yt_wide")
        assert fits.count() == 1 and wide.count() == 1
        text = card.inner_text()
        if lang == "fa":
            assert "آماده" in fits.inner_text() or "ساخته می‌شود" in fits.inner_text(), fits.inner_text()
            assert "نسبت تصویر نمی‌خورد" in wide.inner_text() and "برش" in wide.inner_text(), wide.inner_text()
            assert PERSIAN.search(text)
        else:
            assert "A file is made" in fits.inner_text() and "does not fit" in wide.inner_text() and "crop" in wide.inner_text(), (fits.inner_text(), wide.inner_text())
            assert not PERSIAN.search(text.replace("«", "").replace("»", "")) or "سریال" in text      # only the user's own caption / hashtag text may be Persian
        # the check reads the SAVED caption: a broken number and a glued hashtag, with the repaired form shown
        card.get_by_test_id("lint-broken_number").wait_for(timeout=15000)
        assert card.get_by_test_id("lint-glued_hashtag").count() == 1
        assert "سریال_کوتاه" in card.inner_text()
        # the draft in the box is checked too (nothing is saved): a clean text clears the warnings
        box = page.locator("textarea").first
        box.fill("متن درست و کامل.")
        page.wait_for_selector(f"[data-testid=delivery-{publication['pub']}] [data-testid=lint-broken_number]", state="detached", timeout=15000)
        no_scroll(page)
        page.screenshot(path=str(SHOTS / f"delivery-publishing-{lang}-{size}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


def test_a_network_is_added_switched_and_the_whole_frame_option_is_saved(browser, server, publication, seeded):
    api = api_of(seeded)
    ctx, page, problems = open_page(browser, server, "desktop", f"/pages/{publication['page']}/publishing", "fa")
    try:
        card = page.get_by_test_id("networks-card")
        card.wait_for(timeout=30000)
        before = {t["network"] for t in api.get(f"/api/pages/{publication['page']}/targets")}
        assert {"ig_reel", "yt_wide"} <= before
        card.locator("select").select_option("telegram")
        card.get_by_test_id("network-add").click()
        page.wait_for_function("document.querySelectorAll('[data-testid^=network-]').length >= 4", timeout=15000)
        after = {t["network"]: t for t in api.get(f"/api/pages/{publication['page']}/targets")}
        assert "telegram" in after
        # switch «whole frame with blurred sides» on for the 16:9 network: the plan changes from «does not fit» to «whole frame»
        wide = after["yt_wide"]
        row = card.get_by_test_id(f"network-{wide['id']}")
        row.locator("label.switch").nth(1).click()
        page.wait_for_function("t => document.querySelector(`[data-testid=delivery-net-yt_wide]`)?.innerText.includes(t)", arg="کناره‌های محو", timeout=20000)
        assert {t["network"]: t["fit"] for t in api.get(f"/api/pages/{publication['page']}/targets")}["yt_wide"] == "blur"
        row.locator("label.switch").nth(1).click()
        page.wait_for_function("() => document.querySelector('[data-testid=delivery-net-yt_wide]')?.innerText.includes('فایلی ساخته نمی‌شود')", timeout=20000)
        card.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / "delivery-networks-fa.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_audio_settings_have_the_loudness_profiles(browser, server, seeded, lang):
    page_id = seeded["anime_whatif"]["page"]
    ctx, page, problems = open_page(browser, server, "desktop", f"/pages/{page_id}/settings", lang)
    try:
        page.locator(".seg button").filter(has_text="صدا" if lang == "fa" else "Audio").first.click()
        box = page.get_by_test_id("loudness-profile")
        box.wait_for(timeout=20000)
        buttons = box.locator(".seg button")
        assert buttons.count() == 4
        # a new page: -14 = the first profile is pressed
        assert box.locator(".seg button[aria-pressed=true]").count() == 1
        assert box.locator(".seg button").nth(0).get_attribute("aria-pressed") == "true"
        buttons.nth(1).click()                                                       # «Telegram and Aparat (-16)»
        assert box.locator(".seg button").nth(1).get_attribute("aria-pressed") == "true"
        buttons.nth(2).click()                                                       # broadcast -23
        assert box.locator(".seg button").nth(2).get_attribute("aria-pressed") == "true"
        buttons.nth(0).click()
        assert box.locator(".seg button").nth(0).get_attribute("aria-pressed") == "true"
        assert box.get_by_role("switch").count() == 1 and box.get_by_role("switch").is_checked()
        text = box.inner_text()
        assert (PERSIAN.search(text) is not None) == (lang == "fa"), text[:200]
        no_scroll(page)
        box.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"delivery-audio-settings-{lang}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_quality_panel_has_the_sound_rows_in_the_readers_language(browser, server, publication, lang):
    ctx, page, problems = open_page(browser, server, "desktop", f"/episodes/{publication['episode']}#production", lang)
    try:
        for name in ("loudness", "audio_echo", "audio_masking", "audio_phase"):
            row = page.get_by_test_id(f"qc-{name}")
            row.wait_for(timeout=30000)
            assert row.inner_text().strip(), name
        loud = page.get_by_test_id("qc-loudness").inner_text()
        echo = page.get_by_test_id("qc-audio_echo").inner_text()
        if lang == "fa":
            assert PERSIAN.search(loud) and PERSIAN.search(echo) and "اکو" in echo
        else:
            assert "Loudness" in loud and "echo" in echo.lower() and not PERSIAN.search(loud) and not PERSIAN.search(echo), (loud, echo)
        no_scroll(page)
        page.get_by_test_id("qc-audio_echo").scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"delivery-quality-panel-{lang}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()
