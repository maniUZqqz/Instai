"""The scene-plan block on the storyboard card of a motion-graphics shot (0.18.0): the scenes, the live preview in the series' look, a request in plain words, undo, in Persian and in English,
on a desktop and on a phone. Needs the built UI (python scripts/build_ui.py --force) like every test in this folder."""
from __future__ import annotations

import pytest

from tests_ui.conftest import Api
from tests_ui.test_qa_sweep import SHOTS, visit


def make_motion_shot(seeded) -> tuple[int, int]:
    api: Api = seeded["api"]
    ep = seeded["anime_whatif"]["episodes"][0]
    shot = api.get(f"/api/episodes/{ep}")["scenes"][0]["shots"][0]
    api.patch(f"/api/shots/{shot['id']}", {"technique": "motion_graphics", "narration": "آب روی زمین ۷۱ درصد سطح را پوشانده است. ابتدا بخار می‌شود، سپس ابر می‌سازد و در نهایت باران می‌شود."})
    api.wait_job(api.post(f"/api/shots/{shot['id']}/motion", {"action": "write"}))
    return ep, shot["id"]


@pytest.mark.parametrize("lang,size,ask", [("fa", "desktop", "تیتر بزرگ‌تر شود"), ("en", "desktop", "make the title bigger"), ("fa", "phone", "صحنهٔ اول ۱ ثانیه بیشتر")])
def test_the_plan_of_a_motion_shot_is_shown_and_edited_by_words(browser, server, seeded, lang, size, ask):
    ep, shot_id = make_motion_shot(seeded)
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx, page, problems = visit(browser, server, f"/episodes/{ep}#storyboard", size, lang)
    try:
        page.wait_for_selector("[data-testid=mp-block]", timeout=20000)
        page.wait_for_selector("[data-testid=mp-scenes] >> text=/./", timeout=20000)
        assert page.locator("[data-testid=mp-scenes] > *").count() >= 1
        page.wait_for_function("() => document.querySelector('[data-testid=mp-player]').innerText.trim().length > 3", timeout=20000)      # the live preview draws the text of the plan
        before = page.locator("[data-testid=mp-scenes]").inner_text()
        n0 = int(page.locator("[data-testid=mp-versions]").get_attribute("data-count") or 0) if page.locator("[data-testid=mp-versions]").count() else 1
        page.fill("[data-testid=mp-ask]", ask)
        page.click("[data-testid=mp-apply]")
        page.wait_for_selector("[data-testid=mp-said]", timeout=20000)
        assert page.locator("[data-testid=mp-said]").inner_text().strip(), "the answer says what changed"
        page.wait_for_function("n => { const v = document.querySelector('[data-testid=mp-versions]'); return v && Number(v.getAttribute('data-count')) > n }", arg=n0, timeout=20000)      # a new version
        changed = page.locator("[data-testid=mp-scenes]").inner_text()
        page.click("[data-testid=mp-undo]")
        page.wait_for_function("() => !document.querySelector('[data-testid=mp-redo]').disabled", timeout=20000)      # the undone version can be redone
        assert page.locator("[data-testid=mp-scenes]").inner_text() == before, "undo brings the old plan back"
        page.click("[data-testid=mp-redo]")
        page.wait_for_function("() => document.querySelector('[data-testid=mp-redo]').disabled", timeout=20000)
        assert page.locator("[data-testid=mp-scenes]").inner_text() == changed, "redo brings the change back"
        page.screenshot(path=str(SHOTS / f"motion-plan-card-{lang}-{size}.png"))
        assert not [p for p in problems if "favicon" not in p], problems[:5]
        head = page.locator("[data-testid=mp-block] .strong").first.inner_text()
        assert head == ("طرح صحنهٔ گرافیک متحرک" if lang == "fa" else "Motion-graphics scene plan"), head
    finally:
        ctx.close()
