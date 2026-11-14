"""The automatic self-test of this PC on the System screen and as a line on the home screen (0.14.0), in Persian (RTL) and English (LTR), desktop and phone:
the card is there, the button runs it, every check shows its verdict with a reason in the right language, the ones that wait say so (and nothing says "all sound" while
something waits), no horizontal scroll, no stray Persian in English. The server of these tests has no GPU and no Ollama: those checks must WAIT, never fail."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests_ui.test_screens import PERSIAN, SHOTS, open_page  # noqa: E402

KEYS = ["database", "disk", "ffmpeg", "persian_text", "update_channel", "autostart", "remotion_toolchain", "remotion_render", "motion_library", "motion_frames", "gpu_card", "nvenc", "ollama_run", "comfyui", "motion_critique"]
GPU = ["gpu_card", "nvenc", "ollama_run", "comfyui"]


def run_and_wait(page):
    page.get_by_test_id("pc-selftest-run").click()
    page.wait_for_function("document.querySelector('[data-testid=pc-check-database]') !== null", timeout=180000)
    page.wait_for_function("document.querySelector('[data-testid=pc-selftest-run]') && !document.querySelector('[data-testid=pc-selftest-run]').disabled", timeout=180000)


@pytest.mark.parametrize("lang", ["fa", "en"])
@pytest.mark.parametrize("size", ["desktop", "phone"])
def test_the_system_screen_shows_the_pc_selftest_and_runs_it(browser, server, lang, size):
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = open_page(browser, server, size, "/system", lang)
    try:
        card = page.get_by_test_id("pc-selftest")
        card.wait_for(timeout=30000)
        run_and_wait(page)
        for k in KEYS:
            row = page.get_by_test_id(f"pc-check-{k}")
            assert row.count() == 1, f"no row for {k}"
            assert row.get_attribute("data-verdict") in ("ok", "warn", "fail", "skip", "pending"), k
            assert row.inner_text().strip(), k
        verdicts = {k: page.get_by_test_id(f"pc-check-{k}").get_attribute("data-verdict") for k in KEYS}
        assert verdicts["database"] == "ok" and verdicts["persian_text"] == "ok", verdicts
        assert all(verdicts[k] == "pending" for k in GPU), f"no GPU PC here: the GPU checks wait, they do not fail ({verdicts})"
        assert "fail" not in verdicts.values(), verdicts
        state = page.get_by_test_id("pc-selftest-state")
        assert state.get_attribute("data-state") in ("waiting", "attention"), state.get_attribute("data-state")
        body = card.inner_text()
        if lang == "fa":
            assert PERSIAN.search(body) and "منتظر" in body, body[:300]
            assert "همه‌چیز سالم" not in body, "never 'all sound' while checks wait"
        else:
            assert "Waiting" in body and "All sound" not in body
            assert not PERSIAN.search(body.replace("فارسی", "")), "stray Persian in the English card: " + body[:200]
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        assert sw <= iw + 1, f"horizontal scroll {sw} > {iw}"
        page.screenshot(path=str(SHOTS / f"pc-selftest-{lang}-{size}.png"))
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


@pytest.mark.parametrize("lang", ["fa", "en"])
def test_the_home_screen_has_one_line_that_leads_to_the_details(browser, server, lang):
    ctx, page, problems = open_page(browser, server, "desktop", "/", lang)
    try:
        strip = page.get_by_test_id("pc-selftest-strip")
        strip.wait_for(timeout=30000)
        text = strip.inner_text()
        assert text.strip()
        strip.get_by_role("link").click()
        page.wait_for_url("**/system", timeout=20000)
        page.get_by_test_id("pc-selftest").wait_for(timeout=30000)
        assert not [p for p in problems if "favicon" not in p], problems
    finally:
        ctx.close()


def test_the_api_report_matches_what_the_screen_shows(server):
    import json
    import time
    import urllib.request

    def call(method, path, body=None):
        req = urllib.request.Request(server + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())

    call("POST", "/api/system/selftest", {})
    end = time.time() + 180
    d = call("GET", "/api/system/selftest")
    while time.time() < end and (d["running"] or not d["report"]):
        time.sleep(2)
        d = call("GET", "/api/system/selftest")
    assert [c["key"] for c in d["checks"]] == KEYS
    rep = d["report"]
    assert rep and [r["key"] for r in rep["checks"]] == KEYS and rep["summary"]["fail"] == 0, rep and rep["summary"]
