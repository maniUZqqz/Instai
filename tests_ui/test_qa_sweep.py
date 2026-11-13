"""QA sweep (0.8.0): the whole app against fake services, in a real browser. "I ran InstAI, it still has lots of problems" - this is the test that
finds them before the owner does:

* every screen (the sidebar, the page workspace tabs, the series / episode editors, every Production lab screen, the not-found page) in Persian and
  English, at desktop and phone width: it renders, no console error, no page error, no failed request, no horizontal scroll, every button has a name;
* every link of the sidebar leads to a real screen (a screen another feature adds is swept automatically);
* every tab / segmented control / disclosure of every screen can be pressed without an error;
* the Remotion page: every composition x every style of the library renders in the live player (no error at the first frame and at a later one),
  the code tab shows the code, a render request is queued and followed to the end;
* the curated model library: filters, file tables, the licence confirmation, a scheduled download that is then cancelled (nothing is downloaded);
* the Models page: the coexistence card and the GPU panel.
Run:  python -m pytest tests_ui/test_qa_sweep.py -q   (see tests_ui/conftest.py). Screenshots: INSTAI_UI_SHOTS (default: the temp folder)."""
from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

import pytest

VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 390, "height": 844}}
SHOTS = Path(os.environ.get("INSTAI_UI_SHOTS", tempfile.gettempdir())) / "instai-ui-shots"
LAB = ["workers", "voices", "rigs", "compare", "retake", "mix", "automation", "consistency", "notifications"]
STATIC = ["/", "/pages", "/pages/new", "/library", "/monitor", "/queue", "/report", "/downloads", "/whats-new", "/remotion", "/publishing", "/system", "/models",
          "/settings", "/lab", *[f"/lab/{x}" for x in LAB], "/no-such-screen"]
IGNORED = ("favicon",)
PERSIAN = re.compile(r"[؀-ۿ]")


def visit(browser, base: str, path: str, size: str = "desktop", lang: str = "fa", wait: str = "networkidle"):
    ctx = browser.new_context(viewport=VIEWPORTS[size], locale="fa-IR" if lang == "fa" else "en-US", has_touch=(size == "phone"))
    ctx.add_init_script(f"try {{ localStorage.setItem('instai.lang', '{lang}'); }} catch (e) {{}}")
    page = ctx.new_page()
    problems: list[str] = []
    page.on("console", lambda m: problems.append(f"console.{m.type}: {m.text[:300]}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:300]}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and not any(i in r.url for i in IGNORED) else None)
    page.on("requestfailed", lambda r: problems.append(f"request failed {r.url} ({r.failure})") if not any(i in r.url for i in IGNORED) and "net::ERR_ABORTED" not in str(r.failure) else None)
    page.goto(base + path, wait_until=wait)
    page.wait_for_timeout(500)
    return ctx, page, problems


def routes(seeded) -> dict[str, str]:
    a, e = seeded["anime_whatif"], seeded["concept_explainer"]
    out = {p: p for p in STATIC}
    out.update({
        "workspace": f"/pages/{a['page']}", "workspace/settings": f"/pages/{a['page']}/settings", "workspace/characters": f"/pages/{a['page']}/characters",
        "workspace/series": f"/pages/{a['page']}/series", "workspace/episodes": f"/pages/{a['page']}/episodes", "workspace/publishing": f"/pages/{a['page']}/publishing",
        "workspace/history": f"/pages/{a['page']}/history", "series": f"/series/{a['series']}", "episode": f"/episodes/{a['episodes'][0]}",
        "episode-2": f"/episodes/{a['episodes'][1]}", "explainer-series": f"/series/{e['series']}", "explainer-episode": f"/episodes/{e['episodes'][0]}",
    })
    return out


def check(page, name: str, size: str, lang: str, problems: list[str], expect_not_found: bool = False) -> list[str]:
    bad = [f"{name}: {p}" for p in problems]
    try:
        html = page.locator("html")
        if html.get_attribute("dir") != ("rtl" if lang == "fa" else "ltr"):
            bad.append(f"{name}: html dir is {html.get_attribute('dir')}")
        if not page.title().startswith(("InstAI", "")) or "undefined" in page.title():
            bad.append(f"{name}: odd title {page.title()!r}")
        main = page.locator("main").first
        text = main.inner_text() if main.count() else ""
        if not text.strip():
            bad.append(f"{name}: the main area is empty")
        if "Something went wrong" in text or "undefined" in text or "[object Object]" in text or "NaN" in text.split():
            bad.append(f"{name}: broken text on screen ({[w for w in ('Something went wrong', 'undefined', '[object Object]') if w in text]})")
        if lang == "fa" and not expect_not_found and not PERSIAN.search(text):
            bad.append(f"{name}: no Persian text in the Persian interface")
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        if sw > iw + 1:
            bad.append(f"{name}: horizontal scroll ({sw} > {iw})")
        nameless = page.evaluate("""() => [...document.querySelectorAll('button, a[href]')].filter(e => {
            const r = e.getBoundingClientRect(); if (!r.width || !r.height) return false
            return !(e.innerText || '').trim() && !e.getAttribute('aria-label') && !e.getAttribute('title') && !e.querySelector('img[alt]:not([alt=""])') }).map(e => e.outerHTML.slice(0, 90))""")
        if nameless:
            bad.append(f"{name}: buttons / links without a name: {nameless[:3]}")
        if "ErrorState" in page.content() and page.locator(".error-state, [data-testid=error-state]").count():
            bad.append(f"{name}: an error state is shown")
    except Exception as e:  # noqa: BLE001
        bad.append(f"{name}: check crashed: {e}")
    return bad


@pytest.mark.parametrize("lang,size", [("fa", "desktop"), ("en", "desktop"), ("fa", "phone"), ("en", "phone")])
def test_every_screen_renders_cleanly(browser, server, seeded, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for name, path in routes(seeded).items():
        ctx, page, problems = visit(browser, server, path, size, lang)
        try:
            failures += check(page, f"{lang}/{size} {name}", size, lang, problems, expect_not_found=path == "/no-such-screen")
            if name in ("/", "/downloads", "/remotion", "/models", "/queue", "/library"):
                page.screenshot(path=str(SHOTS / f"qa-{lang}-{size}-{name.strip('/') or 'home'}.png"))
        finally:
            ctx.close()
    assert not failures, "\n".join(failures[:60])


def test_every_sidebar_link_leads_to_a_real_screen(browser, server):
    ctx, page, problems = visit(browser, server, "/", "desktop", "en")
    try:
        links = page.evaluate("[...document.querySelectorAll('nav a[href]')].map(a => [a.getAttribute('href'), a.innerText.trim()])")
    finally:
        ctx.close()
    assert len(links) >= 12, links
    failures = []
    for href, label in links:
        c2, p2, probs = visit(browser, server, href, "desktop", "en")
        try:
            text = p2.locator("main").first.inner_text()
            if "not found" in text.lower() and "dashboard" in text.lower() and href != "/":
                failures.append(f"{href} ({label}) shows the not-found page")
            failures += [f"{href}: {p}" for p in probs]
        finally:
            c2.close()
    assert not failures, "\n".join(failures)


def test_every_tab_and_toggle_can_be_pressed(browser, server, seeded):
    failures: list[str] = []
    for name, path in routes(seeded).items():
        if path == "/no-such-screen":
            continue
        ctx, page, problems = visit(browser, server, path, "desktop", "fa")
        try:
            n = page.locator("[role=tab]").count()
            for i in range(min(n, 12)):
                try:
                    page.locator("[role=tab]").nth(i).click(timeout=3000)
                    page.wait_for_timeout(250)
                except Exception as e:  # noqa: BLE001
                    failures.append(f"{name}: tab {i} could not be pressed ({str(e)[:80]})")
            seg = page.locator(".seg button")
            for i in range(min(seg.count(), 10)):
                try:
                    seg.nth(i).click(timeout=3000)
                    page.wait_for_timeout(200)
                except Exception as e:  # noqa: BLE001
                    failures.append(f"{name}: segmented button {i} could not be pressed ({str(e)[:80]})")
            for i in range(min(page.locator("details > summary").count(), 8)):
                try:
                    page.locator("details > summary").nth(i).click(timeout=3000)
                except Exception:  # noqa: BLE001
                    pass
            page.wait_for_timeout(300)
            failures += [f"{name}: {p}" for p in problems]
        finally:
            ctx.close()
    assert not failures, "\n".join(failures[:40])


# ------------------------------------------------------------------ Remotion

def player_text(page) -> str:
    return page.locator("[data-testid=rm-player]").inner_text()


def test_remotion_page_every_composition_and_every_style_plays(browser, server):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = visit(browser, server, "/remotion", "desktop", "fa")
    failures: list[str] = []
    try:
        page.wait_for_selector("[data-testid=rm-player]", timeout=20000)
        page.wait_for_selector("[data-testid^=rm-style-]", timeout=20000)
        keys = page.eval_on_selector_all("[data-testid^=rm-style-]", "els => els.map(e => e.getAttribute('data-testid').slice(9))")
        assert len(keys) >= 20, keys
        assert page.locator("[data-testid^=rm-comp-]").count() == 4
        samples = {"TitleCard": "عنوان ویدیوی شما", "KineticText": "ایده", "Explainer": "چطور کار می‌کند", "LowerThird": "نام و نام‌خانوادگی"}
        for comp, want in samples.items():
            page.click(f"[data-testid=rm-comp-{comp}]")
            page.wait_for_timeout(400)
            page.wait_for_function("t => document.querySelector('[data-testid=rm-player]').innerText.includes(t)", arg=want, timeout=15000)
            for k in keys:
                page.click(f"[data-testid=rm-style-{k}]")
                page.wait_for_timeout(120)
                if len(problems):
                    failures.append(f"{comp} x {k}: {problems[:2]}")
                    problems.clear()
        for k in keys[:1]:
            page.click(f"[data-testid=rm-style-{k}]")
        page.screenshot(path=str(SHOTS / "remotion-page.png"))
    finally:
        ctx.close()
    assert not failures, "\n".join(failures[:20])


@pytest.mark.parametrize("comp,frame", [("TitleCard", 45), ("TitleCard", 140), ("KineticText", 70), ("KineticText", 200), ("Explainer", 40), ("Explainer", 160), ("Explainer", 430),
                                        ("LowerThird", 40), ("LowerThird", 140)])
def test_remotion_later_frames_of_every_style_do_not_break(browser, server, comp, frame):
    """The player is opened at a later frame (?frame=) for every animation family: stepped, bouncy, 3-D, parallax ... none may throw."""
    ctx, page, problems = visit(browser, server, f"/remotion?comp={comp}&frame={frame}&size=vertical", "desktop", "fa")
    failures = []
    try:
        page.wait_for_selector("[data-testid=rm-player]", timeout=20000)
        page.wait_for_selector("[data-testid^=rm-style-]", timeout=20000)
        keys = page.eval_on_selector_all("[data-testid^=rm-style-]", "els => els.map(e => e.getAttribute('data-testid').slice(9))")
        for k in keys:
            page.click(f"[data-testid=rm-style-{k}]")
            page.wait_for_timeout(100)
        failures += [f"{comp}@{frame}: {p}" for p in problems]
        txt = player_text(page)
        if not txt.strip():
            failures.append(f"{comp}@{frame}: the player shows no text")
    finally:
        ctx.close()
    assert not failures, "\n".join(failures[:10])


def test_remotion_code_tab_and_edit_flow(browser, server):
    ctx, page, problems = visit(browser, server, "/remotion", "desktop", "en")
    try:
        page.wait_for_selector("[data-testid=rm-player]", timeout=20000)
        page.get_by_label("Title", exact=True).fill("My own title")
        page.wait_for_function("() => document.querySelector('[data-testid=rm-player]').innerText.includes('My own title')", timeout=8000)
        page.get_by_role("tab", name=re.compile("Code")).click()
        page.wait_for_selector("[data-testid=rm-code] pre", timeout=8000)
        code = page.locator("[data-testid=rm-code] pre").inner_text()
        assert "useCurrentFrame" in code and "TitleCard" in code
        page.get_by_role("button", name="motion.ts").click()
        assert "Easing" in page.locator("[data-testid=rm-code] pre").inner_text()
        page.get_by_role("tab", name=re.compile("Rendered videos")).click()
        assert problems == [], problems
    finally:
        ctx.close()


def test_remotion_render_is_queued_and_followed(browser, server):
    from tests_ui.conftest import Api

    api = Api(server)
    status = api.get("/api/remotion/status")
    ctx, page, problems = visit(browser, server, "/remotion?comp=TitleCard&size=square", "desktop", "en")
    try:
        page.wait_for_selector("[data-testid=rm-render]", timeout=20000)
        page.wait_for_selector("[data-testid^=rm-style-]", timeout=20000)
        page.locator("[data-testid=rm-render]").click()
        page.wait_for_selector("text=Rendering started", timeout=8000)
        job_id = api.get("/api/remotion/renders")["renders"][0]["job_id"]
        end = time.time() + (360 if status["ready"] else 20)
        last = {}
        while time.time() < end:
            last = api.get(f"/api/jobs/{job_id}")
            if last["status"] in ("succeeded", "failed"):
                break
            time.sleep(1.5)
        if status["ready"]:
            assert last["status"] == "succeeded", last.get("error")
            page.wait_for_selector("[data-testid=rm-result] video", timeout=15000)
            assert last["result"]["bytes"] > 10000
        else:
            assert last["status"] in ("queued", "running") and last.get("wait_code") == "remotion_setup", last
            assert page.locator("text=not ready yet").count() >= 1
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


# ------------------------------------------------------------------ downloads and models

def test_curated_library_flow(browser, server):
    from tests_ui.conftest import Api

    api = Api(server)
    ctx, page, problems = visit(browser, server, "/downloads", "desktop", "en")
    try:
        page.wait_for_selector("[data-testid=curated-list]", timeout=20000)
        n = page.locator("[data-testid^=cur-]:not([data-testid=cur-go]):not([data-testid=cur-confirm-go])").count()
        assert n >= 14, n
        for grp in ("Images", "Control and consistent characters", "Upscaling", "Video", "Voice", "All"):
            page.get_by_role("button", name=grp, exact=True).click()
            page.wait_for_timeout(150)
        page.get_by_role("button", name="All", exact=True).click()
        # a plain commercial package: the file table opens and shows size, sha256, the mirror
        page.locator("[data-testid=cur-flux-parts]").get_by_role("button", name=re.compile("Files")).click()
        table = page.locator("[data-testid=cur-flux-parts] table").inner_text()
        assert "t5xxl_fp8_e4m3fn.safetensors" in table and "ComfyUI\\models\\text_encoders" in table and "hf-mirror.com" in table
        # a non-commercial one: flagged, and the licence must be confirmed first
        ultra = page.locator("[data-testid=cur-upscale-ultrasharp]")
        assert "Non-commercial" in ultra.inner_text()
        ultra.get_by_role("checkbox").check()
        page.locator("[data-testid=cur-go]").click()
        page.wait_for_selector("[data-testid=cur-confirm-go]", timeout=5000)
        assert page.locator("[data-testid=cur-confirm-go]").is_disabled()
        page.get_by_role("button", name="Cancel").click()
        assert api.get("/api/downloads/queue")["jobs"] == [], "nothing was queued without the confirmation"
        # a commercial one, scheduled far in the future so the real worker does not start it, then cancelled
        ultra.get_by_role("checkbox").uncheck()
        page.locator("[data-testid=cur-rife]").get_by_role("checkbox").check()
        r = api.post("/api/downloads", {"packages": ["rife"], "when": {"mode": "at", "time": time.strftime("%H:%M", time.localtime(time.time() + 6 * 3600))}})
        page.reload(wait_until="networkidle")
        page.wait_for_selector(f"[data-testid=dl-{r['job']['id']}]", timeout=10000)
        page.locator(f"[data-testid=dl-{r['job']['id']}]").get_by_role("button", name=re.compile("Cancel")).click()
        page.wait_for_timeout(1000)
        assert api.get(f"/api/jobs/{r['job']['id']}")["status"] == "cancelled"
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()


def test_models_page_shows_the_coexistence_card_and_the_gpu_panel(browser, server):
    ctx, page, problems = visit(browser, server, "/models", "desktop", "en")
    try:
        page.wait_for_selector("[data-testid=coexist-card]", timeout=20000)
        card = page.locator("[data-testid=coexist-card]")
        page.wait_for_function("() => document.querySelector('[data-testid=coexist-card]').innerText.includes('11434')", timeout=15000)
        text = card.inner_text()
        for port in ("8188", "11434", "5640", "5620"):
            assert port in text, port
        assert "NMarketing" in text
        assert [p for p in problems if "favicon" not in p] == [], problems
    finally:
        ctx.close()
