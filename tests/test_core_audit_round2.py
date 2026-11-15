"""Audit batch "ia_core", second pass (2026-11-15): what a browser sweep of every Persian page still found after 0.15.0 -
the model-comparison page with English notes and a command line, the reason automatic posting is off, Latin digits in the quality check,
episode titles and the Remotion setup error, and the English reasons in an episode's history."""
from __future__ import annotations

import re

import pytest

from instai.core import fa_catalog as fc
from tests.test_core_audit import planned_episode, set_techniques, storyboard_episode          # noqa: F401 - the same fixtures' helpers
from tests.test_core_audit_catalog import english_or_command, get

pytestmark = pytest.mark.django_db(transaction=True)

LATIN_NUMBER = re.compile(r"(?<![\w.])[0-9]+(?:\.[0-9]+)?(?![\w.])")          # ASCII digits only: Python's \d also matches the Persian ones


# ------------------------------------------------------------------ the model-comparison page

def test_anime_candidates_are_persian_on_a_persian_page_and_untouched_in_english(api):
    fa = get(api, "/api/anime/candidates", "fa")
    en = get(api, "/api/anime/candidates", "en")
    assert english_or_command(fa) == [], english_or_command(fa)
    assert [c["id"] for c in fa] == [c["id"] for c in en] == ["wan22", "anisora", "animegen"]
    assert all(c["note"] and c["licence"] for c in fa)
    assert fa[0]["label"].endswith("مدل فعلی") and fa[0]["label_en"] == en[0]["label"] and "label_en" not in en[0]      # the card's heading has no English word either
    assert all("community" not in c["label"] for c in fa)
    ani_fa, ani_en = fa[1], en[1]
    assert ani_en["note"].startswith("Bilibili") and "note_en" not in ani_en           # the English answer is the original
    assert ani_fa["note_en"] == ani_en["note"] and not fc.looks_english(ani_fa["note"])   # the Persian one keeps it beside
    assert "ComfyUI-GGUF" in ani_fa["note"] and ani_fa["needs"] == ["ComfyUI-GGUF"]        # a product name and the machine-readable fields stay as they are


def test_every_anime_candidate_text_has_a_persian_twin():
    from instai.core import fa_catalog_data as D
    from instai.production import anime

    for c in anime.CANDIDATES:
        assert c["licence"] in D.LICENCE or not fc.looks_english(c["licence"]), c["id"]           # «Apache-2.0» alone is a name, not a sentence
        assert c["note"] in D.NOTE, c["id"]


# ------------------------------------------------------------------ the reason automatic posting is off

def test_why_not_has_a_persian_twin():
    from instai.publishing import adapters

    assert adapters.why_not_fa("automatic publishing is not enabled for this page") == "انتشار خودکار برای این صفحه روشن نشده است."
    assert adapters.why_not_fa("no API publish target") == "هدفِ انتشار از راهِ API تنظیم نشده است."
    assert adapters.why_not_fa("missing: token, flag") == "این موارد هنوز آماده نیست: token, flag"
    assert adapters.why_not_fa("") == ""


def test_the_automation_answer_carries_both_texts(api, worker):
    from tests.test_story_flow import make_page

    page = make_page(api, worker, "recurring_character", "گربه‌ی کارتونی و دردسرهای خانه")
    d = api.get(f"/api/pages/{page['id']}/automation").json()
    ap = d["auto_publish"]
    assert ap["why_not"] == "automatic publishing is not enabled for this page"
    assert ap["why_not_fa"] == "انتشار خودکار برای این صفحه روشن نشده است." and not fc.looks_english(ap["why_not_fa"])


# ------------------------------------------------------------------ Persian digits where the program writes the Persian sentence

def test_episode_titles_the_program_writes_have_persian_digits(api, worker):
    from instai.channel.planner import skeleton_season
    from tests.test_story_flow import make_page

    season = skeleton_season(3, 60, fa=True)
    assert [e["title"] for e in season["episodes"]] == ["قسمت ۱", "قسمت ۲", "قسمت ۳"]
    assert skeleton_season(2, 60, fa=False)["episodes"][0]["title"] == "Episode 1"           # English stays English
    page = make_page(api, worker, "recurring_character", "گربه‌ی کارتونی و دردسرهای خانه")
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    r = api.post(f"/api/series/{sid}/episodes", {"number": 7}, format="json")
    assert r.status_code == 201 and r.json()["title"] == "قسمت ۷", r.content


def test_the_plan_of_the_demo_model_has_persian_digits(api, worker):
    from tests.test_story_flow import make_page
    from tests.conftest import finish

    page = make_page(api, worker, "recurring_character", "گربه‌ی کارتونی و دردسرهای خانه")
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    j = finish(api, worker, api.post(f"/api/series/{sid}/plan", {"episodes_count": 3}, format="json"))
    titles = [e["title"] for e in j["result"]["plan"]["episodes"]]
    assert titles[:3] == ["قسمت ۱", "قسمت ۲", "قسمت ۳"], titles


def test_job_titles_the_program_writes_have_persian_digits(api, worker):
    ep_id = planned_episode(api, worker)
    r = api.post(f"/api/episodes/{ep_id}/generate-script", {}, format="json")
    assert r.status_code == 202, r.content
    title = r.json()["job"]["title"]
    assert re.search(r"قسمت [۰-۹]+", title) and not re.search(r"[0-9]", title), title


def test_the_quality_check_sentences_have_persian_digits(api, worker, ffmpeg_available):
    from tests.test_pipeline_e2e import produce

    page, sid, ep_id = storyboard_episode(api, worker)
    ep = produce(api, worker, ep_id, "preview")
    bad = [c["message"] for c in ep["qc"]["checks"] if LATIN_NUMBER.search(c["message"])]
    assert bad == [], bad                                                                  # «15.0 فریم بر ثانیه», «مدت 21.6 ثانیه», «0 رشته‌ی باز» ...
    assert any("فریم بر ثانیه" in c["message"] for c in ep["qc"]["checks"])
    assert all(not re.search(r"[۰-۹]", c["message_en"]) for c in ep["qc"]["checks"] if c.get("message_en"))      # the English twin keeps its own digits


# ------------------------------------------------------------------ the Remotion setup error

@pytest.mark.parametrize("english, must_have", [
    ("npm was not found next to Node.js", "npm"),
    ("Node.js 18 or newer was not found (the automatic portable download is for Windows). Install Node.js from nodejs.org.", "Node.js"),
    ("Node.js could not be downloaded (no internet, or nodejs.org and the mirror are blocked).", "اینترنت"),
    ("the npm packages could not be installed (npm exit code 1); see data/logs/remotion-setup.log", "گزارشِ نصب"),
    ("no Chrome / Chromium was found; install one or set INSTAI_BROWSER", "Chrome"),
    ("the Remotion renderer did not load: boom", "Remotion"),
    ("not enough free disk space on C: (1.5 GB free, 3.0 GB needed)", "۱٫۵"),
    ("something nobody wrote a twin for", "گزارشِ نصب"),
])
def test_remotion_setup_errors_are_one_persian_sentence(english, must_have):
    from instai.remotion import toolchain

    fa = toolchain.fa_reason(english)
    assert must_have in fa, fa
    assert not fc.looks_english(fa) and not fc.looks_like_command(fa) and "data/logs" not in fa, fa
    assert toolchain.fa_reason("") == ""


def test_the_remotion_status_says_the_error_in_persian_and_keeps_the_english_line(monkeypatch):
    from instai.remotion import toolchain

    m = toolchain.setup_module()
    monkeypatch.setattr(m, "read_status", lambda: {"state": "error", "error": "npm was not found next to Node.js", "message_fa": "نصب Remotion کامل نشد: npm was not found next to Node.js"})
    toolchain.clear_cache()
    st = toolchain.status()
    if st["state"] != "error":
        pytest.skip("a ready Remotion toolchain on this machine overrides a saved error")
    assert st["error"] == "npm was not found next to Node.js" and "npm" in st["error_fa"] and not fc.looks_english(st["message_fa"])
    assert st["message_en"] == "" or "npm" in st["message_en"]                              # the English text is the saved one, not rewritten


def test_the_pc_self_test_row_for_a_failed_remotion_setup_is_persian(monkeypatch, tmp_path):
    from instai.ops import pcselftest
    from instai.remotion import toolchain

    base = {"ready": False, "node": None, "packages": False, "browser": None, "state": "error", "phase": "", "message_fa": "", "message_en": "", "auto": True}
    english = "npm was not found next to Node.js"
    monkeypatch.setattr(toolchain, "status", lambda: {**base, "error": english, "error_fa": toolchain.fa_reason(english)})
    row = pcselftest.check_remotion_toolchain(tmp_path)
    assert row["verdict"] == "fail" and "npm" in row["reason_fa"] and not fc.looks_english(row["reason_fa"]) and not fc.looks_like_command(row["reason_fa"])
    assert english in row["reason_en"] or "npm" in row["reason_en"]
