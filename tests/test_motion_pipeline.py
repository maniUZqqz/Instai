"""The `motion_graphics` technique in the production pipeline: a motion shot gets a scene plan from its narration, the plan is checked, a `remotion.render` job per shot draws the clip, the clip
is registered as the shot's `shot_clip` and the assembly uses it (no Ken Burns note). The Node side is a Python stand-in that makes REAL mp4 clips with ffmpeg (so the assembly is real);
the real Remotion render of every component in every size is `test_real_toolchain_every_component_in_three_sizes` (INSTAI_REMOTION_REAL=1, on a PC that has run scripts/setup_remotion.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from django.utils import timezone

from tests.conftest import finish, run_jobs
from tests.test_pipeline_e2e import build_episode, produce

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]

FAKE_NODE = r'''
import json, os, subprocess, sys
job = json.load(open(sys.argv[1], encoding="utf-8"))
def ev(**k): print("INSTAI_REMOTION " + json.dumps(k), flush=True)
FF = os.environ["FAKE_FFMPEG"]
ev(event="phase", phase="bundling"); ev(event="bundle", progress=100)
log = os.environ.get("FAKE_LOG")
if log:
    open(log, "a").write(json.dumps({"qa": bool(job.get("qa")), "composition": job.get("composition"), "scale": job.get("scale"), "crf": job.get("crf")}) + "\n")
if job.get("qa"):
    from PIL import Image
    out_dir = job["qa"]["out_dir"]; os.makedirs(out_dir, exist_ok=True)
    results = []
    for item in job["qa"]["items"]:
        spec = item["props"]["spec"]
        W, H = {"vertical": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}[item["props"].get("size", "vertical")]
        shots = []
        for f in item["frames"]:
            path = os.path.join(out_dir, f["name"] + ".jpg")
            Image.new("RGB", (W // 4, H // 4), (30, 40, 60)).save(path)
            boxes = [] if not os.environ.get("FAKE_OVERFLOW") else [{"id": 1, "kind": "text", "scene": int(f["name"].split("-s")[1].split("-")[0]), "role": "title", "size": 90, "x": -200, "y": 100, "w": 600, "h": 100, "color": "#ffffff",
                                                                    "text": "بیرون", "overflow": False, "clipped": False, "opacity": 1, "parent": -1, "overlay": "", "excl": ""}]
            shots.append({"name": f["name"], "frame": f["frame"], "image": path, "geometry": {"frame": f["frame"], "W": W, "H": H, "fps": 30, "platform": "", "safe": {}, "boxes": boxes}})
        results.append({"name": item["name"], "composition": item["composition"], "width": W, "height": H, "fps": 30, "frames": 300, "shots": shots})
        ev(event="qa_progress", done=len(shots), total=len(shots))
    json.dump(results, open(os.path.join(out_dir, "results.json"), "w"))
    ev(event="done", qa=True, out=os.path.join(out_dir, "results.json"))
    sys.exit(0)
spec = job["props"]["spec"]
secs = max(1.0, sum(float(s["duration"]) for s in spec["scenes"]))
size = job["props"].get("size", "vertical")
W, H = {"vertical": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}[size]
sc = float(job.get("scale") or 1)
W, H = int(W * sc) // 2 * 2, int(H * sc) // 2 * 2
ev(event="composition", id=job["composition"], width=W, height=H, fps=30, frames=int(secs * 30))
os.makedirs(os.path.dirname(job["out"]), exist_ok=True)
r = subprocess.run([FF, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:d={secs:.2f}:r=30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", job["out"]])
if r.returncode:
    ev(event="error", message="ffmpeg failed"); sys.exit(1)
for i in (1, 2, 3):
    ev(event="progress", rendered=i * 10, encoded=i * 10, frames=30, progress=i / 3)
ev(event="done", out=job["out"], width=W, height=H, fps=30, frames=int(secs * 30), seconds=0.5)
'''


@pytest.fixture
def toolchain_stub(tmp_path, monkeypatch, ffmpeg_available):
    from instai.jobs.handlers import remotion as h
    from instai.remotion import toolchain

    proj = tmp_path / "remotion"
    proj.mkdir()
    (proj / "render.mjs").write_text(FAKE_NODE, encoding="utf-8")
    state = {"ready": True, "kicks": 0}
    monkeypatch.setattr(toolchain, "PROJECT", proj)
    monkeypatch.setattr(toolchain, "work_dir", lambda: tmp_path / "work")
    monkeypatch.setattr(toolchain, "status", lambda: {"ready": state["ready"], "node": {"path": sys.executable, "version": "v24.0.0", "source": "portable"},
                                                      "browser": {"path": "C:\\Edge\\msedge.exe", "source": "system", "mode": "chrome-for-testing"}, "packages": True,
                                                      "state": "ready" if state["ready"] else "running", "message_fa": "در حال نصب ...", "message_en": "installing ..."})
    monkeypatch.setattr(h, "kick_setup", lambda: state.__setitem__("kicks", state["kicks"] + 1))
    monkeypatch.setenv("FAKE_FFMPEG", ffmpeg_available["ffmpeg"])
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.delenv("FAKE_OVERFLOW", raising=False)
    state["log"] = log
    return state


def motion_episode(api, worker, which=(0, 2)):
    """An explainer episode whose shots `which` are motion-graphics shots (the others keep their technique)."""
    from instai.story.models import Shot

    page, sid, ep_id = build_episode(api, worker, fmt="concept_explainer")
    shots = list(Shot.objects.filter(scene__episode_id=ep_id).order_by("scene__index", "index"))
    assert len(shots) >= 3
    for i in which:
        s = shots[i]
        s.technique = "motion_graphics"
        s.narration = s.narration or "این یک جملهٔ آزمایشی برای نما است. بخار می‌شود، سپس ابر می‌سازد و در نهایت باران می‌شود."
        s.save()
    shots = list(Shot.objects.filter(scene__episode_id=ep_id).order_by("scene__index", "index"))
    picked = [s for s in shots if s.technique == "motion_graphics"]           # the storyboard may have made some more
    assert len(picked) >= len(which)
    return ep_id, picked, shots


def calls(state) -> list:
    p = state["log"]
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_a_motion_shot_is_drawn_planned_checked_and_assembled_without_a_kenburns_fallback(api, worker, toolchain_stub):
    from instai.assets.models import Asset
    from instai.motion_plan import shots as motion
    from instai.motion_plan.models import MotionPlan
    from instai.jobs.models import Job

    ep_id, picked, shots = motion_episode(api, worker)
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep.get("qc")
    # no keyframe is made for a motion shot; the others have theirs
    for s in shots:
        kf = Asset.objects.filter(shot=s, role="keyframe", is_current=True).exists()
        assert kf == (s not in picked), (s.pk, s.technique, kf)
    # one remotion.render job per motion shot, each with a plan, a QA report and a registered clip
    jobs = list(Job.objects.filter(kind="remotion.render", episode_id=ep_id).order_by("id"))
    assert len(jobs) == len(picked) and all(j.status == Job.SUCCEEDED and j.payload["shot_id"] for j in jobs)
    for s in picked:
        plan = MotionPlan.objects.get(shot=s)
        assert plan.spec["scenes"] and plan.origin in ("ai", "fallback") and plan.qa.get("rounds") is not None and plan.qa["geometry"] is True
        clip = Asset.objects.get(shot=s, role="shot_clip", is_current=True)
        assert clip.kind == "video" and clip.provenance["engine"] == "remotion" and clip.provenance["plan_id"] == plan.pk and clip.input_hash == motion.clip_hash(plan, s, s.scene.episode, "preview")
        assert abs(clip.duration_sec - motion.target_seconds(s, s.scene.episode)) < 1.0, "the clip is as long as the speech"
    # the assembly used the clips: no «Ken Burns» note for the motion shots, and the episode's video carries the technique
    video = next(v for v in ep["videos"] if v["role"] == "preview")
    notes = Asset.objects.get(pk=video["id"]).provenance["notes"]
    assert not [n for n in notes if "motion" in n.lower() or "technique motion_graphics" in n or "not implemented" in n], notes
    assert "motion_graphics" in Asset.objects.get(pk=video["id"]).provenance["techniques"]
    c = calls(toolchain_stub)
    assert any(x["qa"] for x in c) and any(not x["qa"] and x["composition"] == "ScenePlan" for x in c)
    assert [x for x in c if not x["qa"]][0]["scale"] < 1, "the preview is drawn small"


def test_the_clip_waits_for_the_toolchain_and_an_edit_redraws_only_that_shot(api, worker, toolchain_stub):
    from instai.assets.models import Asset
    from instai.jobs.models import Job
    toolchain_stub["ready"] = False
    ep_id, picked, shots = motion_episode(api, worker)
    r = api.post(f"/api/episodes/{ep_id}/produce", {"mode": "preview"}, format="json")
    assert r.status_code == 202
    for _ in range(8):
        run_jobs(worker)
    waiting = Job.objects.filter(kind="remotion.render", episode_id=ep_id)
    assert waiting.count() == len(picked) and all(j.status == Job.QUEUED and j.wait_code == "remotion_setup" and j.attempts == 0 for j in waiting), [(j.status, j.wait_code) for j in waiting]
    assert toolchain_stub["kicks"] >= 1, "the setup starts by itself"
    assert api.get(f"/api/episodes/{ep_id}").json()["state"] == "asset_generation", "waiting is not failing"
    toolchain_stub["ready"] = True
    Job.objects.filter(pk__in=[j.pk for j in waiting]).update(run_after=timezone.now())
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep.get("qc")
    first = {s.pk: Asset.objects.get(shot=s, role="shot_clip", is_current=True) for s in picked}
    assert len(calls(toolchain_stub)) >= 2 * len(picked)
    # the owner edits the narration of ONE motion shot: only that clip is drawn again
    before = len([x for x in calls(toolchain_stub) if not x["qa"]])
    s0 = picked[0]
    s0.narration = "یک جملهٔ کاملاً تازه. و جملهٔ دوم."
    s0.save()
    from instai.motion_plan import shots as motion

    assert s0.pk in [s.pk for s in motion.missing(s0.scene.episode, "preview")], "the narration is stale, so is the clip that is as long as it"
    ep2 = produce(api, worker, ep_id, "preview")
    assert ep2["state"] == "ready_for_approval", ep2.get("qc")
    assert len([x for x in calls(toolchain_stub) if not x["qa"]]) - before == 1
    assert Asset.objects.get(shot=picked[1], role="shot_clip", is_current=True).pk == first[picked[1].pk].pk, "the other motion shot kept its clip"
    assert Asset.objects.get(shot=s0, role="shot_clip", is_current=True).pk != first[s0.pk].pk


def test_the_geometry_check_fixes_what_the_frames_show_and_the_plan_keeps_the_versions(api, worker, toolchain_stub, monkeypatch):
    from instai.motion_plan import plans, shots as motion
    from instai.motion_plan.models import MotionPlan

    monkeypatch.setenv("FAKE_OVERFLOW", "1")
    ep_id, picked, shots = motion_episode(api, worker, which=(0,))
    produce(api, worker, ep_id, "preview")
    plan = MotionPlan.objects.get(shot=picked[0])
    assert plan.qa["geometry"] is True and plan.qa["fixed"] >= 1 and plan.qa["rounds"], "the text that spilled out was shrunk"
    sources = [h["source"] for h in plans.history(plan)]
    assert "qa" in sources and plan.spec["scenes"][0].get("tokens", {}).get("font_scale", 1) < 1, (sources, plan.spec["scenes"][0])
    assert plan.qa["remaining"], "an overflow that the frames keep showing is reported, never hidden"
    assert motion.current_clip(picked[0]) is not None


def test_a_standalone_plan_can_be_checked_by_a_job(api, worker, toolchain_stub):
    from instai.motion_plan import plans

    plan = plans.create({"style": "cinematic_realistic", "size": "vertical", "scenes": [{"type": "kinetic_title", "duration": 1.5, "text": " ".join(["کلمه"] * 14)}, {"type": "quote", "duration": 4, "text": "خوب"}]}, origin="page")
    j = finish(api, worker, api.post(f"/api/motion/plans/{plan.pk}/qa"))
    assert j["result"]["geometry"] is True and j["result"]["fixed"] >= 1
    plan.refresh_from_db()
    assert plan.spec["scenes"][0]["duration"] > 1.5 and plan.qa["ok"] is True


def test_the_critique_job_waits_for_ollama_and_runs_by_itself_when_it_is_back(api, worker, toolchain_stub, monkeypatch):
    from instai.jobs.models import Job
    from instai.motion_plan import plans
    from instai.providers import ollama, registry
    from instai.providers.fake import FakeProvider

    plan = plans.create({"style": "cinematic_realistic", "size": "vertical", "scenes": [{"type": "kinetic_title", "duration": 4, "text": "سلام دنیا"}]}, origin="page")
    monkeypatch.setattr(ollama.OllamaProvider, "health", lambda self: {"ok": False, "detail": "refused", "models": []})
    r = api.post(f"/api/motion/plans/{plan.pk}/critique")
    jid = r.json()["job"]["id"]
    for _ in range(4):
        run_jobs(worker)
    j = Job.objects.get(pk=jid)
    assert j.status == Job.QUEUED and j.wait_code == "ollama_down" and j.attempts == 0, "no cloud fallback: the job waits for the owner's Ollama"
    prov = FakeProvider()
    prov.scripted = {"verdict": "ok", "issues": [], "ops": []}
    registry.set_provider_for_tests(prov)
    Job.objects.filter(pk=jid).update(run_after=timezone.now())
    j2 = finish(api, worker, type("R", (), {"status_code": 202, "content": b"", "json": lambda self: {"job": {"id": jid}}})())
    assert j2["result"]["state"] == "done" and j2["result"]["rounds"] == 1
    plan.refresh_from_db()
    assert plan.critique["state"] == "done" and plan.critique["rounds"][0]["before"][0]["image_rel"].startswith("motion/"), "the frames the model saw are kept for the page"


# ------------------------------------------------------------------ the real thing

REAL = os.environ.get("INSTAI_REMOTION_REAL") == "1"


@pytest.mark.skipif(not REAL, reason="set INSTAI_REMOTION_REAL=1 on a PC that has run scripts/setup_remotion.py")
def test_real_toolchain_every_component_in_three_sizes(tmp_path):
    """The acceptance run: ONE frame of every component of the library in landscape, vertical and square, through the real toolchain (render.mjs QA mode: one browser, 57
    stills), then the rule checks of qa.py over the geometry of every frame. No error-level finding may remain. The pictures are tiled into a montage per size
    (INSTAI_MOTION_OUT, default the temp folder) for the owner's eyes."""
    from instai.motion_plan import selftest

    out = Path(os.environ.get("INSTAI_MOTION_OUT") or tmp_path)
    rep = selftest.run_every_component(out, lang="fa")
    assert rep["rendered"] == 57 and not rep["render_errors"], rep["render_errors"]
    errors = [f for f in rep["findings"] if f["severity"] == "error"]
    assert not errors, "\n".join(f"{f['component']}/{f['size']}: {f['message_en']}" for f in errors[:20])
    for size in ("landscape", "vertical", "square"):
        assert (out / f"montage-{size}.png").stat().st_size > 20000


@pytest.mark.skipif(not REAL, reason="set INSTAI_REMOTION_REAL=1 on a PC that has run scripts/setup_remotion.py")
def test_real_toolchain_an_explainer_episode_assembles_with_drawn_clips(api, worker, ffmpeg_available, monkeypatch, tmp_path):
    """The acceptance run of the pipeline: an explainer episode with motion-graphics shots is produced with the REAL Remotion (preview size), the clips are registered, and the assembled
    video has no Ken Burns note for them. On a PC that has run setup_remotion.py nothing is faked; on a bare server INSTAI_REAL_NODE / INSTAI_REAL_BROWSER name the Node.js and the browser."""
    import subprocess

    from instai.assets import storage
    from instai.assets.models import Asset
    from instai.motion_plan import shots as motion
    from instai.motion_plan.models import MotionPlan
    from instai.remotion import toolchain

    node, browser = os.environ.get("INSTAI_REAL_NODE"), os.environ.get("INSTAI_REAL_BROWSER")
    if node and browser:
        monkeypatch.setattr(toolchain, "status", lambda: {"ready": True, "node": {"path": node, "version": "manual", "source": "manual"}, "packages": True,
                                                          "browser": {"path": browser, "source": "manual", "mode": os.environ.get("INSTAI_REAL_MODE", "headless-shell")}, "state": "ready", "message_fa": "", "message_en": ""})
        monkeypatch.setattr(toolchain, "work_dir", lambda: Path(os.environ.get("INSTAI_REAL_WORK") or tmp_path / "work"))
    assert toolchain.status()["ready"], toolchain.status()
    ep_id, picked, shots = motion_episode(api, worker)
    ep = produce(api, worker, ep_id, "preview")
    assert ep["state"] == "ready_for_approval", ep.get("qc")
    for s in picked:
        clip = Asset.objects.get(shot=s, role="shot_clip", is_current=True)
        plan = MotionPlan.objects.get(shot=s)
        assert clip.provenance["engine"] == "remotion" and clip.size_bytes > 5000 and abs(clip.duration_sec - motion.target_seconds(s, s.scene.episode)) < 1.0
        assert plan.qa["geometry"] is True, plan.qa.get("geometry_error")
    video = Asset.objects.get(pk=next(v for v in ep["videos"] if v["role"] == "preview")["id"])
    assert not [n for n in video.provenance["notes"] if "Ken Burns" in n and "motion" in n.lower()], video.provenance["notes"]
    out = os.environ.get("INSTAI_MOTION_OUT")
    if out:                                                    # a contact sheet of the episode (one frame per second) for the owner's eyes
        Path(out).mkdir(parents=True, exist_ok=True)
        subprocess.run([ffmpeg_available["ffmpeg"], "-y", "-loglevel", "error", "-i", str(storage.storage.path_for(video.path)), "-vf", "fps=1,scale=180:-1,tile=8x3", "-frames:v", "1",
                        str(Path(out) / "episode-contact.png")], timeout=120)
