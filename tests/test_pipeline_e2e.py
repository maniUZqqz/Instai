"""End-to-end with fake providers: page -> plan -> script -> storyboard -> keyframes + narration -> FFmpeg assembly -> a real mp4
that is probed. Needs a local ffmpeg (START.bat fetches one); skipped where there is none."""
from __future__ import annotations

import pytest

from tests.conftest import finish, run_jobs

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


def build_episode(api, worker, fmt="anime_whatif"):
    j = finish(api, worker, api.post("/api/strategy", {"page_name": "پیج", "format": fmt, "language": "fa", "idea": "ایده"}, format="json"))
    strat = j["result"]["strategy"]
    page = api.post("/api/pages", {"name": "پیج", "format": fmt, "languages": ["fa"], "idea": "ایده", "strategy": strat,
                                   "series": {**strat["series_ideas"][0], "episodes": 5},
                                   "profiles": {"production": {"episode_length_sec": 20}}}, format="json").json()
    sid = api.get(f"/api/pages/{page['id']}/series").json()[0]["id"]
    plan = finish(api, worker, api.post(f"/api/series/{sid}/plan", {"episodes_count": 5}, format="json"))["result"]["plan"]
    s = api.post(f"/api/series/{sid}/apply-plan", {"plan": plan}, format="json").json()
    ep_id = s["episodes"][0]["id"]
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/generate-script"))
    r = api.post(f"/api/episodes/{ep_id}/approve-script")
    finish(api, worker, type("R", (), {"status_code": 202, "content": b"", "json": lambda self: {"job": r.json()["job"]}})())
    finish(api, worker, api.post(f"/api/episodes/{ep_id}/generate-storyboard"))
    return page, sid, ep_id


def produce(api, worker, ep_id, mode):
    r = api.post(f"/api/episodes/{ep_id}/produce", {"mode": mode}, format="json")
    assert r.status_code == 202, r.content
    for _ in range(60):
        run_jobs(worker)
        ep = api.get(f"/api/episodes/{ep_id}").json()
        if ep["state"] in ("ready_for_approval", "quality_review", "failed"):
            return ep
    raise AssertionError(f"pipeline did not finish: {ep['state']} {ep.get('error')}")


def test_preview_render_end_to_end(api, worker, ffmpeg_available):
    from instai.render import ffmpeg

    page, sid, ep_id = build_episode(api, worker)
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    assert ep["state"] == "storyboarding" and len(shots) >= 3
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep["qc"]
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    assert (video["width"], video["height"]) == (360, 640) and video["codec"] == "h264"
    assert video["duration_sec"] > 5 and video["fps"] == 15
    assert video["loudness_lufs"] is not None and abs(video["loudness_lufs"] + 16) <= 4
    # the file really exists, is playable (ranges) and has audio + video
    from instai.assets.storage import storage
    from instai.assets.models import Asset

    a = Asset.objects.get(pk=video["id"])
    info = ffmpeg.probe(storage.path_for(a.path))
    assert info["has_audio"] and info["has_video"] and abs(info["duration"] - video["duration_sec"]) < 0.2
    resp = api.get(video["url"], HTTP_RANGE="bytes=0-99")
    assert resp.status_code == 206 and resp["Content-Range"].startswith("bytes 0-99/")
    # every shot has a keyframe with provenance, narration audio with metadata
    ep_shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    assert all(sh["keyframe"] and sh["keyframe"]["provenance"]["engine"] == "placeholder" for sh in ep_shots)
    assert all(sh["narration_asset"] and sh["narration_asset"]["duration_sec"] > 0.5 for sh in ep_shots)
    assert ep["cover_url"]
    names = {c["name"]: c for c in ep["qc"]["checks"]}
    assert names["video_stream"]["level"] == "ok" and names["audio_stream"]["level"] == "ok" and names["resolution"]["level"] == "ok"
    # the explicit state history
    events = [e["to"] for e in api.get(f"/api/episodes/{ep_id}/events").json()]
    for st in ("scripting", "script_review", "storyboarding", "asset_generation", "assembly", "quality_review", "ready_for_approval"):
        assert st in events, events


def test_editing_one_shot_regenerates_only_that_shot(api, worker, ffmpeg_available):
    from instai.assets.models import Asset

    page, sid, ep_id = build_episode(api, worker)
    produce(api, worker, ep_id, "preview")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    assert ep["stale"]["keyframes_preview"] == 0 and ep["stale"]["narration"] == 0
    before_kf = Asset.objects.filter(role="keyframe", episode_id=ep_id).count()
    before_nar = Asset.objects.filter(role="narration", episode_id=ep_id).count()
    before_render = Asset.objects.filter(role="render_clip", episode_id=ep_id).count()

    target = shots[1]
    r = api.patch(f"/api/shots/{target['id']}", {"image_prompt": "a completely different frame"}, format="json")
    assert r.status_code == 200
    ep = api.get(f"/api/episodes/{ep_id}").json()
    assert ep["stale"]["keyframes_preview"] == 1 and ep["stale"]["narration"] == 0, "only the edited shot is stale"

    ep = produce(api, worker, ep_id, "preview")
    assert Asset.objects.filter(role="keyframe", episode_id=ep_id).count() == before_kf + 1
    assert Asset.objects.filter(role="narration", episode_id=ep_id).count() == before_nar, "narration is reused"
    assert Asset.objects.filter(role="render_clip", episode_id=ep_id).count() == before_render + 1, "only one shot clip is re-rendered"
    cur = Asset.objects.filter(shot_id=target["id"], role="keyframe", is_current=True).get()
    assert cur.version == 2 and cur.parent_id is not None


def test_approved_assets_are_reused(api, worker, ffmpeg_available):
    from instai.assets.models import Asset

    page, sid, ep_id = build_episode(api, worker)
    produce(api, worker, ep_id, "preview")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shot = ep["scenes"][0]["shots"][0]
    assert api.post(f"/api/shots/{shot['id']}/approve", {}, format="json").json()["approved"] is True
    # editing after approval makes the shot stale again (the approval belonged to the old prompt) ...
    api.patch(f"/api/shots/{shot['id']}", {"image_prompt": "changed after approval"}, format="json")
    assert api.get(f"/api/episodes/{ep_id}").json()["stale"]["keyframes_preview"] == 1
    # ... but if the owner approves the existing image anyway, it is kept and never regenerated
    api.post(f"/api/shots/{shot['id']}/approve", {}, format="json")
    assert api.get(f"/api/episodes/{ep_id}").json()["stale"]["keyframes_preview"] == 0
    n = Asset.objects.filter(role="keyframe", shot_id=shot["id"]).count()
    produce(api, worker, ep_id, "preview")
    assert Asset.objects.filter(role="keyframe", shot_id=shot["id"]).count() == n, "an approved keyframe is reused, never regenerated"


def test_final_mode_is_full_size_and_approval_flow(api, worker, ffmpeg_available):
    page, sid, ep_id = build_episode(api, worker, fmt="recurring_character")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    # shrink to 3 short shots so a 1080x1920 render stays quick on any PC
    sb = {"scenes": [{"title": "s", "shots": [{"description": f"d{i}", "image_prompt": f"p{i}", "technique": "still_kenburns", "duration_sec": 2.5,
                                                "camera": {"move": m, "intensity": 0.6}, "narration": f"این جمله‌ی شماره {i} است", "transition": t}
                                               for i, (m, t) in enumerate([("zoom_in", "crossfade"), ("pan_left", "cut"), ("zoom_out", "cut")], 1)]}]}
    r = api.put(f"/api/episodes/{ep_id}/storyboard", sb, format="json")
    assert r.status_code == 200, r.content
    ep = produce(api, worker, ep_id, "final")
    v = next(x for x in ep["videos"] if x["role"] == "final")
    assert (v["width"], v["height"], v["fps"]) == (1080, 1920, 30)
    assert api.post(f"/api/episodes/{ep_id}/approve").json()["state"] == "approved"
    assert api.post(f"/api/episodes/{ep_id}/revoke").json()["state"] == "ready_for_approval"
    # publishing: a manual-export package, never an auto post
    pub = api.post(f"/api/pages/{page['id']}/publications", {"episode": ep_id, "caption": "متن", "hashtags": ["انیمه"]}, format="json").json()
    j = finish(api, worker, api.post(f"/api/publications/{pub['id']}/export"))
    assert j["result"]["size_bytes"] > 1000
    import zipfile
    from instai.assets.models import Asset
    from instai.assets.storage import storage

    z = zipfile.ZipFile(storage.path_for(Asset.objects.get(pk=j["result"]["package_asset_id"]).path))
    assert {"caption.txt", "hashtags.txt", "README.txt", "cover.png"} <= set(z.namelist())
    assert any(n.endswith(".mp4") for n in z.namelist())
