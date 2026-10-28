"""The studio screens in Persian (RTL) AND English (LTR), at desktop and phone width: style / theme / template library, wizard look step, the development
room (What-If: source search -> canon research -> brainstorm -> map -> bible), the episode Studio tab (animatic, design sheets, casting, gate) and the
per-page text-model card. Texts are looked up in the real dictionaries, so a renamed string does not break the tests."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_i18n import texts  # noqa: E402
from tests_ui.test_screens import PERSIAN, SHOTS, VIEWPORTS, open_page  # noqa: E402

FA, EN = texts()


def tx(key: str, lang: str, **params) -> str:
    s = (FA if lang == "fa" else EN)[key]
    for k, v in params.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def stray_persian(text: str) -> str | None:
    """A Persian letter in English text, ignoring the language's own name ("فارسی" in a language picker is correct)."""
    clean = text.replace("فارسی", "")
    m = PERSIAN.search(clean)
    return " ".join(clean[max(0, m.start() - 25): m.end() + 25].split()) if m else None


def exact(text: str):
    return re.compile("^" + re.escape(text) + "$")


def check_shell(page, lang: str, name: str, failures: list[str]) -> None:
    html = page.locator("html")
    want_dir = "rtl" if lang == "fa" else "ltr"
    if html.get_attribute("dir") != want_dir or not (html.get_attribute("lang") or "").startswith(lang):
        failures.append(f"{name}: html dir/lang = {html.get_attribute('dir')}/{html.get_attribute('lang')}")
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    if sw > iw + 1:
        failures.append(f"{name}: horizontal scroll ({sw} > {iw})")
    if page.locator("main").count() == 0:
        failures.append(f"{name}: no <main> landmark")
    if page.locator("text=Something went wrong").count():
        failures.append(f"{name}: error boundary shown")


@pytest.fixture(scope="session")
def studio_seed(server):
    """English-named pages so the English screens can be checked for stray Persian text."""
    from tests_ui.conftest import Api

    api = Api(server)
    out = {"api": api}
    page = api.post("/api/pages", {"name": "Studio What-If", "format": "anime_whatif", "languages": ["en"], "idea": "what if", "automation_level": "manual"})
    s = api.post(f"/api/pages/{page['id']}/series", {"title": "What if Arta stayed home", "target_episodes": 3})
    out["whatif"] = {"page": page["id"], "series": s["id"]}
    page2 = api.post("/api/pages", {"name": "Studio Cat", "format": "recurring_character", "languages": ["en"], "idea": "cat", "automation_level": "manual",
                                    "profiles": {"production": {"studio_mode": True, "episode_length_sec": 20}}})
    api.post(f"/api/pages/{page2['id']}/characters", {"name": "Mimi", "role": "hero", "personality": "playful"})
    s2 = api.post(f"/api/pages/{page2['id']}/series", {"title": "Mimi at home", "target_episodes": 2})
    plan = api.wait_job(api.post(f"/api/series/{s2['id']}/plan", {"episodes_count": 2}))["result"]["plan"]
    eps = api.post(f"/api/series/{s2['id']}/apply-plan", {"plan": plan})["episodes"]
    ep = eps[0]["id"]
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-script"))
    r = api.post(f"/api/episodes/{ep}/approve-script")
    api.wait_job(r["job"])
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-storyboard"))
    out["cat"] = {"page": page2["id"], "series": s2["id"], "episode": ep}
    return out


# ------------------------------------------------------------------ library
@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_library_gallery_filters_duplicate_and_tabs(browser, server, size, lang):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_page(browser, server, size, "/library", lang)
    failures: list[str] = []
    try:
        page.locator(".style-card").first.wait_for(timeout=15000)
        n = page.locator(".style-card").count()
        assert n >= 40, f"{n} style cards"
        chips = page.locator(".filter-chip")
        assert chips.count() == 9, "all + 8 realism levels"
        chips.nth(4).click()  # one realism level
        page.wait_for_timeout(200)
        n2 = page.locator(".style-card").count()
        assert 0 < n2 < n, "the filter narrows the gallery"
        page.locator(".style-card").first.click()
        page.get_by_role("button", name=exact(tx("lib.duplicate", lang))).wait_for(timeout=5000)
        page.get_by_role("button", name=exact(tx("lib.duplicate", lang))).click()
        page.locator(".style-card .badge", has_text=tx("lib.mine", lang)).first.wait_for(timeout=10000)
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-library.png"))
        main = page.locator("main").inner_text()
        if lang == "en" and stray_persian(main):
            failures.append("library (en): stray Persian text: " + stray_persian(main))
        if lang == "fa" and not PERSIAN.search(main):
            failures.append("library (fa): no Persian text")
        check_shell(page, lang, f"library {size} {lang}", failures)
        page.get_by_role("tab", name=exact(tx("lib.tab_themes", lang))).click()
        page.wait_for_timeout(200)
        assert page.locator(".theme-card").count() >= 16
        page.get_by_role("tab", name=exact(tx("lib.tab_templates", lang))).click()
        page.wait_for_timeout(300)
        assert page.locator("main .card").count() >= 4, "the four built-in templates are listed"
        main = page.locator("main").inner_text()
        if lang == "en" and stray_persian(main):
            failures.append("templates (en): stray Persian text")
        check_shell(page, lang, f"library tabs {size} {lang}", failures)
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_new_style_editor_saves_a_user_style(browser, server, lang):
    from tests_ui.conftest import Api

    ctx, page, problems = open_page(browser, server, "desktop", "/library", lang)
    try:
        page.locator(".style-card").first.wait_for(timeout=15000)
        page.get_by_role("button", name=exact(tx("lib.new_style", lang))).click()
        page.get_by_label(re.compile("^" + re.escape(tx("lib.name_en", lang)))).fill(f"UI made style {lang}")
        page.get_by_label(re.compile("^" + re.escape(tx("lib.image_pos", lang)))).fill("ui test prompt, soft light")
        page.get_by_role("button", name=exact(tx("common.save", lang))).click()
        page.wait_for_function(f"document.body.innerText.includes('UI made style {lang}')", timeout=10000)
        names = [s["name_en"] for s in Api(server).get("/api/library")["styles"]]
        assert f"UI made style {lang}" in names
        assert not problems, problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ wizard
@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_wizard_template_and_look_steps(browser, server, size, lang):
    ctx, page, problems = open_page(browser, server, size, "/pages/new", lang)
    failures: list[str] = []
    try:
        assert page.locator(".choice-grid .choice").count() >= 4, "templates are the first choice"
        nxt = page.get_by_role("button", name=exact(tx("common.next", lang)))
        page.get_by_label(re.compile("^" + re.escape(tx("wiz.name", lang)))).first.fill("x")
        nxt.click()  # -> languages
        page.wait_for_timeout(200)
        both = page.get_by_label("English").first
        assert both.count() >= 0
        nxt.click()  # -> look
        page.locator(".style-card").first.wait_for(timeout=15000)
        assert page.locator(".style-card").count() >= 40 and page.locator(".theme-card").count() >= 16
        page.locator(".style-card").nth(5).click()
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-wizard-look.png"))
        check_shell(page, lang, f"wizard look {size} {lang}", failures)
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ development room
def step_button(page, lang: str, key: str):
    return page.locator(".dev-step", has_text=tx(key, lang))


@pytest.mark.parametrize("size", ["desktop", "phone"])
@pytest.mark.parametrize("lang", ["fa", "en"])
def test_development_room_renders_and_is_bilingual(browser, server, studio_seed, size, lang):
    sid = studio_seed["whatif"]["series"]
    ctx, page, problems = open_page(browser, server, size, f"/series/{sid}", lang)
    failures: list[str] = []
    try:
        page.locator(".dev-stepper").wait_for(timeout=15000)
        assert page.locator(".dev-step").count() == 8, "What-If has eight steps"
        stepper = page.locator(".dev-stepper").inner_text()
        if lang == "en" and stray_persian(stepper):
            failures.append("stepper (en) has Persian text")
        if lang == "fa" and not PERSIAN.search(stepper):
            failures.append("stepper (fa) has no Persian text")
        heading = page.locator("#dev-step-h").inner_text()
        assert heading, "the first open step is shown"
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-develop.png"))
        check_shell(page, lang, f"develop {size} {lang}", failures)
        assert not failures, failures
        assert not problems, problems
    finally:
        ctx.close()


def test_development_room_whatif_flow_in_english(browser, server, studio_seed):
    """Source search -> choose -> canon research -> brainstorm -> approve -> consequence map -> bible, all by clicking, in English."""
    from tests_ui.conftest import Api

    lang = "en"
    sid = studio_seed["whatif"]["series"]
    ctx, page, problems = open_page(browser, server, "desktop", f"/series/{sid}", lang)
    try:
        page.locator(".dev-stepper").wait_for(timeout=15000)
        # 1. source
        page.get_by_label(re.compile("^" + re.escape(tx("src.query", lang)))).fill("Sample")
        page.get_by_role("button", name=exact(tx("src.search", lang))).click()
        page.locator(".cand").first.wait_for(timeout=60000)
        page.get_by_role("button", name=exact(tx("src.use", lang))).first.click()
        page.locator(".card-head h2", has_text=tx("src.chosen", lang)).wait_for(timeout=15000)
        page.get_by_role("button", name=exact(tx("dev.approve_step", lang))).click()
        page.wait_for_function("document.querySelector('.dev-step.st-done') !== null", timeout=15000)
        # 2. canon research
        step_button(page, lang, "dev.status_todo").first.wait_for(timeout=5000)
        page.locator(".dev-step").nth(1).click()
        page.get_by_role("button", name=exact(tx("res.run", lang))).click()
        page.get_by_text(tx("res.canon_doc", lang), exact=True).wait_for(timeout=90000)
        # 3. brainstorm: AI cards, then approve one, then add one of my own
        page.locator(".dev-step").nth(2).click()
        page.get_by_role("button", name=exact(tx("idea.generate", lang))).click()
        page.locator("article.idea").first.wait_for(timeout=90000)
        assert page.locator("article.idea").count() == 6
        page.locator("article.idea").first.get_by_role("button", name=exact(tx("idea.approve", lang))).click()
        page.locator("article.idea.approved").first.wait_for(timeout=10000)
        page.get_by_role("button", name=re.compile("^" + re.escape(tx("idea.add_mine", lang)))).click()
        page.get_by_label(re.compile("^" + re.escape(tx("idea.title", lang)))).first.fill("My own twist")
        page.get_by_role("button", name=exact(tx("common.add", lang))).click()
        page.locator("article.idea", has_text="My own twist").first.wait_for(timeout=10000)
        page.get_by_role("button", name=exact(tx("dev.approve_step", lang))).click()
        # 4. consequence map
        page.locator(".dev-step").nth(3).click()
        page.get_by_role("button", name=exact(tx("map.generate", lang))).click()
        page.locator(".map-node").first.wait_for(timeout=90000)
        assert page.locator(".map-node").count() >= 6
        # 5. bible
        page.locator(".dev-step").nth(5).click()
        page.get_by_role("button", name=exact(tx("bible.generate", lang))).click()
        page.get_by_label(re.compile("^" + re.escape(tx("bible.premise", lang)))).wait_for(timeout=90000)
        page.wait_for_function("document.querySelector('textarea[id]') !== null")
        page.get_by_role("button", name=exact(tx("bible.approve", lang))).click()
        page.get_by_text(tx("bible.approved_note", lang)).wait_for(timeout=15000)
        page.screenshot(path=str(SHOTS / "desktop-en-develop-bible.png"))
        api = Api(server)
        d = api.get(f"/api/series/{sid}/development")
        done = {x["key"]: x["status"] for x in d["steps"]}
        assert done["source"] == "done" and done["divergence"] == "done" and d["bible"]["status"] == "approved"
        assert d["source"]["provider"] == "fake" and d["research"]["canon"]["content"]["characters"] and len(d["steps"][3]["data"]["nodes"]) >= 6
        assert not problems, problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ episode studio tab
@pytest.mark.parametrize("size", ["desktop", "phone"])
@pytest.mark.parametrize("lang", ["fa", "en"])
def test_episode_studio_tab(browser, server, studio_seed, size, lang):
    from tests_ui.conftest import Api

    ep = studio_seed["cat"]["episode"]
    ctx, page, problems = open_page(browser, server, size, f"/episodes/{ep}#studio", lang)
    failures: list[str] = []
    try:
        page.locator(".stage-board").wait_for(timeout=15000)
        assert page.locator(".stage-board .stage").count() == 6
        page.screenshot(path=str(SHOTS / f"{size}-{lang}-studio.png"))
        main = page.locator("main").inner_text()
        if lang == "en" and stray_persian(main):
            failures.append("studio (en): stray Persian text: " + stray_persian(main))
        check_shell(page, lang, f"studio {size} {lang}", failures)
        assert not failures, failures
        assert not problems, problems
        if size == "phone":
            return
        api = Api(server)
        # design sheets and casting by clicking (fake providers)
        page.get_by_role("button", name=re.compile("^(" + re.escape(tx("design.generate", lang)) + "|" + re.escape(tx("design.regenerate", lang)) + ")$")).click()
        page.locator("article.sheet").first.wait_for(timeout=60000)
        assert page.locator("article.sheet").count() >= 3
        page.get_by_role("button", name=exact(tx("cast.suggest", lang))).click()
        page.locator(".cast-row .badge", has_text=tx("cast.set", lang)).first.wait_for(timeout=60000)
        if api.get("/api/health")["ffmpeg"]:
            page.get_by_role("button", name=re.compile("^(" + re.escape(tx("animatic.build", lang)) + "|" + re.escape(tx("animatic.rebuild", lang)) + ")$")).click()
            page.locator("video.animatic-video").wait_for(timeout=120000)
        st = api.get(f"/api/episodes/{ep}/studio")
        assert len(st["design_sheets"]) >= 3 and all(c["has_voice"] for c in st["casting"])
        assert not problems, problems
    finally:
        ctx.close()


def test_page_text_model_card_saves_a_choice(browser, server, studio_seed):
    from tests_ui.conftest import Api

    lang = "en"
    pid = studio_seed["whatif"]["page"]
    ctx, page, problems = open_page(browser, server, "desktop", f"/pages/{pid}/settings", lang)
    try:
        page.get_by_role("button", name=exact(tx("prof.kind_production", lang))).click()
        page.get_by_text(tx("llm.title", lang), exact=True).wait_for(timeout=10000)
        sel = page.get_by_label(exact(tx("llm.group.brainstorm", lang)))
        sel.select_option("fake")
        page.get_by_role("button", name=re.compile("^" + re.escape(tx("common.save", lang)))).first.click()
        page.wait_for_timeout(800)
        prof = Api(server).get(f"/api/pages/{pid}")["profiles"]["production"]
        assert prof["llm"]["groups"]["brainstorm"]["provider"] == "fake"
        assert not problems, problems
    finally:
        ctx.close()
