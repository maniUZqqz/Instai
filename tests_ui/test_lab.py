"""Lab screens (hub, workers, voices, rigs, comparison, retake, mix, automation, notifications, consistency) in Persian and English at desktop and phone width: texts and direction, real flows against the
running server (pairing code, LAN switch, voice casting with licence warnings, consent-gated references, rig create/edit/approve/preview),
no console errors, no failed requests, no horizontal page scroll. Seeds through the API of the running server (see conftest.Api)."""
from __future__ import annotations

import re
import time
import uuid

import pytest

from tests_ui.conftest import Api
from tests_ui.lab_helpers import PERSIAN, SHOTS, digits, hscroll, open_lab, tone_wav

LANGS = ["fa", "en"]
SIZES = ["desktop", "phone"]
DEMO_TEXT = {  # a few words that must come out in the right language
    "fa": {"hub": "آزمایشگاه تولید", "workers": "رایانه‌های کارگر", "local": "این رایانه", "pocket_warn": "غیرتجاری", "edge_warn": "غیررسمی", "approved": "تأییدشده"},
    "en": {"hub": "Production lab", "workers": "Worker PCs", "local": "This PC", "pocket_warn": "NON-COMMERCIAL", "edge_warn": "unofficial", "approved": "Approved"},
}


@pytest.fixture(scope="module")
def api(server) -> Api:
    return Api(server)


@pytest.fixture
def char(api):
    """A fresh page with one fresh character per test, so saved voices / rigs never leak between parametrised runs."""
    tag = uuid.uuid4().hex[:6]
    page = api.post("/api/pages", {"name": f"استودیو {tag}", "format": "recurring_character", "languages": ["fa"], "idea": "x"})
    ch = api.post(f"/api/pages/{page['id']}/characters", {"name": f"نیما {tag}", "role": "main"})
    return {"page": page["id"], "character": ch["id"], "query": f"?page={page['id']}&character={ch['id']}"}


def finish(ctx, problems, name):
    try:
        assert not problems, f"{name}: " + "; ".join(problems)
    finally:
        ctx.close()


# ------------------------------------------------------------------ hub
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_hub_renders_links_and_direction(browser, server, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_lab(browser, server, size, "/lab", lang)
    try:
        html = page.locator("html")
        assert html.get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
        assert html.get_attribute("lang") == lang
        assert page.locator("main h1").inner_text().strip() == DEMO_TEXT[lang]["hub"]
        if lang == "fa":
            assert PERSIAN.search(page.locator("main").inner_text())
        for key in ("workers", "voices", "rigs", "compare", "retake", "mix", "automation", "consistency", "notifications"):
            tile = page.locator(f"[data-testid=tile-{key}]")
            assert tile.get_attribute("href") == f"/lab/{key}"                          # every screen is switched on
            assert tile.get_attribute("aria-disabled") is None
        assert page.locator("nav.nav a[href='/lab']").count() == 1           # the sidebar entry
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        page.screenshot(path=str(SHOTS / f"lab-hub-{lang}-{size}.png"))
        page.locator("[data-testid=tile-workers]").click()
        page.wait_for_url(re.compile(r"/lab/workers$"))
        assert page.locator("main h1").inner_text().strip() == DEMO_TEXT[lang]["workers"]
        page.go_back()
        page.wait_for_url(re.compile(r"/lab$"))
        page.locator("[data-testid=tile-voices]").click()
        page.wait_for_url(re.compile(r"/lab/voices$"))
        page.go_back()
        page.locator("[data-testid=tile-rigs]").click()
        page.wait_for_url(re.compile(r"/lab/rigs$"))
        assert page.locator("main h1").count() == 1
    finally:
        finish(ctx, problems, f"hub {lang} {size}")


# ------------------------------------------------------------------ workers
@pytest.fixture
def lan_port(api):
    """A free port for the worker listener (the UI toggle reuses the saved port) and a guaranteed shut-down afterwards."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api.post("/api/workers/lan", {"enabled": True, "port": port})
    api.post("/api/workers/lan", {"enabled": False})
    yield port
    api.post("/api/workers/lan", {"enabled": False})


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_workers_page_pairing_and_lan_switch(browser, server, api, lan_port, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/workers", lang)
    try:
        local = page.locator("[data-testid=device-local]")
        local.wait_for(timeout=15000)
        assert DEMO_TEXT[lang]["local"] in local.inner_text()
        assert page.locator("[data-testid=device-local] .badge").first.is_visible()
        switch = page.get_by_role("switch")
        assert not switch.is_checked()
        assert page.locator("[data-testid=pairing-panel]").count() == 0
        # the plain-language explanation of what the LAN switch opens
        text = page.locator("main").inner_text()
        assert ("فقط یک درگاه" in text) if lang == "fa" else ("ONE extra port" in text)
        # turn the worker port on with the switch
        page.locator("label.switch").first.click()                                 # (the input itself is visually hidden under the track)
        page.wait_for_function("document.querySelector('[role=switch]').checked === true")
        assert api.get("/api/workers")["lan"]["running"] is True
        # show the pairing code: 9 characters with a dash, the steps for PC B and START-WORKER.bat
        page.get_by_role("button", name=re.compile("نمایش کد جفت|Show pairing code")).click()
        code = page.locator("[data-testid=pairing-code]")
        code.wait_for(timeout=15000)
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", code.inner_text().strip()), code.inner_text()
        steps = page.locator("[data-testid=pairing-steps] li")
        assert steps.count() == 4
        assert "START-WORKER.bat" in page.locator("[data-testid=pairing-steps]").inner_text()
        panel = page.locator("[data-testid=pairing-panel]").inner_text()
        assert re.search(r"\d", digits(panel))                                     # the countdown
        addr = page.locator("[data-testid=pairing-address]")
        if addr.count():                                                           # a LAN address (this PC may have none)
            assert re.fullmatch(r"[\d.]+:" + str(lan_port), addr.first.inner_text().strip())
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"lab-workers-{lang}-{size}.png"))
        # turn it off again
        page.locator("label.switch").first.click()
        page.wait_for_function("document.querySelector('[role=switch]').checked === false")
        assert api.get("/api/workers")["lan"]["running"] is False
        page.locator("[data-testid=pairing-panel]").wait_for(state="detached", timeout=10000)
    finally:
        finish(ctx, problems, f"workers {lang} {size}")


@pytest.fixture
def paired_worker(api, server, lan_port):
    """A worker paired through the real HTTP API (the main server also serves /api/worker/* on localhost) and reporting capabilities."""
    import requests

    code = api.post("/api/workers/pairing")["code"]
    name = "pc-b-" + uuid.uuid4().hex[:4]
    r = requests.post(server + "/api/worker/pair", json={"code": code, "name": name, "info": {"agent": "1.0"}}, timeout=20)
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    h = requests.post(server + "/api/worker/hello", headers={"Authorization": f"Worker {token}"}, timeout=20,
                      json={"gpu": {"name": "RTX 3060", "total_mb": 12288, "free_mb": 9000}, "caps": ["gpu", "comfy:wan22_i2v_a14b_fp8", "voice:moss"] + [f"voice:x{i}" for i in range(8)],
                            "models": {"comfyui": True}, "info": {"agent": "1.0"}})
    assert h.status_code == 200
    yield {"name": name, "token": token}
    for w in api.get("/api/workers")["workers"]:
        if w["name"].startswith(name):
            api.call("DELETE", f"/api/workers/{w['id']}")


@pytest.mark.parametrize("lang", LANGS)
def test_workers_page_shows_a_paired_worker_and_its_controls(browser, server, api, paired_worker, lang):
    name = paired_worker["name"]
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/workers", lang)
    try:
        card = page.locator("[data-testid=device-worker]").filter(has_text=name)
        card.wait_for(timeout=20000)
        txt = card.inner_text()
        assert "RTX 3060" in txt and "comfy:wan22_i2v_a14b_fp8" in txt and "voice:moss" in txt
        assert digits(txt).count("12") >= 1                                                         # VRAM total is shown
        assert card.locator(".gpu-bar").count() == 1
        assert card.locator("details summary").count() >= 1                                         # the long capability list is folded
        # disable and enable (the switch)
        sw = card.get_by_role("switch")
        assert sw.is_checked()
        card.locator("label.switch").click()
        card.locator(".badge.err").filter(has_text=re.compile("غیرفعال|Disabled")).wait_for(timeout=10000)
        assert [w for w in api.get("/api/workers")["workers"] if w["name"] == name][0]["enabled"] is False
        card.locator("label.switch").click()
        page.wait_for_function("(n) => [...document.querySelectorAll('[data-testid=device-worker]')].find(e => e.innerText.includes(n))?.querySelector('[role=switch]').checked === true", arg=name)
        assert [w for w in api.get("/api/workers")["workers"] if w["name"] == name][0]["enabled"] is True
        # rename in a dialog
        card.get_by_role("button", name=re.compile("تغییر نام|Rename")).click()
        dlg = page.get_by_role("dialog")
        dlg.get_by_role("textbox").fill(name + "-x")
        dlg.get_by_role("button", name=re.compile("ذخیره|Save")).click()
        dlg.wait_for(state="detached", timeout=10000)
        assert any(w["name"] == name + "-x" for w in api.get("/api/workers")["workers"])
        card = page.locator("[data-testid=device-worker]").filter(has_text=name + "-x")
        card.wait_for(timeout=10000)
        # benchmark: a task is queued for the worker and the card shows it
        card.get_by_role("button", name=re.compile("اجرای بنچمارک|Run benchmark")).click()
        card.locator("[role=progressbar]").wait_for(timeout=15000)
        assert any(t["kind"] == "bench.node" for t in api.get("/api/remote-tasks"))
        assert page.locator("table.table").filter(has_text="bench.node").count() == 1               # and the recent tasks table lists it
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        # remove with confirmation
        card.get_by_role("button", name=re.compile("حذف کارگر|Remove worker")).click()
        page.get_by_role("dialog").get_by_role("button", name=re.compile("حذف کارگر|Remove worker")).click()
        page.locator("[data-testid=device-worker]").filter(has_text=name).wait_for(state="detached", timeout=15000)
        assert not [w for w in api.get("/api/workers")["workers"] if w["name"].startswith(name)]
    finally:
        finish(ctx, problems, f"worker card {lang}")


# ------------------------------------------------------------------ voices
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_voices_engines_badges_and_warnings(browser, server, char, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/voices" + char["query"], lang)
    try:
        page.locator("[data-testid^=engine-]").first.wait_for(timeout=20000)
        ids = page.locator("[data-testid^=engine-]").evaluate_all("els => els.map(e => e.getAttribute('data-testid').replace('engine-', ''))")
        assert sorted(ids) == ["edge", "fake", "moss", "piper", "pocket"]
        for e in ids:
            assert page.locator(f"[data-testid=engine-{e}] .badge").count() >= 2          # availability + licence badge
        pocket, edge = page.locator("[data-testid=engine-pocket]").inner_text(), page.locator("[data-testid=engine-edge]").inner_text()
        assert "NON-COMMERCIAL" in pocket and DEMO_TEXT[lang]["pocket_warn"] in page.locator("[data-testid=warning-pocket]").inner_text()
        assert "UNOFFICIAL" in edge and DEMO_TEXT[lang]["edge_warn"] in page.locator("[data-testid=warning-edge]").inner_text()
        assert page.locator("[data-testid=warning-moss]").count() == 0                   # MOSS has no warning
        for sv in ("moss", "sfx", "music"):
            assert page.locator(f"[data-testid=service-{sv}]").is_visible()
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"lab-voices-{lang}-{size}.png"))
    finally:
        finish(ctx, problems, f"voices engines {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_casting_edge_for_english_shows_the_warning_and_persists(browser, server, api, char, lang):
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/voices" + char["query"], lang)
    try:
        cast_en = page.locator("[data-testid=cast-en]")
        cast_en.wait_for(timeout=20000)
        select = cast_en.locator("select").first
        assert select.input_value() == "auto"                                           # nothing risky is ever preselected
        assert page.locator("[data-testid=cast-warning-en]").count() == 0
        options = select.locator("option").all_inner_texts()
        assert any("Edge" in o and "UNOFFICIAL" in o for o in options)
        assert not any("Pocket" in o for o in options)                                   # Pocket speaks Persian only: not offered for English
        fa_options = page.locator("[data-testid=cast-fa] select").first.locator("option").all_inner_texts()
        assert any("Pocket" in o and "NON-COMMERCIAL" in o for o in fa_options)           # ... but it is listed, with its badge, for Persian
        assert page.locator("[data-testid=cast-fa] select").first.input_value() == "auto"
        select.select_option("edge")
        warn = page.locator("[data-testid=cast-warning-en]")
        warn.wait_for(timeout=5000)
        assert DEMO_TEXT[lang]["edge_warn"] in warn.inner_text() and "UNOFFICIAL" in warn.inner_text()
        assert page.locator("[data-testid=cast-warning-fa]").count() == 0                # per language card
        cast_en.get_by_role("button", name=re.compile("ذخیرهٔ انتخاب|Save choice")).click()
        page.wait_for_function("() => document.querySelector('[data-testid=cast-en]').innerText.match(/ذخیره‌شده|Saved/)")
        casts = {c["language"]: c for c in api.get(f"/api/characters/{char['character']}/voices")["casts"]}
        assert casts["en"]["engine"] == "edge" and casts["en"]["licence"]["warning"] == "edge_unofficial" and "fa" not in casts
        page.reload()
        page.locator("[data-testid=cast-en] select").first.wait_for(timeout=20000)
        assert page.locator("[data-testid=cast-en] select").first.input_value() == "edge"
        assert page.locator("[data-testid=cast-warning-en]").is_visible()
        # remove it again: automatic, warning gone
        page.locator("[data-testid=cast-en]").get_by_role("button", name=re.compile("حذف انتخاب|Remove choice")).click()
        page.wait_for_function("() => document.querySelector('[data-testid=cast-en] select').value === 'auto'")
        assert api.get(f"/api/characters/{char['character']}/voices")["casts"] == []
    finally:
        finish(ctx, problems, f"cast edge {lang}")


def test_a_reference_without_consent_is_blocked_and_with_consent_is_saved(browser, server, api, char, tmp_path):
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/voices" + char["query"], "en")
    try:
        form = page.locator("[data-testid=ref-form]")
        form.wait_for(timeout=20000)
        submit = page.locator("[data-testid=ref-submit]")
        assert submit.is_disabled() and "consent" in page.locator("[data-testid=ref-blocked]").inner_text().lower()
        wav = tmp_path / "voice.wav"
        wav.write_bytes(tone_wav(4.0))
        form.get_by_label(re.compile("Voice owner")).fill("Ali")
        form.get_by_label(re.compile("^Purpose")).fill("narration of this page")
        form.locator("input[type=file]").set_input_files(str(wav))
        page.wait_for_function("() => !document.querySelector('[data-testid=ref-blocked]')?.innerText.includes('audio file')")
        assert submit.is_disabled()                                                     # file and names are there, consent is not
        assert "consent confirmation" in page.locator("[data-testid=ref-blocked]").inner_text()
        # a recording that is too short is refused in the browser, before any request
        short = tmp_path / "short.wav"
        short.write_bytes(tone_wav(1.0))
        form.locator("input[type=file]").set_input_files(str(short))
        page.wait_for_selector("text=between 3 and 30 seconds")
        assert submit.is_disabled()
        form.locator("input[type=file]").set_input_files(str(wav))
        page.wait_for_function("() => !document.body.innerText.includes('between 3 and 30 seconds (now')")
        form.get_by_label(re.compile("I confirm that the voice owner")).check()
        page.wait_for_function("() => !document.querySelector('[data-testid=ref-submit]').disabled")
        assert api.get(f"/api/characters/{char['character']}/voices")["refs"] == []     # nothing was sent until now
        if not ffmpeg_ok(api):
            pytest.skip("ffmpeg is not available here: the recording cannot be normalised (the consent gate above was checked)")
        submit.click()
        page.locator("[data-testid=voice-ref]").first.wait_for(timeout=20000)
        refs = api.get(f"/api/characters/{char['character']}/voices")["refs"]
        assert len(refs) == 1 and refs[0]["person_name"] == "Ali" and refs[0]["consent_given"] is True
        assert "Consent recorded" in page.locator("[data-testid=voice-ref]").first.inner_text()
        assert page.locator("[data-testid=voice-ref] audio").first.get_attribute("src").startswith("/media/")
        # the Persian cast can now use it: the engine becomes MOSS
        fa_card = page.locator("[data-testid=cast-fa]")
        fa_card.locator("select").last.select_option(str(refs[0]["id"]))          # (engine is "auto": the reference select is the last one)
        assert fa_card.locator("select").first.is_disabled()
        fa_card.get_by_role("button", name=re.compile("Save choice")).click()
        page.wait_for_function("() => document.querySelector('[data-testid=cast-fa]').innerText.includes('Saved')")
        cast = api.get(f"/api/characters/{char['character']}/voices")["casts"][0]
        assert cast["engine"] == "moss" and cast["reference"] == refs[0]["id"]
        # delete the reference (with confirmation): the cast goes back to automatic
        page.locator("[data-testid=voice-ref]").get_by_role("button", name=re.compile("Delete reference")).click()
        page.get_by_role("dialog").get_by_role("button", name="Delete reference").click()
        page.locator("[data-testid=voice-ref]").wait_for(state="detached", timeout=10000)
        assert api.get(f"/api/characters/{char['character']}/voices")["refs"] == []
    finally:
        finish(ctx, problems, "reference consent")


def test_voice_preview_shows_the_audio_and_licence(browser, server, char):
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/voices" + char["query"], "en")
    try:
        card = page.locator("[data-testid=cast-en]")
        card.wait_for(timeout=20000)
        card.get_by_role("button", name=re.compile("Listen to a sample")).click()
        audio = page.locator("[data-testid=preview-en] audio")
        audio.wait_for(timeout=60000)
        assert audio.get_attribute("src").startswith("/media/previews/")
        assert page.locator("[data-testid=preview-en] .badge").first.is_visible()           # the licence of the engine that spoke
    finally:
        finish(ctx, problems, "voice preview")


# ------------------------------------------------------------------ rigs
def ffmpeg_ok(api) -> bool:
    return bool(api.get("/api/health").get("ffmpeg"))


@pytest.mark.parametrize("lang", LANGS)
def test_rig_create_edit_approve_preview(browser, server, api, char, lang):
    if not ffmpeg_ok(api):
        pytest.skip("ffmpeg is not available here: the preview video cannot be made")
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/rigs" + char["query"], lang)
    try:
        page.locator("[data-testid=rig-create-demo]").click()
        page.locator("[data-testid^=completeness-]").first.wait_for(timeout=30000)
        rig_id = int(page.locator("[data-testid^=completeness-]").first.get_attribute("data-testid").split("-")[1])
        assert digits(page.locator(f"[data-testid=mouth-count-{rig_id}]").inner_text()).replace(" ", "") == "9/9"
        assert page.locator(f"[data-testid=completeness-{rig_id}] .lab-mouths li.lab-chip-ok").count() == 9
        assert page.locator(f"[data-testid=rig-{rig_id}] .lab-thumbs img").count() == 18          # the demo character has 18 parts
        # edit a pivot of the right arm and save
        page.locator(f"[data-testid=parts-{rig_id}] summary").click()
        px = page.locator(f"[data-testid=parts-{rig_id}] input[aria-label^='arm_r'][aria-label$=' x']").first
        px.fill("")
        px.fill("41")
        save = page.locator(f"[data-testid=parts-save-{rig_id}]")
        assert save.is_enabled()
        with sent(page, "PATCH", f"/api/rigs/{rig_id}"):
            save.click()
        rig = api.get(f"/api/characters/{char['character']}/rigs")[0]
        assert rig["parts"]["arm_r"]["pivot"][0] == 41
        # approve
        assert not rig["approved"]
        page.locator(f"[data-testid=rig-approve-{rig_id}]").click()
        page.wait_for_selector(f"[data-testid=rig-{rig_id}] >> text={DEMO_TEXT[lang]['approved']}")
        assert api.get(f"/api/characters/{char['character']}/rigs")[0]["approved"] is True
        # preview: a real clip rendered by the worker, shown in a <video> with a source
        page.locator(f"[data-testid=rig-preview-{rig_id}]").click()
        video = page.locator(f"[data-testid=rig-video-{rig_id}] video")
        video.wait_for(timeout=120000)
        src = video.get_attribute("src")
        assert src and src.startswith("/media/characters/")
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"lab-rigs-{lang}-desktop.png"), full_page=True)
    finally:
        finish(ctx, problems, f"rigs {lang}")


@pytest.mark.parametrize("lang", LANGS)
def test_phone_width_has_no_horizontal_scroll_on_every_lab_screen(browser, server, api, char, lang):
    api.post(f"/api/characters/{char['character']}/rigs", {"source": "demo"})
    shots = {"hub": "/lab", "workers": "/lab/workers", "voices": "/lab/voices" + char["query"], "rigs": "/lab/rigs" + char["query"]}
    SHOTS.mkdir(parents=True, exist_ok=True)
    for name, path in shots.items():
        ctx, page, problems = open_lab(browser, server, "phone", path, lang)
        try:
            if name == "rigs":
                page.locator("[data-testid^=completeness-]").first.wait_for(timeout=20000)
                page.locator("[data-testid^=parts-] summary").first.click()          # the widest element: the parts table
            if name == "voices":
                page.locator("[data-testid=cast-en]").wait_for(timeout=20000)
            sw, iw = hscroll(page)
            assert sw <= iw + 1, f"{name} {lang}: horizontal scroll {sw} > {iw}"
            assert page.locator("html").get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
            page.screenshot(path=str(SHOTS / f"lab-{name}-{lang}-phone.png"), full_page=False)
        finally:
            finish(ctx, problems, f"phone {name} {lang}")


# ====================================================================================================================
# Round 2: comparison, retake, mix, automation + publishing, notifications, consistency
# ====================================================================================================================
T2 = {
    "fa": {"unavailable": "نصب نیست", "skipped": "ردشد", "estimate": "برآورد", "missing": "ناقص", "empty_notes": "اعلانی نیست", "honest": "صادقانه"},
    "en": {"unavailable": "Not installed", "skipped": "Skipped", "estimate": "estimate", "missing": "Missing", "empty_notes": "No notifications", "honest": "Honest note"},
}
LABEL_SAVE = re.compile("^(ذخیره|Save)$")


@pytest.fixture(scope="module")
def anime(server, seeded):
    """The seeded anime page and its first episode (script, storyboard, preview video, placeholder keyframes)."""
    a = seeded["anime_whatif"]
    return {"page": a["page"], "episode": a["episodes"][0], "query": f"?page={a['page']}&episode={a['episodes'][0]}"}


@pytest.fixture
def fresh_page(api):
    """A page of its own for tests that change its settings."""
    tag = uuid.uuid4().hex[:6]
    page = api.post("/api/pages", {"name": f"آزمایشگاه {tag}", "format": "recurring_character", "languages": ["fa"], "idea": "x"})
    return {"page": page["id"], "query": f"?page={page['id']}"}


def has_video(api, episode) -> bool:
    return bool(api.get("/api/health").get("ffmpeg")) and bool(api.get(f"/api/episodes/{episode}")["videos"])


def phone_ok(page, name):
    sw, iw = hscroll(page)
    assert sw <= iw + 1, f"{name}: horizontal scroll {sw} > {iw}"


def sent(page, method: str, url_part: str):
    """Context manager around an action: waits for the response of the request this action sends (method + a part of the URL)."""
    return page.expect_response(lambda r: r.request.method == method and url_part in r.url, timeout=30000)


def wait_until(fn, timeout: float = 60, what: str = "the condition"):
    """Poll a condition on the server state (a worker job) until it holds."""
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return
        time.sleep(0.3)
    raise AssertionError(f"timed out waiting for {what}")


def wait_text(page, selector: str, needle: str, timeout: int = 15000):
    """Wait until the element's text (Persian digits turned into ASCII) contains `needle`."""
    js = "([sel, needle]) => (document.querySelector(sel)?.innerText || '').replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 0x6f0)).includes(needle)"
    try:
        page.wait_for_function(js, arg=[selector, needle], timeout=timeout)
    except Exception as e:  # noqa: BLE001 - say what the page showed instead
        shown = page.locator(selector).first.inner_text() if page.locator(selector).count() else "(not on the page)"
        raise AssertionError(f"{selector} never contained {needle!r}; it shows {shown!r}") from e


def number(text: str) -> float:
    """First number in a formatted text (Persian digits and the Persian decimal separator included)."""
    m = re.search(r"-?\d+(?:\.\d+)?", digits(text).replace("٫", "."))
    assert m, f"no number in {text!r}"
    return float(m.group(0))


# ------------------------------------------------------------------ comparison
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_compare_page_lists_candidates_with_licences_and_estimates(browser, server, anime, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/compare" + anime["query"], lang)
    try:
        page.locator("[data-testid=candidate-wan22]").wait_for(timeout=20000)
        ids = page.locator("[data-testid^=candidate-]").evaluate_all("els => els.map(e => e.getAttribute('data-testid')).filter(x => !x.startsWith('candidate-est'))")
        assert sorted(ids) == ["candidate-animegen", "candidate-anisora", "candidate-wan22"]
        for cid in ("wan22", "anisora", "animegen"):
            txt = page.locator(f"[data-testid=candidate-{cid}]").inner_text()
            assert T2[lang]["unavailable"] in txt                                     # no ComfyUI here: honest "not installed"
            assert "Apache-2.0" in txt
            assert T2[lang]["estimate"] in page.locator(f"[data-testid=candidate-est-{cid}]").inner_text()   # times are marked as estimates
        assert "extra restrictions" in page.locator("[data-testid=candidate-anisora]").inner_text()
        assert "ComfyUI-GGUF" in page.locator("[data-testid=candidate-anisora]").inner_text()
        assert page.locator("html").get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
        assert page.locator("[data-testid=compare-create]").is_visible()
        phone_ok(page, f"compare {lang} {size}")
    finally:
        finish(ctx, problems, f"compare render {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_compare_without_key_images_says_so_and_does_not_start(browser, server, api, seeded, lang):
    plain = seeded["concept_explainer"]                     # planned episodes only: no storyboard, no key images
    ctx, page, problems = open_lab(browser, server, "desktop", f"/lab/compare?page={plain['page']}", lang)
    try:
        page.locator("[data-testid=compare-create]").wait_for(timeout=20000)
        page.get_by_role("status").filter(has_text=re.compile("تصویر کلیدی|key images")).wait_for(timeout=10000)
        assert page.locator("[data-testid=compare-create]").is_disabled()
        assert api.get(f"/api/comparisons?page={plain['page']}") == []
        phone_ok(page, f"compare no stills {lang}")
    finally:
        finish(ctx, problems, f"compare no stills {lang}")


@pytest.mark.parametrize("lang", LANGS)
def test_compare_creates_a_comparison_skips_missing_models_and_sets_the_page_default(browser, server, api, anime, lang):
    if not api.get(f"/api/assets?episode={anime['episode']}&role=keyframe&kind=image&current=1"):
        pytest.skip("the seeded episode has no key images here (no preview was produced: ffmpeg is missing)")
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/compare" + anime["query"], lang)
    try:
        earlier = {c["id"] for c in api.get(f"/api/comparisons?page={anime['page']}")}
        page.locator("[data-testid=compare-seeds]").fill("5, 6")
        with sent(page, "POST", "/api/comparisons") as made:
            page.locator("[data-testid=compare-create]").click()
        cmp_id = made.value.json()["comparison"]["id"]
        assert cmp_id not in earlier
        page.wait_for_function("(id) => document.querySelector('[data-testid=compare-pick]')?.value === String(id)", arg=cmp_id, timeout=15000)
        page.locator("[data-testid=compare-grid]").wait_for(timeout=30000)
        detail = api.get(f"/api/comparisons/{cmp_id}")
        n = len(detail["clips"])
        assert detail["seeds"] == [5, 6] and n == len(detail["stills"]) * 2 * 3        # every still x seed x model has a cell
        # the job runs on the worker: with no ComfyUI every model is recorded as SKIPPED, with its reason (never a made-up clip)
        page.wait_for_function("(n) => document.querySelectorAll('[data-testid=clip-reason]').length >= n", arg=n, timeout=90000)
        assert "not available" in page.locator("[data-testid=clip-reason]").first.inner_text()
        assert T2[lang]["skipped"] in page.locator("[data-testid=cell-0-5-wan22]").inner_text()
        assert page.locator("[data-testid=compare-grid] video").count() == 0
        for cid in ("wan22", "anisora", "animegen"):
            assert page.locator(f"[data-testid=vote-{cid}]").is_disabled()           # no clip, no vote
        assert {c["status"] for c in api.get(f"/api/comparisons/{cmp_id}")["clips"]} == {"skipped"}
        # "run again" queues a new job
        jobs_before = len(api.get(f"/api/jobs?kind=compare.run&page={anime['page']}"))
        with sent(page, "POST", f"/api/comparisons/{cmp_id}/run"):
            page.locator("[data-testid=compare-run-again]").click()
        assert len(api.get(f"/api/jobs?kind=compare.run&page={anime['page']}")) == jobs_before + 1
        # the page default: change it, see it saved, put it back
        sel = page.locator("[data-testid=compare-default-select]")
        assert sel.input_value() == "wan22"
        with sent(page, "PUT", f"/api/pages/{anime['page']}/production-config"):
            sel.select_option("animegen")
        assert api.get(f"/api/pages/{anime['page']}/production-config")["anime_model"] == "animegen"
        with sent(page, "PUT", f"/api/pages/{anime['page']}/production-config"):
            sel.select_option("wan22")
        assert api.get(f"/api/pages/{anime['page']}/production-config")["anime_model"] == "wan22"
    finally:
        finish(ctx, problems, f"compare create {lang}")


# ------------------------------------------------------------------ retake
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_retake_page_renders_with_range_modes_and_validation(browser, server, api, anime, lang, size):
    if not has_video(api, anime["episode"]):
        pytest.skip("ffmpeg is not available here: no rendered video to retake")
    ctx, page, problems = open_lab(browser, server, size, "/lab/retake" + anime["query"], lang)
    try:
        video = page.locator("[data-testid=retake-video]")
        video.wait_for(timeout=20000)
        assert video.get_attribute("src").startswith("/media/")
        modes = page.locator("input[name=retake-mode]").evaluate_all("els => els.map(e => e.value)")
        assert modes == ["keep", "mute", "replace", "cut"]
        page.locator("[data-testid=retake-start]").fill("1")
        page.locator("[data-testid=retake-end]").fill("1.1")
        page.get_by_role("status").filter(has_text=re.compile("۰٫۴|0\\.4")).wait_for(timeout=5000)     # too short: the reason is shown
        assert page.locator("[data-testid=retake-submit]").is_disabled()
        page.locator("[data-testid=retake-end]").fill("0.5")                                              # ends before it starts
        assert page.locator("[data-testid=retake-submit]").is_disabled()
        page.locator("[data-testid=retake-end]").fill("2")
        assert page.locator("[data-testid=retake-submit]").is_enabled()
        page.locator("label.choice", has=page.locator("[data-testid=retake-mode-replace]")).click()
        assert page.locator("[data-testid=retake-audio-asset]").is_visible()
        assert page.locator("[data-testid=retake-submit]").is_disabled()                                  # replace needs an audio file
        assert page.locator("html").get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
        phone_ok(page, f"retake {lang} {size}")
    finally:
        finish(ctx, problems, f"retake render {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_retake_cut_produces_a_result_with_sync_numbers_and_revert_restores_the_video(browser, server, api, anime, lang):
    if not has_video(api, anime["episode"]):
        pytest.skip("ffmpeg is not available here: no rendered video to retake")
    before = api.get(f"/api/episodes/{anime['episode']}")["videos"][0]
    if before["duration_sec"] < 3.5:
        pytest.skip("the preview is too short for a 1 s cut")
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/retake" + anime["query"], lang)
    try:
        page.locator("[data-testid=retake-video]").wait_for(timeout=20000)
        page.locator("[data-testid=retake-start]").fill("1")
        page.locator("[data-testid=retake-end]").fill("2")
        page.locator("label.choice", has=page.locator("[data-testid=retake-mode-cut]")).click()
        with sent(page, "POST", f"/api/episodes/{anime['episode']}/video-retakes") as made:
            page.locator("[data-testid=retake-submit]").click()
        new_id = made.value.json()["retake"]["id"]
        wait_until(lambda: api.get(f"/api/video-retakes/{new_id}")["status"] in ("done", "failed"), 120, "the retake job")
        new = api.get(f"/api/video-retakes/{new_id}")
        assert new["status"] == "done", new["error"]
        page.wait_for_function("(u) => document.querySelector('[data-testid=retake-after-video]')?.getAttribute('src') === u", arg=new["result"]["url"], timeout=30000)   # an earlier retake may still be shown
        page.locator(f"[data-testid=retake-history-{new_id}]").wait_for(timeout=15000)
        page.locator("[data-testid=retake-result]").wait_for(timeout=10000)
        # exact sync numbers of the result: duration error ~0 s
        assert number(page.locator("[data-testid=retake-duration-error]").inner_text()) < 0.2
        after_src = page.locator("[data-testid=retake-after-video]").get_attribute("src")
        assert after_src == new["result"]["url"]
        page.get_by_role("button", name=re.compile("^(قبل|Before)$")).click()
        page.locator("[data-testid=retake-before-video]").wait_for(timeout=10000)
        assert page.locator("[data-testid=retake-before-video]").get_attribute("src") != after_src          # the toggle shows the ORIGINAL video
        assert page.locator("[data-testid^=retake-history-]").count() >= 1
        cur = api.get(f"/api/episodes/{anime['episode']}")["videos"][0]
        assert cur["id"] != before["id"] and abs(cur["duration_sec"] - (before["duration_sec"] - 1.0)) < 0.3        # 1 s shorter
        phone_ok(page, "retake result")
        # revert (with confirmation): the previous video is current again
        page.locator("[data-testid=retake-revert]").click()
        with sent(page, "POST", f"/api/video-retakes/{new_id}/revert"):
            page.get_by_role("dialog").get_by_role("button", name=re.compile("برگرداندن به قبل|Revert")).click()
        assert api.get(f"/api/assets/{before['id']}")["is_current"] is True
        assert api.get(f"/api/episodes/{anime['episode']}")["videos"][0]["id"] == before["id"]
    finally:
        finish(ctx, problems, f"retake cut {lang}")


# ------------------------------------------------------------------ mix
def clear_mix(api, episode):
    for t in api.get(f"/api/episodes/{episode}/mix")["tracks"]:
        api.call("DELETE", f"/api/mix-tracks/{t['id']}")


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_mix_page_empty_state_and_explanations(browser, server, api, anime, lang, size):
    clear_mix(api, anime["episode"])
    ctx, page, problems = open_lab(browser, server, size, "/lab/mix" + anime["query"], lang)
    try:
        panel = page.locator("[data-testid=mix-panel]")
        panel.wait_for(timeout=20000)
        text = panel.inner_text()
        assert ("کم‌شدنِ خودکار" in text) if lang == "fa" else ("ducking" in text.lower())
        assert ("رایانهٔ دوم" in text) if lang == "fa" else ("second PC" in text)
        assert page.locator("[data-testid=mix-tracks]").count() == 0
        assert page.locator("[data-testid=mix-generate]").is_disabled()               # nothing to generate yet
        phone_ok(page, f"mix {lang} {size}")
    finally:
        finish(ctx, problems, f"mix empty {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_mix_plan_add_edit_generate_with_fake_engines(browser, server, api, anime, lang):
    ep_id = anime["episode"]
    clear_mix(api, ep_id)
    shot = api.get(f"/api/episodes/{ep_id}")["scenes"][0]["shots"][0]
    audio_before = api.get(f"/api/pages/{anime['page']}")["profiles"]["audio"]
    api.put(f"/api/pages/{anime['page']}/profiles/audio", {**audio_before, "music_enabled": True, "sfx_enabled": True, "music_mood": "calm", "music_volume_db": -22})
    api.patch(f"/api/shots/{shot['id']}", {"sfx": "heavy door slam"})
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/mix" + anime["query"], lang)
    try:
        page.locator("[data-testid=mix-plan]").click()
        page.locator("li[data-testid^=track-]").first.wait_for(timeout=20000)
        kinds = {t["kind"] for t in api.get(f"/api/episodes/{ep_id}/mix")["tracks"]}
        assert {"music", "sfx"} <= kinds                                              # music bed + the shot's effect
        assert page.locator("li[data-testid^=track-]").count() >= 2
        assert page.locator("audio[data-testid^=track-audio-]").count() == 0          # nothing generated yet: no player
        # a custom track by hand
        n0 = page.locator("li[data-testid^=track-]").count()
        page.locator("[data-testid=mix-add-kind]").select_option("ambience")
        page.locator("[data-testid=mix-add-prompt]").fill("rain on a window, no music")
        page.locator("[data-testid=mix-add-submit]").click()
        page.wait_for_function("(n) => document.querySelectorAll('li[data-testid^=track-]').length === n + 1", arg=n0, timeout=15000)
        # edit the level of the first track and save
        first = page.locator("li[data-testid^=track-]").first
        tid = first.get_attribute("data-testid").split("-")[1]
        first.get_by_label(re.compile("بلندی|Level")).fill("-30")
        with sent(page, "PATCH", f"/api/mix-tracks/{tid}"):
            first.get_by_role("button", name=LABEL_SAVE).click()
        assert [t for t in api.get(f"/api/episodes/{ep_id}/mix")["tracks"] if str(t["id"]) == tid][0]["gain_db"] == -30
        # generate everything planned: the job runs the (fake) engines on the worker
        gen = page.locator("[data-testid=mix-generate]")
        assert gen.is_enabled()
        total = len(api.get(f"/api/episodes/{ep_id}/mix")["tracks"])
        gen.click()
        page.wait_for_function("(n) => document.querySelectorAll('audio[data-testid^=track-audio-]').length >= n", arg=total, timeout=180000)
        assert all(a.get_attribute("src").startswith("/media/") for a in page.locator("audio[data-testid^=track-audio-]").all())
        assert {t["status"] for t in api.get(f"/api/episodes/{ep_id}/mix")["tracks"]} == {"ready"}
        # a new description of a ready track needs new audio: it goes back to "planned"
        first = page.locator(f"li[data-testid=track-{tid}]")
        first.get_by_label(re.compile("توضیح برای مولد|Description for the generator")).fill("something else")
        with sent(page, "PATCH", f"/api/mix-tracks/{tid}"):
            first.get_by_role("button", name=LABEL_SAVE).click()
        assert [t for t in api.get(f"/api/episodes/{ep_id}/mix")["tracks"] if str(t["id"]) == tid][0]["status"] == "planned"
        # delete with confirmation
        n = page.locator("li[data-testid^=track-]").count()
        page.locator("li[data-testid^=track-]").last.get_by_role("button", name=re.compile("حذف ترک|Delete track")).click()
        page.get_by_role("dialog").get_by_role("button", name=re.compile("حذف ترک|Delete track")).click()
        page.wait_for_function("(n) => document.querySelectorAll('li[data-testid^=track-]').length === n - 1", arg=n, timeout=15000)
    finally:
        finish(ctx, problems, f"mix flow {lang}")
        clear_mix(api, ep_id)
        api.put(f"/api/pages/{anime['page']}/profiles/audio", audio_before)
        api.patch(f"/api/shots/{shot['id']}", {"sfx": shot.get("sfx") or ""})


# ------------------------------------------------------------------ automation + publishing
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_automation_page_renders_every_section(browser, server, fresh_page, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/automation" + fresh_page["query"], lang)
    try:
        page.locator("[data-testid=au-levels]").wait_for(timeout=20000)
        assert page.locator("input[name=automation-level]").count() == 3
        assert page.locator("input[name=automation-level]:checked").evaluate("e => e.parentElement.innerText").strip().startswith("دستی" if lang == "fa" else "Manual")
        assert page.locator("[data-testid=meter-gpu] [role=progressbar]").count() == 1 and page.locator("[data-testid=meter-api] [role=progressbar]").count() == 1
        assert page.locator("[data-testid=window-state]").is_visible()
        assert page.locator("[data-testid=slots] li").count() == 4                    # the next four publication slots
        assert page.locator("[data-testid=ap-state]").inner_text().strip() == ("خاموش" if lang == "fa" else "Off")
        assert page.locator("[data-testid=ap-enable]").is_disabled()                  # blocked until the sentence is typed
        assert page.locator("[data-testid=targets-empty]").is_visible()
        page.locator("[data-testid=instagram-requirements] summary").click()          # the account checklist is one click away
        assert page.locator("[data-testid=instagram-requirements] li").count() == 6
        phone_ok(page, f"automation {lang} {size}")
    finally:
        finish(ctx, problems, f"automation render {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_automation_level_budget_windows_persist_and_auto_publish_needs_the_sentence(browser, server, api, fresh_page, lang):
    pid = fresh_page["page"]
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/automation" + fresh_page["query"], lang)
    try:
        page.locator("[data-testid=au-levels]").wait_for(timeout=20000)
        # level: pick "assisted" -> saved on the server, still there after a reload
        with sent(page, "PUT", f"/api/pages/{pid}/automation"):
            page.locator("[data-testid=au-levels] label.choice").nth(1).click()
        assert api.get(f"/api/pages/{pid}/automation")["level"] == "assisted"
        page.reload()
        page.locator("[data-testid=au-levels]").wait_for(timeout=20000)
        assert page.locator("input[name=automation-level]:checked").evaluate("e => e.parentElement.innerText").strip().startswith("نیمه" if lang == "fa" else "Assisted")
        # budgets
        page.locator("[data-testid=budget-gpu]").fill("120")
        page.locator("[data-testid=budget-api]").fill("3.5")
        with sent(page, "PUT", f"/api/pages/{pid}/automation"):
            page.locator("[data-testid=budget-save]").click()
        saved = api.get(f"/api/pages/{pid}/automation")
        assert saved["gpu_minutes_per_week"] == 120 and saved["api_usd_per_week"] == 3.5
        wait_text(page, "[data-testid=meter-gpu]", "/ 120")                              # the meter follows the saved budget
        # render window: nights only on Saturday, Tehran offset
        page.locator("[data-testid=window-add]").click()
        page.locator("[data-testid=window-0] label.lab-day").first.click()
        page.locator("[data-testid=window-offset]").fill("210")
        with sent(page, "PUT", f"/api/pages/{pid}/automation"):
            page.locator("[data-testid=windows-save]").click()
        saved = api.get(f"/api/pages/{pid}/automation")
        assert saved["utc_offset_minutes"] == 210 and saved["render_windows"] == [{"days": ["sat"], "start": "22:00", "end": "07:00"}]
        # auto-publish: refused without the exact sentence, accepted with it, can be switched off again
        sentence = page.locator("[data-testid=ap-sentence]").inner_text().strip()
        enable = page.locator("[data-testid=ap-enable]")
        assert enable.is_disabled()
        page.locator("[data-testid=ap-confirm]").fill("yes I do")
        assert enable.is_disabled()
        page.locator("[data-testid=ap-confirm]").fill(sentence)
        assert enable.is_enabled()
        enable.click()
        page.locator("[data-testid=ap-disable]").wait_for(timeout=10000)
        assert page.locator("[data-testid=ap-state]").inner_text().strip() == ("روشن" if lang == "fa" else "On")
        info = api.get(f"/api/pages/{pid}/automation")["auto_publish"]
        assert info["enabled"] and info["confirmed_at"] and info["can_post_now"] is False       # no API target, no flag: it still cannot post
        assert page.locator("[data-testid=ap-why-not]").is_visible()
        page.locator("[data-testid=ap-disable]").click()
        page.locator("[data-testid=ap-enable]").wait_for(timeout=10000)
        assert api.get(f"/api/pages/{pid}/automation")["auto_publish"]["enabled"] is False
        # run the automation now: nothing to do on an empty page
        page.locator("[data-testid=au-tick]").click()
        page.locator("[data-testid=au-tick-result]").wait_for(timeout=15000)
    finally:
        finish(ctx, problems, f"automation settings {lang}")


@pytest.mark.parametrize("lang", LANGS)
def test_publishing_target_requirements_and_no_token_field(browser, server, api, fresh_page, lang):
    pid = fresh_page["page"]
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/automation" + fresh_page["query"], lang)
    try:
        page.locator("[data-testid=target-add]").click()
        page.locator("[data-testid=targets-empty]").wait_for(state="detached", timeout=15000)
        tid = api.get(f"/api/pages/{pid}/targets")[0]["id"]
        card = page.locator(f"[data-testid=target-{tid}]")
        card.wait_for(timeout=15000)
        assert page.locator(f"[data-testid=requirements-{tid}] li").count() == 1                     # manual export: nothing to set up
        assert page.locator(f"[data-testid=target-config-{tid}]").count() == 0                       # ... so no API fields
        page.locator(f"[data-testid=target-mode-{tid}]").select_option("api")
        cfg = page.locator(f"[data-testid=target-config-{tid}]")
        cfg.wait_for(timeout=5000)
        assert ".env" in cfg.inner_text()                                                            # the token lives in .env, never in the form
        assert cfg.locator("input[type=password]").count() == 0
        page.locator(f"[data-testid=cfg-ig-{tid}]").fill("1784")
        cfg.get_by_placeholder("https://media.example.org").fill("https://media.example.org")
        with sent(page, "PATCH", f"/api/targets/{tid}"):
            page.locator(f"[data-testid=target-save-{tid}]").click()
        saved = api.get(f"/api/targets/{tid}")
        assert saved["mode"] == "api" and saved["config"]["ig_user_id"] == "1784"
        # now the Instagram checklist (six requirements) is shown with what is met and what is missing
        page.locator(f"[data-testid=requirements-{tid}] li").nth(5).wait_for(timeout=15000)
        ok = {r["key"]: r["ok"] for r in api.get(f"/api/targets/{tid}")["requirements"]}
        assert ok["account"] and ok["public_url"] and ok["mode"] and not ok["flag"] and not ok["token"]
        assert T2[lang]["missing"] in page.locator(f"[data-testid=req-{tid}-flag]").inner_text()      # the feature flag is off by default
        assert T2[lang]["missing"] in page.locator(f"[data-testid=req-{tid}-token]").inner_text()
        assert T2[lang]["missing"] not in page.locator(f"[data-testid=req-{tid}-account]").inner_text()
        phone_ok(page, f"targets {lang}")
    finally:
        finish(ctx, problems, f"publishing target {lang}")


def test_publications_export_package_and_publish_needs_confirmation(browser, server, api, anime):
    if api.get(f"/api/episodes/{anime['episode']}")["state"] not in ("ready_for_approval", "approved", "scheduled", "published"):
        pytest.skip("the seeded episode did not reach ready_for_approval here")
    pub = api.post(f"/api/pages/{anime['page']}/publications", {"episode": anime["episode"], "caption": "نمونه"})
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/automation?page=" + str(anime["page"]), "en")
    try:
        row = page.locator(f"[data-testid=publication-{pub['id']}]")
        row.wait_for(timeout=20000)
        row.locator(f"[data-testid=pub-export-{pub['id']}]").click()
        row.locator("a[download]").wait_for(timeout=90000)
        assert [p for p in api.get(f"/api/pages/{anime['page']}/publications") if p["id"] == pub["id"]][0]["package_url"].endswith(".zip")
        # "Publish now" asks first; cancelling sends nothing
        row.locator(f"[data-testid=pub-publish-{pub['id']}]").click()
        dlg = page.get_by_role("dialog")
        assert "cannot be undone" in dlg.inner_text()
        dlg.get_by_role("button", name=re.compile("Cancel")).click()
        dlg.wait_for(state="detached", timeout=5000)
        assert api.get(f"/api/jobs?kind=publish.send&episode={anime['episode']}") == []
        phone_ok(page, "publications")
    finally:
        finish(ctx, problems, "publications")
        api.call("DELETE", f"/api/publications/{pub['id']}")


# ------------------------------------------------------------------ notifications
@pytest.fixture(scope="module")
def ready_page(server, api):
    """A page of its own with ONE episode at ready_for_approval (script, storyboard, preview video), so the real automation can be run on it without
    touching the seeded pages."""
    if not api.get("/api/health").get("ffmpeg"):
        pytest.skip("ffmpeg is not available here: no preview video to automate")
    strat = api.wait_job(api.post("/api/strategy", {"page_name": "اعلان", "format": "anime_whatif", "language": "fa", "idea": "ایده"}))["result"]["strategy"]
    page = api.post("/api/pages", {"name": f"اعلان {uuid.uuid4().hex[:4]}", "format": "anime_whatif", "languages": ["fa"], "idea": "ایده", "strategy": strat,
                                   "series": {**strat["series_ideas"][0], "episodes": 1}, "profiles": {"production": {"episode_length_sec": 20}}})
    sid = api.get(f"/api/pages/{page['id']}/series")[0]["id"]
    plan = api.wait_job(api.post(f"/api/series/{sid}/plan", {"episodes_count": 1}))["result"]["plan"]
    ep = api.post(f"/api/series/{sid}/apply-plan", {"plan": plan})["episodes"][0]["id"]
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-script"))
    api.wait_job(api.post(f"/api/episodes/{ep}/approve-script")["job"])
    api.wait_job(api.post(f"/api/episodes/{ep}/generate-storyboard"))
    api.post(f"/api/episodes/{ep}/produce", {"mode": "preview"})
    end = time.time() + 240
    while time.time() < end and api.get(f"/api/episodes/{ep}")["state"] not in ("ready_for_approval", "quality_review", "failed"):
        time.sleep(1)
    if api.get(f"/api/episodes/{ep}")["state"] != "ready_for_approval":
        pytest.skip("the preview did not reach ready_for_approval here")
    return {"page": page["id"], "episode": ep}


@pytest.fixture
def notification(api, ready_page):
    """An unread notification made by the real automation: the automatic level with a tiny GPU budget refuses the final render and says so.
    The page goes back to manual afterwards."""
    api.post("/api/notifications/read", {"all": True})
    api.put(f"/api/pages/{ready_page['page']}/automation", {"level": "automatic", "gpu_minutes_per_week": 1})
    api.post("/api/automation/tick", {})
    api.put(f"/api/pages/{ready_page['page']}/automation", {"level": "manual", "gpu_minutes_per_week": 600})
    assert api.get("/api/notifications?unread=1")["unread"] >= 1
    yield
    api.post("/api/notifications/read", {"all": True})


@pytest.mark.parametrize("lang", LANGS)
def test_notification_bell_shows_the_count_lists_and_marks_read(browser, server, api, notification, lang):
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab", lang)
    try:
        page.wait_for_function("() => /[0-9۰-۹]/.test(document.querySelector('[data-testid=bell-count]')?.innerText || '')", timeout=20000)
        n = int(digits(page.locator("[data-testid=bell-count]").inner_text()))
        assert n == api.get("/api/notifications?unread=1")["unread"] and n >= 1
        page.locator("[data-testid=bell-button]").click()
        pop = page.locator("[data-testid=bell-popover]")
        pop.wait_for(timeout=5000)
        item = pop.locator("[data-testid^=bell-item-]").first
        assert "GPU" in item.inner_text()                                             # the backend's (Persian) text is shown as it is
        item.locator("[data-testid^=bell-read-]").click()
        page.wait_for_function("(n) => (document.querySelector('[data-testid=bell-count]')?.innerText || '').replace(/[۰-۹]/g, c => '۰۱۲۳۴۵۶۷۸۹'.indexOf(c)) !== String(n)", arg=n, timeout=15000)
        assert api.get("/api/notifications?unread=1")["unread"] == n - 1
    finally:
        finish(ctx, problems, f"bell {lang}")


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_notifications_page_lists_filters_and_marks_read(browser, server, api, notification, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/notifications", lang)
    try:
        lst = page.locator("[data-testid=notes-list]")
        lst.wait_for(timeout=20000)
        first = lst.locator("li[data-testid^=note-]").first
        assert first.locator(".badge").count() >= 2                                   # level + kind (+ "unread")
        assert first.get_by_role("button", name=re.compile("^(باز کردن|Open)$")).count() == 1       # the notice links to the episode
        phone_ok(page, f"notifications {lang} {size}")
        page.locator("[data-testid=notes-read-all]").click()
        page.get_by_text(T2[lang]["empty_notes"]).first.wait_for(timeout=15000)       # the unread filter is empty now
        assert api.get("/api/notifications?unread=1")["unread"] == 0
        page.get_by_role("button", name=re.compile("^(همه|All)$")).click()
        page.locator("[data-testid=notes-list] li[data-testid^=note-]").first.wait_for(timeout=10000)   # ... but they are still listed under "all"
    finally:
        finish(ctx, problems, f"notifications page {lang} {size}")


# ------------------------------------------------------------------ consistency
@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("lang", LANGS)
def test_consistency_page_honest_lora_note_and_failed_training_without_references(browser, server, api, char, lang, size):
    ctx, page, problems = open_lab(browser, server, size, "/lab/consistency" + char["query"], lang)
    try:
        panel = page.locator("[data-testid=lora-panel]")
        panel.wait_for(timeout=20000)
        assert T2[lang]["honest"] in panel.inner_text() and "12" in digits(panel.inner_text())        # the unverified / 12 GB warning
        assert page.locator("[data-testid=lora-empty]").is_visible()
        phone_ok(page, f"consistency {lang} {size}")
        if size == "desktop":
            page.locator("[data-testid=lora-train]").click()
            dlg = page.get_by_role("dialog")
            assert "12" in digits(dlg.inner_text())
            dlg.get_by_role("button", name=re.compile("آموزشِ LoRA|Train a LoRA")).click()
            # no approved reference image: the job fails and the row says why (nothing is faked)
            page.wait_for_function("() => /ناموفق|Failed/.test(document.querySelector('[data-testid^=lora-status-]')?.innerText || '')", timeout=90000)
            assert "approved reference" in page.locator("[data-testid=lora-panel]").inner_text()
        else:
            assert page.locator("[data-testid=lora-train]").is_enabled()
    finally:
        finish(ctx, problems, f"consistency {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_consistency_shot_render_quality_panel(browser, server, api, anime, lang):
    ch = api.post(f"/api/pages/{anime['page']}/characters", {"name": "ثبات " + uuid.uuid4().hex[:4], "role": "x"})
    ctx, page, problems = open_lab(browser, server, "desktop", "/lab/consistency" + anime["query"] + f"&character={ch['id']}", lang)
    try:
        panel = page.locator("[data-testid=renders-panel]")
        panel.wait_for(timeout=20000)
        rows = api.get(f"/api/episodes/{anime['episode']}/renders")
        if rows:
            assert page.locator("[data-testid=renders-table] tbody tr").count() == len(rows)
        else:
            assert ("شاتِ ویدئویی" in panel.inner_text()) if lang == "fa" else ("No registered video" in panel.inner_text())
        assert ("حدسیِ اولیه" in panel.inner_text()) if lang == "fa" else ("first guesses" in panel.inner_text())     # thresholds are labelled as unverified
    finally:
        finish(ctx, problems, f"renders panel {lang}")


# ------------------------------------------------------------------ phone width, every round-2 screen
@pytest.mark.parametrize("lang", LANGS)
def test_phone_width_has_no_horizontal_scroll_on_the_round2_screens(browser, server, anime, char, lang):
    routes = {"compare": "/lab/compare" + anime["query"], "retake": "/lab/retake" + anime["query"], "mix": "/lab/mix" + anime["query"],
              "automation": "/lab/automation?page=" + str(anime["page"]), "notifications": "/lab/notifications", "consistency": "/lab/consistency" + char["query"]}
    for name, path in routes.items():
        ctx, page, problems = open_lab(browser, server, "phone", path, lang)
        try:
            page.wait_for_load_state("networkidle")
            phone_ok(page, f"{name} {lang}")
            assert page.locator("html").get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
        finally:
            finish(ctx, problems, f"phone round2 {name} {lang}")
