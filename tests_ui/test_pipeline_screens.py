"""Browser checks of the studio-pipeline screens that the review of 0.9.0 looked at: the episode ladder (it was an HTTP 500 as soon as the episode had design sheets), the series
art-style card, the choice-story editor (review line and reader), the character identity panel, the Models page and the style search with the owner's own wording.
Persian (RTL) at desktop and phone width; no console error, no failed request, no horizontal scroll, and no raw English key where a Persian name belongs.

Run:  python -m pytest tests_ui/test_pipeline_screens.py -q   (or against a running app: INSTAI_UI_BASE=http://127.0.0.1:PORT)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import SHOTS, open_page  # noqa: E402
from tests_ui.test_studio_screens import check_shell, exact, stray_persian, tx  # noqa: E402

RAW_ENDINGS = re.compile(r"\b(bad|good|secret|neutral)\s+\d")          # "bad 5": the raw ending keys of the review line
RAW_WORDS = re.compile(r"\b(limbs|outline|stickman_doodle|mono_paper|qwen_image_edit_multiref)\b")


@pytest.fixture(scope="module")
def world(server, seeded):
    """An episode of the seeded anime page with design sheets (the case that crashed the ladder), a choice story from a ready-made template and a locked stick character."""
    api = seeded["api"]
    ep = seeded["anime_whatif"]["episodes"][0]
    page_id = seeded["anime_whatif"]["page"]
    api.wait_job(api.post(f"/api/episodes/{ep}/studio/design/generate", {"language": "en"}))
    assert api.get(f"/api/episodes/{ep}/studio/design-sheets"), "the design sheets exist"
    cs_page = api.post("/api/pages", {"name": "داستان انتخابی نمونه", "format": "choice_story", "languages": ["fa"], "idea": "ایده"})
    story = api.post(f"/api/pages/{cs_page['id']}/choice-stories", {"template": "prison_escape", "title": "فرار از زندان"})
    hero = api.post(f"/api/pages/{page_id}/characters", {"name": "رامین", "role": "hero", "personality": "شجاع"})
    api.post(f"/api/characters/{hero['id']}/identity/stick", {"spec": {"limb_colour": "#e8a22b", "hat": "beanie", "hat_colour": "#e8a22b", "neck": "scarf"}})
    return {"api": api, "episode": ep, "series": seeded["anime_whatif"]["series"], "page": page_id, "story": story["id"], "hero": hero["id"]}


def visit(browser, server, size, path, lang="fa"):
    SHOTS.mkdir(parents=True, exist_ok=True)
    return open_page(browser, server, size, path, lang)


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_episode_ladder_opens_with_design_sheets_and_names_no_raw_key(browser, server, world, size):
    ctx, page, problems = visit(browser, server, size, f"/episodes/{world['episode']}#ladder")
    failures: list[str] = []
    try:
        page.locator(".ladder-stage").first.wait_for(timeout=15000)
        assert page.locator(".ladder-stage").count() == 21, "every stage of the studio ladder is listed"
        design = page.locator(".ladder-stage", has_text="طراحی").first
        assert design.locator(".badge").count() >= 1, "the design stage shows its status"
        main = page.locator("main").inner_text()
        assert "خطای داخلی" not in main, "the ladder is not the red error box"
        if RAW_WORDS.search(main):
            failures.append("raw key on the ladder: " + RAW_WORDS.search(main).group(0))
        page.screenshot(path=str(SHOTS / f"{size}-ladder.png"))
        check_shell(page, "fa", f"episode ladder {size}", failures)
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_series_art_style_card_shows_the_style_name_not_its_keys(browser, server, world, size):
    api = world["api"]
    api.put(f"/api/series/{world['series']}/ladder/art_style", {"data": {"style_key": "stickman_doodle", "realism": "graphic", "theme_key": "mono_paper", "notes": ""}, "note": "ui"})
    ctx, page, problems = visit(browser, server, size, f"/series/{world['series']}#ladder")
    try:
        card = page.locator(".ladder-stage", has_text="سبک هنری").first
        card.wait_for(timeout=15000)
        card.get_by_role("button", name=re.compile("سبک هنری")).first.click()
        line = card.locator("[data-testid=ladder-style-line]")
        line.wait_for(timeout=8000)
        page.wait_for_function("() => { const e = document.querySelector('[data-testid=ladder-style-line]'); return !!e && !/stickman_doodle/.test(e.innerText) && !/…/.test(e.innerText) }", timeout=10000)
        text = line.inner_text()
        assert "stickman_doodle" not in text and "mono_paper" not in text, text
        assert re.search(r"[؀-ۿ]", text), "the style is named in Persian"
        assert not page.locator("main").inner_text().count("graphic |"), "no key list"
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_choice_editor_review_line_names_the_endings_in_persian(browser, server, world, size):
    ctx, page, problems = visit(browser, server, size, f"/choice/{world['story']}")
    try:
        page.get_by_text(re.compile("پایان‌ها")).first.wait_for(timeout=15000)
        main = page.locator("main").inner_text()
        assert not RAW_ENDINGS.search(main), RAW_ENDINGS.search(main).group(0)
        assert re.search(r"پایان‌ها:\s*(بد|خوب|مخفی|خنثی)", main), "the endings line is in Persian"
        check_shell(page, "fa", f"choice editor {size}", [])
        assert not problems, problems
    finally:
        ctx.close()


def test_the_identity_colour_key_names_its_roles_in_persian(browser, server, world):
    ctx, page, problems = visit(browser, server, "desktop", f"/pages/{world['page']}/characters")
    try:
        card = page.locator(".card", has_text="رامین").first
        card.get_by_role("button", name=re.compile("ویرایش")).first.click()          # the identity panel is inside the opened character
        page.get_by_text("کلید رنگ").first.wait_for(timeout=15000)
        main = page.locator("main").inner_text()
        assert not RAW_WORDS.search(main), RAW_WORDS.search(main).group(0)
        assert "دست و پا" in main and "خط دور" in main, "the colour-key roles are named in Persian"
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_models_page_names_the_multi_reference_feature(browser, server, lang):
    ctx, page, problems = visit(browser, server, "desktop", "/models", lang)
    try:
        page.locator("main .card").first.wait_for(timeout=20000)
        main = page.locator("main").inner_text()
        assert "qwen_image_edit_multiref" not in main, "the workflow id is not a title"
        assert tx("mdl.use.qwen_image_edit_multiref", lang) in main
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_style_search_finds_the_owners_own_wording(browser, server, lang):
    ctx, page, problems = visit(browser, server, "desktop", "/library", lang)
    try:
        page.locator(".style-card").first.wait_for(timeout=15000)
        box = page.get_by_role("searchbox").first
        box.fill("Lego-like bricks")
        page.wait_for_timeout(400)
        assert page.locator(".style-card").count() == 1, "exactly the brick style"
        assert "Lego-like bricks" in page.locator(".style-card").first.inner_text(), "its caption is the owner's wording"
        box.fill("")
        assert not problems, problems
    finally:
        ctx.close()
