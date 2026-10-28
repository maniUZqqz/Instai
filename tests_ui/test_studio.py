"""Studio screens (hub, workers, voices, rigs) in Persian and English at desktop and phone width: texts and direction, real flows against the
running server (pairing code, LAN switch, voice casting with licence warnings, consent-gated references, rig create/edit/approve/preview),
no console errors, no failed requests, no horizontal page scroll. Seeds through the API of the running server (see conftest.Api)."""
from __future__ import annotations

import re
import uuid

import pytest

from tests_ui.conftest import Api
from tests_ui.studio_helpers import PERSIAN, SHOTS, digits, hscroll, open_studio, tone_wav

LANGS = ["fa", "en"]
SIZES = ["desktop", "phone"]
DEMO_TEXT = {  # a few words that must come out in the right language
    "fa": {"hub": "استودیو", "workers": "رایانه‌های کارگر", "local": "این رایانه", "pocket_warn": "غیرتجاری", "edge_warn": "غیررسمی", "approved": "تأییدشده"},
    "en": {"hub": "Studio", "workers": "Worker PCs", "local": "This PC", "pocket_warn": "NON-COMMERCIAL", "edge_warn": "unofficial", "approved": "Approved"},
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
    ctx, page, problems = open_studio(browser, server, size, "/studio", lang)
    try:
        html = page.locator("html")
        assert html.get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
        assert html.get_attribute("lang") == lang
        assert page.locator("main h1").inner_text().strip() == DEMO_TEXT[lang]["hub"]
        if lang == "fa":
            assert PERSIAN.search(page.locator("main").inner_text())
        for key in ("workers", "voices", "rigs"):
            tile = page.locator(f"[data-testid=tile-{key}]")
            assert tile.get_attribute("href") == f"/studio/{key}"
        for key in ("comparison", "retake", "scheduler", "publishing", "notifications"):
            tile = page.locator(f"[data-testid=tile-{key}]")
            assert tile.get_attribute("aria-disabled") == "true" and tile.get_attribute("href") is None
        assert page.locator("nav.nav a[href='/studio']").count() == 1           # the sidebar entry
        assert hscroll(page)[0] <= hscroll(page)[1] + 1
        page.screenshot(path=str(SHOTS / f"studio-hub-{lang}-{size}.png"))
        page.locator("[data-testid=tile-workers]").click()
        page.wait_for_url(re.compile(r"/studio/workers$"))
        assert page.locator("main h1").inner_text().strip() == DEMO_TEXT[lang]["workers"]
        page.go_back()
        page.wait_for_url(re.compile(r"/studio$"))
        page.locator("[data-testid=tile-voices]").click()
        page.wait_for_url(re.compile(r"/studio/voices$"))
        page.go_back()
        page.locator("[data-testid=tile-rigs]").click()
        page.wait_for_url(re.compile(r"/studio/rigs$"))
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
    ctx, page, problems = open_studio(browser, server, size, "/studio/workers", lang)
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
        page.screenshot(path=str(SHOTS / f"studio-workers-{lang}-{size}.png"))
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
    ctx, page, problems = open_studio(browser, server, "desktop", "/studio/workers", lang)
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
    ctx, page, problems = open_studio(browser, server, size, "/studio/voices" + char["query"], lang)
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
        page.screenshot(path=str(SHOTS / f"studio-voices-{lang}-{size}.png"))
    finally:
        finish(ctx, problems, f"voices engines {lang} {size}")


@pytest.mark.parametrize("lang", LANGS)
def test_casting_edge_for_english_shows_the_warning_and_persists(browser, server, api, char, lang):
    ctx, page, problems = open_studio(browser, server, "desktop", "/studio/voices" + char["query"], lang)
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
    ctx, page, problems = open_studio(browser, server, "desktop", "/studio/voices" + char["query"], "en")
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
    ctx, page, problems = open_studio(browser, server, "desktop", "/studio/voices" + char["query"], "en")
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
    ctx, page, problems = open_studio(browser, server, "desktop", "/studio/rigs" + char["query"], lang)
    try:
        page.locator("[data-testid=rig-create-demo]").click()
        page.locator("[data-testid^=completeness-]").first.wait_for(timeout=30000)
        rig_id = int(page.locator("[data-testid^=completeness-]").first.get_attribute("data-testid").split("-")[1])
        assert digits(page.locator(f"[data-testid=mouth-count-{rig_id}]").inner_text()).replace(" ", "") == "9/9"
        assert page.locator(f"[data-testid=completeness-{rig_id}] .studio-mouths li.studio-chip-ok").count() == 9
        assert page.locator(f"[data-testid=rig-{rig_id}] .studio-thumbs img").count() == 18          # the demo character has 18 parts
        # edit a pivot of the right arm and save
        page.locator(f"[data-testid=parts-{rig_id}] summary").click()
        px = page.locator(f"[data-testid=parts-{rig_id}] input[aria-label^='arm_r'][aria-label$=' x']").first
        px.fill("")
        px.fill("41")
        save = page.locator(f"[data-testid=parts-save-{rig_id}]")
        assert save.is_enabled()
        save.click()
        page.wait_for_function("(id) => document.querySelector(`[data-testid=parts-save-${id}]`).disabled", arg=rig_id)
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
        page.screenshot(path=str(SHOTS / f"studio-rigs-{lang}-desktop.png"), full_page=True)
    finally:
        finish(ctx, problems, f"rigs {lang}")


@pytest.mark.parametrize("lang", LANGS)
def test_phone_width_has_no_horizontal_scroll_on_every_studio_screen(browser, server, api, char, lang):
    api.post(f"/api/characters/{char['character']}/rigs", {"source": "demo"})
    shots = {"hub": "/studio", "workers": "/studio/workers", "voices": "/studio/voices" + char["query"], "rigs": "/studio/rigs" + char["query"]}
    SHOTS.mkdir(parents=True, exist_ok=True)
    for name, path in shots.items():
        ctx, page, problems = open_studio(browser, server, "phone", path, lang)
        try:
            if name == "rigs":
                page.locator("[data-testid^=completeness-]").first.wait_for(timeout=20000)
                page.locator("[data-testid^=parts-] summary").first.click()          # the widest element: the parts table
            if name == "voices":
                page.locator("[data-testid=cast-en]").wait_for(timeout=20000)
            sw, iw = hscroll(page)
            assert sw <= iw + 1, f"{name} {lang}: horizontal scroll {sw} > {iw}"
            assert page.locator("html").get_attribute("dir") == ("rtl" if lang == "fa" else "ltr")
            page.screenshot(path=str(SHOTS / f"studio-{name}-{lang}-phone.png"), full_page=False)
        finally:
            finish(ctx, problems, f"phone {name} {lang}")
