"""Audit round ia_ui: the everyday screens at 1366 px (a laptop) and 390 px (a phone), in a real browser against the fake services.

* the idea bank and the style library are searchable by a word typed without the half-space; the idea bank pages its cards and has its Chagher / fitness chip;
* the episode page: the state stepper shows the CURRENT step, the video is in the first screen, the version pill covers nothing;
* the wizard's style step and the library load a handful of pictures, not 116; Settings is short and the downloads page asks before a big download;
* the Remotion page: the preview stays in view while a style is picked, every style card has its own picture, the code is fetched only when asked for.
Run:  python -m pytest tests_ui/test_audit_ui.py -q   (INSTAI_UI_BASE=http://127.0.0.1:PORT drives an app that is already running, see tests_ui/conftest.py)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest

VIEWPORTS = {"desktop": {"width": 1366, "height": 850}, "phone": {"width": 390, "height": 780}}
SHOTS = Path(os.environ.get("INSTAI_UI_SHOTS", tempfile.gettempdir())) / "instai-ui-shots"
SIZES = ["desktop", "phone"]
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def visit(browser, base, path, size="desktop", lang="fa", wait="networkidle"):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR" if lang == "fa" else "en-US", has_touch=(size == "phone"))
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); }} catch (e) {{}}")
    page = ctx.new_page()
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text[:300]}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:300]}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "favicon" not in r.url else None)
    page.goto(base + path, wait_until=wait)
    page.wait_for_timeout(500)
    return ctx, page, problems


def num(s: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", (s or "").translate(PERSIAN_DIGITS))]


def shot(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / name))


def no_hscroll(page, where: str) -> None:
    sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert sw <= iw + 1, f"{where}: horizontal scroll ({sw} > {iw})"


# ------------------------------------------------------------------ search without the half-space

@pytest.mark.parametrize("size", SIZES)
def test_idea_search_without_the_half_space_finds_the_category(browser, server, size):
    ctx, page, problems = visit(browser, server, "/ideas", size)
    try:
        box = page.locator("#idea-q")
        shown = lambda: num(page.locator("p[aria-live=polite]").first.inner_text())[0]   # «n ایده از total»  # noqa: E731
        box.fill("روانشناسی")
        page.wait_for_timeout(300)
        compact = shown()
        box.fill("روان‌شناسی")
        page.wait_for_timeout(300)
        spaced = shown()
        assert compact >= 15 and compact == spaced, (compact, spaced)
        box.fill("اقتصاد")
        page.wait_for_timeout(300)
        assert shown() >= 15, "the category's own name finds its ideas"
        box.fill("ورزش")
        page.wait_for_timeout(300)
        assert shown() >= 1, "the Persian name of a tag finds its ideas"
        box.fill("zzzzqqq")
        page.wait_for_timeout(300)
        assert shown() == 0 and page.locator("[data-testid=idea-grid] article").count() == 0
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_style_search_without_the_half_space(browser, server, size):
    ctx, page, problems = visit(browser, server, "/library", size)
    try:
        page.wait_for_selector("[data-testid=style-gallery] .style-card", timeout=20000)
        box = page.locator("input[type=search]").first
        box.fill("واقع‌گرا")
        page.wait_for_timeout(300)
        spaced = page.locator("[data-testid=style-gallery] .style-card").count()
        box.fill("واقعگرا")
        page.wait_for_timeout(300)
        compact = page.locator("[data-testid=style-gallery] .style-card").count()
        assert spaced >= 1 and compact >= spaced, (spaced, compact)
        assert problems == [] or all("favicon" in p for p in problems), problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ the idea bank pages its cards

@pytest.mark.parametrize("size", SIZES)
def test_idea_bank_shows_a_page_of_cards_and_the_chagher_chip(browser, server, size):
    ctx, page, problems = visit(browser, server, "/ideas", size)
    try:
        grid = page.locator("[data-testid=idea-grid] article")
        grid.first.wait_for(timeout=20000)
        assert grid.count() == 24, grid.count()
        height = page.evaluate("document.documentElement.scrollHeight")
        assert height < (7500 if size == "desktop" else 14000), height       # it was 24 000 px (desktop) / 60 000 px (phone) with all 121 cards
        more = page.locator("[data-testid=ideas-more]")
        assert more.count() == 1
        more.click()
        page.wait_for_timeout(200)
        assert grid.count() == 48
        # the Chagher / fitness ideas are a chip of their own
        chip = page.locator("[data-testid=idea-collection-chagher]")
        assert "چغر" in chip.inner_text() and num(chip.inner_text())[0] >= 9
        chip.click()
        page.wait_for_timeout(300)
        assert grid.count() == num(chip.inner_text())[0] and page.locator("[data-testid=ideas-more]").count() == 0
        page.get_by_role("button", name="پاک کردن فیلترها").click() if page.get_by_role("button", name="پاک کردن فیلترها").count() else None
        # every tag is reachable (the list used to be cut after 18 of 40), inside a box that scrolls
        tags = page.locator(".tag-chips .filter-chip")
        assert tags.count() >= 30, tags.count()
        assert page.evaluate("(() => { const e = document.querySelector('.tag-chips'); return e.scrollHeight > e.clientHeight })()"), "the tag list scrolls inside its box"
        no_hscroll(page, "ideas")
        shot(page, f"audit-ideas-{size}.png")
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ the episode page

def _episode(seeded, n=0):
    return seeded["anime_whatif"]["episodes"][n]


@pytest.mark.parametrize("size", SIZES)
def test_the_stepper_shows_the_current_step_and_says_where_we_are(browser, server, seeded, size):
    for n in (0, 1):
        ctx, page, problems = visit(browser, server, f"/episodes/{_episode(seeded, n)}", size)
        try:
            page.wait_for_selector("[data-testid=state-stepper]", timeout=20000)
            page.wait_for_timeout(500)
            cur = page.locator(".state-steps [aria-current=step]")
            assert cur.count() == 1
            ol = page.locator(".state-steps").bounding_box()
            box = cur.bounding_box()
            assert box["x"] >= ol["x"] - 1 and box["x"] + box["width"] <= ol["x"] + ol["width"] + 1, f"episode {n}: the current step is clipped {box} in {ol}"
            summary = page.locator("[data-testid=state-summary]").inner_text()
            assert re.search(r"مرحله", summary) and len(num(summary)) >= 2 and cur.inner_text().strip().split(" — ")[0] in summary, summary
            no_hscroll(page, "episode")
            shot(page, f"audit-episode-stepper-{n}-{size}.png")
        finally:
            ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_the_video_is_in_the_first_screen_with_the_approve_button(browser, server, seeded, size):
    ep = _episode(seeded)
    detail = seeded["api"].get(f"/api/episodes/{ep}")
    if not detail["videos"] or detail["state"] not in ("quality_review", "ready_for_approval"):
        pytest.skip("no ffmpeg on this machine: no video was rendered")
    ctx, page, problems = visit(browser, server, f"/episodes/{ep}", size)
    try:
        video = page.locator("video").first
        video.wait_for(timeout=20000)
        vh = VIEWPORTS[size]["height"]
        box = video.bounding_box()
        assert box["y"] < vh * 0.62, f"the video starts at y={box['y']} of a {vh} px screen (it was at 1987 / 2683 px)"
        # the card with the player comes before the summary and the row of steps
        order = page.evaluate("""() => { const y = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().top + scrollY : null; };
                                         return {next: y('[data-testid=next-review]'), summary: y('[data-testid=fold-summary]'), steps: y('[data-testid=state-stepper]')}; }""")
        assert order["next"] < order["steps"] and (order["summary"] is None or order["next"] < order["summary"]), order
        assert page.locator("[data-testid=fold-summary]").evaluate("e => e.open") is (size == "desktop"), "the episode summary is folded on a phone only"
        review = page.locator("[data-testid=next-review]")
        assert review.count() == 1 and review.locator("video").count() == 1
        assert review.get_by_role("button", name=re.compile("تأیید")).count() >= 1, "the approve button is next to the player"
        assert review.locator("[data-testid=qc-summary]").count() == 1
        # only ONE player on the production tab's top: the versions card has the facts, not a second player
        page.goto(page.url.split("#")[0] + "#production", wait_until="networkidle")
        page.wait_for_timeout(500)
        assert page.locator("video").count() == 1, "one player on the page, not two"
        assert page.locator("[data-testid=fold-estimate]").evaluate("e => e.open") is False
        assert page.locator("[data-testid=fold-jobs]").evaluate("e => e.open") is False
        no_hscroll(page, "episode production")
        shot(page, f"audit-episode-video-{size}.png")
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_the_version_pill_covers_nothing_on_any_screen(browser, server, seeded, size):
    paths = ["/", "/pages", "/ideas", "/library", "/settings", f"/episodes/{_episode(seeded)}", "/remotion"]
    for path in paths:
        ctx, page, problems = visit(browser, server, path, size)
        try:
            badge = page.locator("[data-testid=version-badge]")
            assert badge.count() == 1, path
            assert page.evaluate("b => getComputedStyle(b).position", badge.element_handle()) != "fixed", "in the normal flow, not over the page"
            assert badge.evaluate("b => !!b.closest('header.topbar')"), "in the top bar"
            vb = badge.bounding_box()
            assert vb and vb["x"] >= 0 and vb["x"] + vb["width"] <= VIEWPORTS[size]["width"] + 1, (path, vb)
            hit = page.evaluate("""(b) => {
                const r = b.getBoundingClientRect(); const out = [];
                for (const e of document.querySelectorAll('button, a, input, select, textarea, [role=button]')) {
                  if (e === b || b.contains(e)) continue;
                  const q = e.getBoundingClientRect();
                  if (q.width && q.height && q.left < r.right && q.right > r.left && q.top < r.bottom && q.bottom > r.top) out.push((e.innerText || e.getAttribute('aria-label') || e.tagName).slice(0, 30));
                }
                return out; }""", badge.element_handle())
            assert hit == [], f"{path}: the version pill overlaps {hit}"
            no_hscroll(page, path)
        finally:
            ctx.close()


# ------------------------------------------------------------------ the style pictures

def _wizard_to_style_step(page):
    page.get_by_label(re.compile("^نام صفحه")).first.fill("صفحهٔ آزمون")
    for _ in range(2):
        page.get_by_role("button", name="بعدی", exact=True).click()
        page.wait_for_timeout(300)
    page.wait_for_selector("[data-testid=style-suggestions]", timeout=20000)


@pytest.mark.parametrize("size", SIZES)
def test_wizard_style_step_is_short_and_loads_few_pictures(browser, server, size):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR", has_touch=(size == "phone"))
    ctx.add_init_script("try { localStorage.setItem('instai.lang', 'fa'); } catch (e) {}")
    page = ctx.new_page()
    pics: list[str] = []
    page.on("request", lambda r: pics.append(r.url) if r.resource_type == "image" and "/api/" in r.url else None)
    try:
        page.goto(server + "/pages/new", wait_until="networkidle")
        _wizard_to_style_step(page)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        assert page.locator("[data-testid=style-suggestions] .style-card").count() == 6
        assert len(pics) <= 14, f"{len(pics)} pictures on the first paint of the style step"
        height = page.evaluate("document.documentElement.scrollHeight")
        assert height < (3200 if size == "desktop" else 5200), height           # 6998 px desktop / 14 792 px phone with the whole gallery
        nxt = page.get_by_role("button", name="بعدی", exact=True).bounding_box()
        assert nxt["y"] < VIEWPORTS[size]["height"], f"the «بعدی» button is at y={nxt['y']}"
        no_hscroll(page, "wizard style step")
        shot(page, f"audit-wizard-style-{size}.png")
        # the whole gallery on demand: inside a box that scrolls, pictures only for what is in view
        before = len(pics)
        page.locator("[data-testid=style-show-all]").click()
        page.wait_for_selector("[data-testid=style-gallery] .style-card", timeout=10000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(600)
        assert page.locator("[data-testid=style-gallery] .style-card").count() >= 100
        assert len(pics) - before <= 40, f"{len(pics) - before} more pictures for the opened gallery"
        assert page.evaluate("(() => { const e = document.querySelector('[data-testid=style-gallery]'); return e.scrollHeight > e.clientHeight + 100 })()"), "the gallery scrolls in its own box"
        page.locator("input[name$='-style']").nth(30).check(force=True)      # a pick from the long list works
        page.get_by_role("button", name="فقط پیشنهادها").click()
        assert page.locator("[data-testid=style-suggestions] .style-card.selected").count() == 1, "the chosen look stays in view in the short list"
    finally:
        ctx.close()


@pytest.mark.parametrize("size", SIZES)
def test_library_loads_a_page_of_pictures_not_all(browser, server, size):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR", has_touch=(size == "phone"))
    ctx.add_init_script("try { localStorage.setItem('instai.lang', 'fa'); } catch (e) {}")
    page = ctx.new_page()
    pics: list[str] = []
    page.on("request", lambda r: pics.append(r.url) if r.resource_type == "image" and "/api/" in r.url else None)
    try:
        page.goto(server + "/library", wait_until="networkidle")
        page.wait_for_selector("[data-testid=style-gallery] .style-card", timeout=20000)
        page.wait_for_timeout(800)
        cards = page.locator("[data-testid=style-gallery] .style-card")
        assert cards.count() == 36, cards.count()
        assert len(pics) <= 36, f"{len(pics)} pictures on the first paint of the library (it asked for 116)"
        page.locator("[data-testid=styles-more]").click()
        page.wait_for_timeout(300)
        assert cards.count() == 72
        height = page.evaluate("document.documentElement.scrollHeight")
        assert height > 0
        no_hscroll(page, "library")
    finally:
        ctx.close()


# ------------------------------------------------------------------ settings, downloads, models

@pytest.mark.parametrize("size", SIZES)
def test_settings_keeps_the_settings_and_links_to_the_catalogue(browser, server, size):
    ctx, page, problems = visit(browser, server, "/settings", size)
    try:
        height = page.evaluate("document.documentElement.scrollHeight")
        assert height < (5000 if size == "desktop" else 9000), height          # 14 876 px (desktop) / 38 000 px (phone) with the catalogue of 22 packages
        text = page.locator("main").inner_text()
        assert len(text) < 9000, len(text)
        assert page.locator("main a[href='/downloads']").count() >= 1 and page.locator("main a[href='/models']").count() >= 1
        assert page.locator("main").get_by_role("button", name="نصب").count() == 0, "no install button on the settings page"
        assert page.get_by_role("button", name="ذخیره").count() >= 1, "the save button is still there"
        no_hscroll(page, "settings")
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


def test_models_page_holds_the_licences_and_loads_them_when_opened(browser, server):
    ctx, page, problems = visit(browser, server, "/models", "desktop")
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url) if r.url.rstrip("/").endswith("/api/models") else None)
    try:
        fold = page.locator("[data-testid=fold-licences]")
        fold.wait_for(timeout=30000)
        assert asked == [], "the licence list is not fetched until it is opened"
        fold.locator("summary").click()
        page.wait_for_selector("[data-testid=fold-licences] .card.flat", timeout=60000)
        text = fold.inner_text()
        assert "VRAM" in text and "مجوز" in text
        badges = " ".join(fold.locator(".badge").all_inner_texts())
        assert "EXCLUDED" not in badges and "OWNER DECISION" not in badges and re.search(r"[؀-ۿ]", badges), "Persian badges only"
        assert len(asked) == 1
    finally:
        ctx.close()


def test_a_big_download_asks_first_and_one_that_does_not_fit_is_blocked(browser, server):
    GB = 1024 ** 3
    ctx = browser.new_context(viewport=VIEWPORTS["desktop"], locale="fa-IR")
    ctx.add_init_script("try { localStorage.setItem('instai.lang', 'fa'); } catch (e) {}")
    page = ctx.new_page()
    posted: list[str] = []
    state = {"free": 500 * GB}

    def catalog(route):
        resp = route.fetch()
        body = resp.json()
        body.update(free_bytes=state["free"], free_gb=round(state["free"] / GB, 1), big_bytes=2 * GB, spare_bytes=2 * GB)
        route.fulfill(response=resp, body=json.dumps(body))

    page.route("**/api/downloads/catalog", catalog)
    page.on("request", lambda r: posted.append(r.url) if r.method == "POST" and r.url.endswith("/api/downloads") else None)
    try:
        page.goto(server + "/downloads", wait_until="networkidle")
        page.wait_for_selector("[data-testid=curated-list]", timeout=30000)
        assert "جای آزاد دیسک" in page.locator("[data-testid=disk-free]").first.inner_text()
        big = page.evaluate("() => fetch('/api/downloads/catalog').then(r => r.json()).then(c => (c.curated || []).filter(p => !p.complete && p.commercial === 'yes').sort((a, b) => b.missing_size - a.missing_size)[0]?.id)")
        assert big, "a commercial curated package that is not installed"
        page.locator(f"[data-testid=cur-{big}]").get_by_role("checkbox").check()
        page.locator("[data-testid=cur-go]").click()
        dlg = page.get_by_role("dialog")
        dlg.wait_for(timeout=5000)
        assert "شروع شود" in dlg.inner_text() and "جای آزاد" in dlg.inner_text()
        dlg.get_by_role("button", name="انصراف").click()
        page.wait_for_timeout(300)
        assert posted == [], "nothing was queued without the owner's «yes»"
        # it does not fit: the button is off and the reason is written
        state["free"] = 3 * GB
        page.reload(wait_until="networkidle")
        page.wait_for_selector("[data-testid=curated-list]", timeout=30000)
        page.locator(f"[data-testid=cur-{big}]").get_by_role("checkbox").check()
        assert page.locator("[data-testid=cur-go]").is_disabled()
        assert "جای آزاد دیسک کافی نیست" in page.locator("main").inner_text()
        assert posted == []
    finally:
        ctx.close()


# ------------------------------------------------------------------ the Remotion page

@pytest.mark.parametrize("size", SIZES)
def test_remotion_preview_stays_in_view_while_a_style_is_picked(browser, server, size):
    ctx = browser.new_context(viewport={"width": VIEWPORTS[size]["width"], "height": 900 if size == "desktop" else 780}, locale="fa-IR", has_touch=(size == "phone"))
    ctx.add_init_script("try { localStorage.setItem('instai.lang', 'fa'); localStorage.removeItem('instai.rm.tab'); } catch (e) {}")
    page = ctx.new_page()
    asked: list[str] = []
    page.on("request", lambda r: asked.append(r.url.split("/api/")[-1]) if "/api/remotion/" in r.url else None)
    problems: list[str] = []
    page.on("pageerror", lambda e: problems.append(str(e)[:300]))
    try:
        page.goto(server + "/remotion", wait_until="networkidle")
        page.wait_for_selector("[data-testid=rm-player]", timeout=30000)
        page.wait_for_selector("[data-testid^=rm-style-]", timeout=30000)
        assert not any(a.startswith("remotion/code") for a in asked), f"the code is fetched with the page: {asked}"
        vh = page.evaluate("window.innerHeight")
        # pick a style far down the list: the card scrolls into view in its box and the preview is still on screen
        names = page.eval_on_selector_all("[data-testid^=rm-style-]", "els => els.map(e => e.getAttribute('data-testid'))")
        assert len(names) >= 100
        card = page.locator(f"[data-testid={names[60]}]")
        card.scroll_into_view_if_needed()
        card.click()
        page.wait_for_timeout(500)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(300)
        box = page.locator("[data-testid=rm-player]").bounding_box()
        assert box and box["y"] >= -1 and box["y"] + box["height"] <= vh + 1, f"the preview is out of view: {box} in a {vh} px screen"
        assert page.locator("[data-testid=rm-chosen]").inner_text().strip().endswith(page.locator(f"[data-testid={names[60]}] .strong").inner_text().strip())
        # every card has its own picture (made when the card comes near the screen)
        page.wait_for_timeout(800)
        with_pic = page.eval_on_selector_all(".rm-kit .rm-thumb", "els => els.filter(e => e.querySelector(':scope > div, :scope > svg, :scope > img, :scope > canvas')).length")
        assert with_pic >= 4, f"{with_pic} style cards drew their picture"
        no_hscroll(page, "remotion")
        shot(page, f"audit-remotion-{size}.png")
        # the code tab asks for the code when it is opened
        page.get_by_role("tab", name=re.compile("کد")).click()
        page.wait_for_selector("[data-testid=rm-code] pre", timeout=15000)
        assert any(a.startswith("remotion/code") for a in asked)
        assert problems == [], problems
    finally:
        ctx.close()
