"""Word-by-word captions on screen (0.17), in Persian (RTL) and English (LTR), desktop and phone: the picker in the page settings (eight presets drawn by the render engine as real pictures, the
frame shape, the safe-zone guides, saving) and the card of one episode (the page's choice shows through, an override, going back, the SRT file). The server of these tests has fake services and
no GPU; the previews need an ffmpeg with the `ass` filter (the tests skip without it - the picker itself must still render, which the first test checks)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import PERSIAN, SHOTS, open_page  # noqa: E402

PRESETS = ["classic", "pop", "box", "karaoke", "clean", "neon", "typewriter", "lower"]


def no_scroll(page):
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}"


def catalogue(seeded) -> dict:
    return seeded["api"].get("/api/captions")


def wait_pictures(page, scope, count: int):
    """Every preview <img> of the picker has been decoded by the browser (a real picture, not an empty box)."""
    page.wait_for_function(
        "([sel, n]) => { const im = [...document.querySelectorAll(sel + ' .cap-thumb img')]; return im.length >= n && im.every(i => i.complete && i.naturalWidth > 20) }",
        arg=[scope, count], timeout=90000)


def names(seeded, lang) -> dict:
    return {p["key"]: p[lang] for p in catalogue(seeded)["presets"]}


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_page_settings_show_all_eight_presets_as_real_pictures(browser, server, seeded, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page_id = seeded["anime_whatif"]["page"]
    cat = catalogue(seeded)
    assert [p["key"] for p in cat["presets"]] == PRESETS, "the seven presets and the plain look, in this order"
    ctx, page, problems = open_page(browser, server, size, f"/pages/{page_id}/settings", lang)
    try:
        page.locator(".seg button").filter(has_text="ظاهر" if lang == "fa" else "Look").first.click()
        box = page.locator("fieldset", has=page.locator(".cap-grid")).first
        box.wait_for(timeout=30000)
        cards = box.locator(".cap-card")
        cards.nth(7).wait_for(timeout=30000)
        assert cards.count() == 8
        want = names(seeded, lang)
        text = box.inner_text()
        for key in PRESETS:
            assert want[key] in text, (key, want[key])
        assert (PERSIAN.search(text) is not None) == (lang == "fa"), text[:200]
        assert box.locator("input[name=caption-preset]:checked").count() == 1
        assert "selected" in (cards.nth(0).get_attribute("class") or ""), "a page that never picked keeps the plain InstAI subtitle (classic) selected"
        wait_pictures(page, "fieldset:has(.cap-grid)", 8)                         # the pictures are the engine's own, not CSS
        # a preset is picked and the draft is marked unsaved; the frame shape changes the pictures
        cards.nth(3).click()
        assert box.locator(".cap-card.selected").count() == 1
        assert box.locator("input[name=caption-preset]").nth(3).is_checked()
        box.locator(".seg button").filter(has_text="افقی" if lang == "fa" else "Landscape").first.click()
        page.wait_for_function("() => document.querySelectorAll('.cap-thumb.landscape').length === 8", timeout=30000)
        wait_pictures(page, "fieldset:has(.cap-grid)", 8)
        thumb = box.locator(".cap-thumb.landscape").first.bounding_box()
        assert thumb and abs(thumb["width"] / thumb["height"] - 16 / 9) < 0.05, thumb
        no_scroll(page)
        box.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"captions-settings-{lang}-{size}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


def test_picking_a_preset_in_the_page_settings_is_saved_on_the_page(browser, server, seeded):
    api = seeded["api"]
    page_id = seeded["anime_whatif"]["page"]
    ctx, page, problems = open_page(browser, server, "desktop", f"/pages/{page_id}/settings", "fa")
    try:
        page.locator(".seg button").filter(has_text="ظاهر").first.click()
        box = page.locator("fieldset", has=page.locator(".cap-grid")).first
        box.locator(".cap-card").nth(7).wait_for(timeout=30000)
        box.locator(".cap-card").filter(has_text=names(seeded, "fa")["karaoke"]).first.click()
        page.get_by_role("button", name="ذخیره", exact=True).click()
        page.wait_for_function("() => document.body.innerText.includes('ذخیره شد')", timeout=20000)
        saved = api.get(f"/api/pages/{page_id}")["profiles"]["visual"]["caption_style"]
        assert saved["preset"] == "karaoke", saved
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()
        api.put(f"/api/pages/{page_id}/profiles/visual", {**api.get(f"/api/pages/{page_id}")["profiles"]["visual"], "caption_style": {"preset": "classic", "mode": "burned", "zone": "auto"}})


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_episode_card_shows_the_pages_choice_an_override_and_the_srt(browser, server, seeded, lang, size):
    api = seeded["api"]
    a = seeded["anime_whatif"]
    ep = a["episodes"][0]
    api.call("DELETE", f"/api/episodes/{ep}/captions")
    api.put(f"/api/pages/{a['page']}/profiles/visual", {**api.get(f"/api/pages/{a['page']}")["profiles"]["visual"], "caption_style": {"preset": "box", "mode": "burned", "zone": "auto"}})
    want = names(seeded, lang)
    ctx, page, problems = open_page(browser, server, size, f"/episodes/{ep}#production", lang)
    try:
        card = page.get_by_test_id("captions-card")
        card.wait_for(timeout=30000)
        assert want["box"] in card.get_by_test_id("captions-current").inner_text()          # the page's choice shows through
        assert card.locator(".cap-grid").count() == 0, "the previews are only drawn when the card is opened"
        card.get_by_test_id("captions-toggle").click()
        card.locator(".cap-card").nth(7).wait_for(timeout=30000)
        wait_pictures(page, "[data-testid=captions-card]", 8)
        card.locator(".cap-card").filter(has_text=want["neon"]).first.click()
        page.wait_for_function(f"() => document.querySelector('[data-testid=captions-current]').innerText.includes({want['neon']!r})", timeout=30000)
        assert api.get(f"/api/episodes/{ep}/captions")["override"] == {"preset": "neon"}
        assert api.get(f"/api/pages/{a['page']}")["profiles"]["visual"]["caption_style"]["preset"] == "box", "the page keeps its own choice"
        reset = page.get_by_role("button", name="برگشت به انتخابِ صفحه" if lang == "fa" else "Back to the page's choice")
        reset.click()
        page.wait_for_function(f"() => document.querySelector('[data-testid=captions-current]').innerText.includes({want['box']!r})", timeout=30000)
        assert api.get(f"/api/episodes/{ep}/captions")["override"] == {}
        srt = api.get(f"/api/episodes/{ep}")["captions"]["srt_url"]
        if srt:
            link = card.locator("a[download]")
            assert link.count() == 1 and srt.split("/")[-1] in (link.get_attribute("href") or "")
        no_scroll(page)
        card.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"captions-episode-{lang}-{size}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()
        api.call("DELETE", f"/api/episodes/{ep}/captions")
        api.put(f"/api/pages/{a['page']}/profiles/visual", {**api.get(f"/api/pages/{a['page']}")["profiles"]["visual"], "caption_style": {"preset": "classic", "mode": "burned", "zone": "auto"}})
