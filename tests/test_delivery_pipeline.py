"""Delivery in the real pipeline (0.15), with the fake providers: a final render lands within 0.8 LU of its page's target and under -1 dBTP (new pages -14, a page that was saved with
-16 keeps -16), the loudness numbers are kept on the final Asset and shown in the quality panel, and the sound checks name nothing on a clean episode. The old pages keep their
target through the data migration."""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from instai.assets.models import Asset  # noqa: E402
from instai.render import loudness  # noqa: E402
from tests.conftest import finish  # noqa: E402
from tests.test_pipeline_e2e import build_episode, produce  # noqa: E402

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]

SHORT_SHOTS = {"scenes": [{"title": "s", "shots": [
    {"description": f"d{i}", "image_prompt": f"p{i}", "technique": "still_kenburns", "duration_sec": 2.5, "camera": {"move": m, "intensity": 0.6},
     "narration": f"این جمله‌ی شماره {i} است و کمی طولانی‌تر می‌شود تا گفتار پیوسته باشد", "transition": t}
    for i, (m, t) in enumerate([("zoom_in", "crossfade"), ("pan_left", "cut"), ("zoom_out", "cut")], 1)]}]}


def final_of(api, ep_id):
    ep = api.get(f"/api/episodes/{ep_id}").json()
    return ep, next(v for v in ep["videos"] if v["role"] == "final")


def rows(ep):
    return {c["name"]: c for c in ep["qc"]["checks"]}


def test_a_final_render_lands_on_the_pages_target_and_the_numbers_are_kept_and_shown(api, worker, ffmpeg_available):
    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    assert api.put(f"/api/episodes/{ep_id}/storyboard", SHORT_SHOTS, format="json").status_code == 200
    # a page made now is a -14 page (nothing was saved for its audio profile)
    ep = produce(api, worker, ep_id, "final")
    assert ep["state"] == "ready_for_approval", ep["qc"]
    v = next(x for x in ep["videos"] if x["role"] == "final")
    assert abs(v["loudness_lufs"] + 14.0) <= 0.8, v["loudness_lufs"]
    prov = Asset.objects.get(pk=v["id"]).provenance
    lo = prov["loudness"]
    assert lo["target"] == -14.0 and lo["ok"] is True and abs(lo["lufs"] + 14.0) <= 0.8 and lo["tp"] <= -0.95 and "before" in lo and prov["target_lufs"] == -14.0
    assert prov["audio_qc"]["ok"] is True and prov["audio_qc"]["problems"] == [], prov["audio_qc"]
    r = rows(ep)
    # the quality panel: loudness with before/after, the true peak, and the three sound checks - each with Persian AND English text
    assert r["loudness"]["level"] == "ok" and r["loudness"]["value"]["target"] == -14.0 and "هدف" in r["loudness"]["message"] and "target -14" in r["loudness"]["message_en"]
    assert r["true_peak"]["level"] == "ok" and r["true_peak"]["value"] <= -0.95
    for name in ("audio_echo", "audio_masking", "audio_phase"):
        assert r[name]["level"] == "ok" and r[name]["message"] and r[name]["message_en"], name
    assert all(c["message_en"] for c in ep["qc"]["checks"] if c["name"] not in ("script", "continuity", "voice_licence", "open_threads", "claims"))
    assert not [c for c in ep["qc"]["checks"] if c["level"] == "fail"]


def test_a_page_saved_at_minus_16_keeps_minus_16_until_its_owner_changes_it(api, worker, ffmpeg_available):
    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    api.put(f"/api/episodes/{ep_id}/storyboard", SHORT_SHOTS, format="json")
    assert api.put(f"/api/pages/{page['id']}/profiles/audio", {"target_lufs": -16}, format="json").status_code == 200
    ep = produce(api, worker, ep_id, "final")
    ep_, v = final_of(api, ep_id)
    assert abs(v["loudness_lufs"] + 16.0) <= 0.8, v["loudness_lufs"]
    assert Asset.objects.get(pk=v["id"]).provenance["loudness"]["target"] == -16.0
    assert rows(ep_)["loudness"]["value"]["target"] == -16.0
    # the owner changes it to the new default: the same episode is assembled again (the target is part of the timeline hash) and lands on -14
    assert api.put(f"/api/pages/{page['id']}/profiles/audio", {"target_lufs": -14}, format="json").status_code == 200
    produce(api, worker, ep_id, "final")
    assert abs(final_of(api, ep_id)[1]["loudness_lufs"] + 14.0) <= 0.8


def test_the_switch_off_leaves_the_render_s_own_loudness_and_a_preview_is_not_settled(api, worker, ffmpeg_available):
    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    api.put(f"/api/episodes/{ep_id}/storyboard", SHORT_SHOTS, format="json")
    ep = produce(api, worker, ep_id, "preview")
    pv = next(x for x in ep["videos"] if x["role"] == "preview")
    assert Asset.objects.get(pk=pv["id"]).provenance["loudness"] == {"skipped": "preview"}
    assert rows(ep)["loudness"]["level"] == "ok" and "value" in rows(ep)["loudness"]
    api.put(f"/api/pages/{page['id']}/profiles/audio", {"loudness_settle": False}, format="json")
    produce(api, worker, ep_id, "final")
    ep, fv = final_of(api, ep_id)
    assert Asset.objects.get(pk=fv["id"]).provenance["loudness"] == {"skipped": "off"} and rows(ep)["loudness"]["level"] in ("ok", "warn")
    # the switch is part of the timeline hash only when it is OFF: a page with the default keeps the hash it always had
    from instai.production import pipeline
    from instai.story.models import Episode

    e = Episode.objects.get(pk=ep_id)
    off = pipeline.timeline_hash(e, "final")
    api.put(f"/api/pages/{page['id']}/profiles/audio", {"loudness_settle": True}, format="json")
    assert pipeline.timeline_hash(Episode.objects.get(pk=ep_id), "final") != off


def test_music_and_effects_are_mixed_and_checked_with_real_stems(api, worker, ffmpeg_available):
    """The fake engines' music bed and effect over the fake narration, through the real assembly: the stems of the episode are rendered and compared shot by shot. The
    default plan (bed -22 dB ducked, effect -12 dB) must leave the voice above both: this is the calibration of the 6 dB line on InstAI's own mixes."""
    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    api.put(f"/api/episodes/{ep_id}/storyboard", SHORT_SHOTS, format="json")
    api.put(f"/api/pages/{page['id']}/profiles/audio", {"music_enabled": True, "sfx_enabled": True, "music_mood": "epic"}, format="json")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    api.patch(f"/api/shots/{ep['scenes'][0]['shots'][1]['id']}", {"sfx": "heavy door slam"}, format="json")
    api.post(f"/api/episodes/{ep_id}/mix/plan", {}, format="json")
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/mix/generate", {}, format="json"))
    produce(api, worker, ep_id, "final")
    ep, v = final_of(api, ep_id)
    aq = Asset.objects.get(pk=v["id"]).provenance["audio_qc"]
    assert aq["masking"]["applicable"] is True and aq["masking"]["margin_db"] >= 6.0 and aq["masking"]["masked"] == [], aq["masking"]
    assert {w["group"] for w in aq["masking"]["windows"]} == {"ducked", "plain"} and aq["problems"] == []
    r = rows(ep)
    assert r["audio_masking"]["level"] == "ok" and "کمترین فاصله" in r["audio_masking"]["message"] and "smallest margin" in r["audio_masking"]["message_en"]
    assert abs(v["loudness_lufs"] + 14.0) <= 0.8


def test_the_qc_of_an_old_render_without_the_new_numbers_still_works(api, worker, ffmpeg_available):
    """A render made before 0.15 has no `loudness` / `audio_qc` in its provenance: the panel keeps the old loose limit and the sound checks run on the file itself."""
    from instai.production import pipeline
    from instai.story.models import Episode

    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    api.put(f"/api/episodes/{ep_id}/storyboard", SHORT_SHOTS, format="json")
    produce(api, worker, ep_id, "final")
    ep, v = final_of(api, ep_id)
    a = Asset.objects.get(pk=v["id"])
    a.provenance = {k: x for k, x in a.provenance.items() if k not in ("loudness", "audio_qc", "target_lufs")}
    a.save()
    report = pipeline.run_qc(Episode.objects.get(pk=ep_id), a)
    by = {c["name"]: c for c in report["checks"]}
    assert by["loudness"]["level"] == "ok" and "true_peak" not in by and {"audio_echo", "audio_masking", "audio_phase"} <= set(by)
    assert loudness.PROFILES["social"]["lufs"] == -14.0
