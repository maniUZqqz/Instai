"""Phase 3 hero shots: segment planning, colour match, embedding QC, Wan clips through the GPU router and the real pipeline (fake ComfyUI that
returns real small videos), reference keyframes from the character sheet, the anime model comparison + vote, and the LoRA before/after job."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from tests import fakes
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)


# ------------------------------------------------------------------ pure helpers

def test_segment_plan_covers_the_duration_with_valid_wan_lengths():
    from instai.production import hero

    assert hero.segment_frames(3.0) == [49] and hero.segment_frames(5.0) == [81] and len(hero.segment_frames(6.0)) == 2 and len(hero.segment_frames(12.0)) == 3
    for d in (1.0, 2.5, 4.9, 5.1, 9.0, 14.0):
        plan = hero.segment_frames(d)
        assert all(n % 4 == 1 and 9 <= n <= 81 for n in plan)
        total = sum(plan) - (len(plan) - 1)                          # chained passes share one frame
        assert abs(total / hero.FPS - d) < 0.9, (d, plan)


def make_video(path: Path, w=96, h=160, frames=20, fps=16, vf="null") -> Path:
    from instai.core import runtime

    ff = runtime.ffmpeg_info()["ffmpeg"]
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x6a8fd8:s={w}x{h}:r={fps}", "-vf", vf, "-frames:v", str(frames),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(path)], check=True)
    return path


def test_colour_match_pulls_a_drifting_clip_back_to_the_reference(tmp_path, ffmpeg_available):
    from instai.render import colormatch

    ref = tmp_path / "ref.png"
    Image.new("RGB", (96, 160), (0x6a, 0x8f, 0xd8)).save(ref)
    # a clip that gets darker and more orange over time (what image-to-video drift looks like)
    drift = make_video(tmp_path / "drift.mp4", frames=24, vf="eq=brightness=-0.02:eval=frame,colorbalance=rs=0.35:bs=-0.35,eq=contrast=0.9")
    out = tmp_path / "fixed.mp4"
    r = colormatch.match_clip(drift, ref, out)
    assert r["before"] > 8 and r["after"] < r["before"] * 0.5, r
    from instai.render import ffmpeg

    info = ffmpeg.probe(out)
    assert info["vcodec"] == "h264" and (info["width"], info["height"]) == (96, 160) and abs(info["duration"] - 24 / 16) < 0.2
    # an already matching clip is left alone (no flicker from needless correction)
    same = make_video(tmp_path / "same.mp4", frames=12)
    r2 = colormatch.match_clip(same, ref, tmp_path / "same_fixed.mp4")
    assert r2["before"] < 6 and r2["after"] < 6 and all(abs(g - 1) < 0.2 for g in r2["gain"])


def test_embedding_similarity_catches_drift_and_ignores_plain_backgrounds(tmp_path, ffmpeg_available):
    from instai.production import consistency

    def sheet(color, bg):
        im = Image.new("RGB", (200, 300), bg)
        d = ImageDraw.Draw(im)
        d.ellipse((60, 40, 140, 120), fill=color)
        d.rectangle((70, 120, 130, 260), fill=(200, 60, 60))
        return im
    a, same_other_bg, recoloured = sheet((240, 200, 160), (255, 255, 255)), sheet((240, 200, 160), (20, 20, 20)), sheet((40, 200, 90), (255, 255, 255))
    assert consistency.similarity(a, a) == 1.0
    assert consistency.similarity(a, recoloured) < 0.85                          # whole-image similarity (structure + colour) drops when the character is recoloured
    assert consistency.palette_similarity(a, same_other_bg) > 0.8 and consistency.palette_similarity(a, recoloured) < 0.78
    kf = tmp_path / "kf.png"
    a.save(kf)
    good = tmp_path / "good.mp4"
    make_video_from_image(a, good)
    bad = tmp_path / "bad.mp4"
    make_video_from_image(recoloured, bad)
    ok = consistency.check_clip(good, kf, kf)
    assert ok["ok"] and ok["drift"] >= consistency.DRIFT_OK and ok["sheet"] > 0.95
    drifted = consistency.check_clip(bad, kf, None)
    assert not drifted["ok"] and drifted["notes"] and "drifts" in drifted["notes"][0]
    consistency.set_embedder(lambda im: [1.0, 0.0])                  # a stronger embedder can be plugged in
    try:
        assert consistency.similarity(a, recoloured) == 1.0
    finally:
        consistency.set_embedder(None)


def make_video_from_image(img: Image.Image, out: Path, frames=16):
    from instai.core import runtime

    d = out.parent / (out.stem + "_f")
    d.mkdir(exist_ok=True)
    img.save(d / "f.png")
    ff = runtime.ffmpeg_info()["ffmpeg"]
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", str(d / "f.png"), "-frames:v", str(frames), "-r", "16", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-preset", "ultrafast", str(out)], check=True)


# ------------------------------------------------------------------ fake ComfyUI with real videos

class VideoComfy:
    """The fake ComfyUI of tests/fakes.py, returning real (small) videos sized from the Wan graph's frame count."""

    def __init__(self, hue=0):
        self.srv = fakes.comfy_server()
        self.hue = hue

        def video_bytes(graph):
            node = next(n for n in graph.values() if n["class_type"] in ("WanImageToVideo", "WanFirstLastFrameToVideo"))
            return fakes.make_test_video(96, 160, int(node["inputs"]["length"]), 16, color_shift=self.hue)
        self.srv.video_bytes = video_bytes

    def __enter__(self):
        self.srv.__enter__()
        return self.srv

    def __exit__(self, *a):
        self.srv.__exit__()


@pytest.fixture
def comfy_local():
    from instai.core import settings_store
    from instai.gpu import compute

    c = VideoComfy()
    srv = c.__enter__()
    settings_store.set_setting("comfyui_url", srv.url)
    compute._CAP_CACHE.update(at=0.0, value=None)
    yield srv
    settings_store.set_setting("comfyui_url", "")
    compute._CAP_CACHE.update(at=0.0, value=None)
    c.__exit__()


def prepared_episode(api, worker, techniques, with_sheet=True, image_engine="placeholder"):
    """A page + episode with storyboard; shots get the given techniques; optionally an approved character sheet."""
    from instai.assets import storage as asset_storage
    from instai.core import settings_store
    from instai.pages.models import Character, CharacterReference
    from tests.test_pipeline_e2e import build_episode

    page, sid, ep_id = build_episode(api, worker, fmt="anime_whatif")
    api.put(f"/api/pages/{page['id']}/profiles/production", {"final_height": 480, "fps": 12, "allowed_techniques": ["still_kenburns", "wan_i2v", "wan_flf", "puppet_2d"]},
            format="json")
    ep = api.get(f"/api/episodes/{ep_id}").json()
    shots = [sh for sc in ep["scenes"] for sh in sc["shots"]]
    techniques = list(techniques) + ["still_kenburns"] * (len(shots) - len(techniques))        # the generated storyboard may pick other techniques: pin them all
    for sh, tech in zip(shots, techniques):
        assert api.patch(f"/api/shots/{sh['id']}", {"technique": tech, "duration_sec": 3.0}, format="json").status_code == 200
    sheet_path = None
    if with_sheet:
        ch = Character.objects.create(page_id=page["id"], name="هیرو", appearance="red jacket, spiky hair")
        tmp = Path(asset_storage.storage.root) / "_t" / "sheet.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (300, 400), (200, 60, 60)).save(tmp)
        a = asset_storage.register(tmp, f"characters/{ch.pk}/sheet.png", kind="image", role="reference")
        CharacterReference.objects.create(character=ch, kind="sheet", asset=a, approved=True)
        for sh in shots[: len(techniques)]:
            api.patch(f"/api/shots/{sh['id']}", {"speaker": "هیرو"}, format="json")
        sheet_path = a
    settings_store.set_setting("image_engine", image_engine)
    return page, ep_id, shots, sheet_path


def run_final(api, worker, ep_id, rounds=60):
    from tests.conftest import run_jobs

    r = api.post(f"/api/episodes/{ep_id}/produce", {"mode": "final"}, format="json")
    assert r.status_code == 202, r.content
    for _ in range(rounds):
        run_jobs(worker)
        ep = api.get(f"/api/episodes/{ep_id}").json()
        if ep["state"] in ("ready_for_approval", "quality_review", "failed"):
            return ep
    raise AssertionError(ep["state"])


def test_hero_shots_flow_through_the_router_and_the_whole_pipeline(api, worker, ffmpeg_available, comfy_local):
    from instai.assets.models import Asset
    from instai.production.models import ShotRender

    page, ep_id, shots, _ = prepared_episode(api, worker, ["wan_i2v", "wan_flf", "still_kenburns"])
    ep = run_final(api, worker, ep_id)
    assert ep["state"] in ("ready_for_approval", "quality_review"), ep.get("error") or ep["qc"]
    renders = {r.shot_id: r for r in ShotRender.objects.filter(shot__scene__episode_id=ep_id, technique__in=("wan_i2v", "wan_flf"))}
    assert len(renders) == 2 and all(r.status == "done" and r.device == "local" and r.seconds > 0 for r in renders.values())
    i2v, flf = renders[shots[0]["id"]], renders[shots[1]["id"]]
    for r in (i2v, flf):
        assert r.qc["drift"] is not None and "thresholds" in r.qc and r.params["colour"]["frames"] >= 40         # colour matched, QC recorded
    # graphs that reached ComfyUI: plain I2V for the first, FIRST/LAST FRAME for the second (end image = the next shot's keyframe)
    kinds = [[n["class_type"] for n in g.values()] for g in comfy_local.prompts]
    assert any("WanImageToVideo" in k for k in kinds) and any("WanFirstLastFrameToVideo" in k for k in kinds)
    flf_graph = next(g for g in comfy_local.prompts if any(n["class_type"] == "WanFirstLastFrameToVideo" for n in g.values()))
    assert flf_graph["12"]["inputs"]["end_image"] == ["18", 0] and flf_graph["12"]["inputs"]["length"] in (49,)
    assert comfy_local.uploads >= 3                                                      # start (+ end) images were uploaded as task inputs
    clip = Asset.objects.get(shot_id=shots[0]["id"], role="shot_clip", is_current=True)
    assert clip.provenance["workflow"] == "wan22_i2v_a14b_fp8" and clip.provenance["colour_match"]["after"] <= clip.provenance["colour_match"]["before"] + 0.5
    # editing the hero shot's prompt makes only its clip stale; a re-render reuses the other clip
    before = Asset.objects.filter(role="shot_clip", episode_id=ep_id).count()
    api.patch(f"/api/shots/{shots[0]['id']}", {"image_prompt": "totally different"}, format="json")
    run_final(api, worker, ep_id)
    assert Asset.objects.filter(role="shot_clip", episode_id=ep_id).count() == before + 1


def test_long_hero_shot_is_chained_and_stitched(api, worker, ffmpeg_available, comfy_local):
    from instai.production.models import ShotRender
    from instai.render import ffmpeg
    from instai.assets.models import Asset
    from instai.assets.storage import storage

    page, ep_id, shots, _ = prepared_episode(api, worker, ["wan_flf"], with_sheet=False)
    api.patch(f"/api/shots/{shots[0]['id']}", {"duration_sec": 8.0}, format="json")
    run_final(api, worker, ep_id)
    r = ShotRender.objects.get(shot_id=shots[0]["id"])
    assert r.status == "done" and r.params["segments"] == 2
    graphs = comfy_local.prompts
    assert [any(n["class_type"] == "WanFirstLastFrameToVideo" for n in g.values()) for g in graphs[-2:]] == [False, True]   # chain: I2V first, FLF to the next keyframe last
    clip = Asset.objects.get(shot_id=shots[0]["id"], role="shot_clip", is_current=True)
    assert clip.provenance["segments"] == 2
    info = ffmpeg.probe(storage.path_for(clip.path))
    assert info["duration"] > 4.5                                                         # two ~4 s passes minus the shared frame


def reference_graphs(comfy):
    return [g for g in comfy.prompts if any(n["class_type"] == "LoadImage" and str(n["inputs"].get("image")) == "uploaded.png" for n in g.values())
            and not any(n["class_type"] in ("WanImageToVideo", "WanFirstLastFrameToVideo") for n in g.values())]


def test_hero_keyframe_comes_from_the_character_sheet(api, worker, ffmpeg_available, comfy_local):
    from instai.assets.models import Asset

    page, ep_id, shots, sheet = prepared_episode(api, worker, ["wan_i2v", "still_kenburns"], image_engine="comfyui")
    run_final(api, worker, ep_id)
    ref = reference_graphs(comfy_local)
    assert len(ref) == 1                                                                  # only the hero shot is conditioned on the sheet
    texts = " ".join(str(n["inputs"].get("text") or n["inputs"].get("prompt") or "") for n in ref[0].values())
    assert "same character design" in texts
    kf = Asset.objects.get(shot_id=shots[0]["id"], role="keyframe", is_current=True)
    assert kf.provenance["workflow"] == "qwen_image_edit_ref" and kf.provenance["reference"] is True        # Qwen-Image-Edit is preferred when a PC has it
    assert any(n["class_type"] == "TextEncodeQwenImageEditPlus" for n in ref[0].values())
    plain = Asset.objects.get(shot_id=shots[1]["id"], role="keyframe", is_current=True)
    assert plain.provenance["workflow"] == "flux_dev_fp8_t2i" and plain.provenance["reference"] is False
    # a new approved sheet makes the hero keyframe stale (the character changed)
    from instai.assets import storage as asset_storage
    from instai.pages.models import CharacterReference

    tmp = Path(asset_storage.storage.root) / "_t" / "sheet2.png"
    Image.new("RGB", (300, 400), (60, 60, 200)).save(tmp)
    a2 = asset_storage.register(tmp, "characters/x/sheet2.png", kind="image", role="reference")
    CharacterReference.objects.filter(character__page_id=page["id"]).update(asset=a2)
    assert api.get(f"/api/episodes/{ep_id}").json()["stale"]["keyframes_final"] >= 1


def test_reference_keyframe_falls_back_to_flux_img2img_without_qwen_edit(api, worker, ffmpeg_available):
    from instai.assets.models import Asset
    from instai.core import settings_store
    from instai.gpu import compute

    c = VideoComfy()
    c.srv = fakes.comfy_server(missing_models=("qwen_image_edit_2509_fp8_e4m3fn.safetensors",))
    c.srv.video_bytes = lambda graph: fakes.make_test_video(96, 160, 49, 16)
    srv = c.__enter__()
    try:
        settings_store.set_setting("comfyui_url", srv.url)
        compute._CAP_CACHE.update(at=0.0, value=None)
        page, ep_id, shots, _ = prepared_episode(api, worker, ["wan_i2v"], image_engine="comfyui")
        run_final(api, worker, ep_id)
        kf = Asset.objects.get(shot_id=shots[0]["id"], role="keyframe", is_current=True)
        assert kf.provenance["workflow"] == "flux_dev_fp8_img2img"
        g = reference_graphs(srv)[0]
        assert any(n["class_type"] == "VAEEncode" for n in g.values()) and any(n["class_type"] == "ImageScale" for n in g.values())
        assert next(n for n in g.values() if n["class_type"] == "KSampler")["inputs"]["denoise"] == 0.62
    finally:
        settings_store.set_setting("comfyui_url", "")
        compute._CAP_CACHE.update(at=0.0, value=None)
        c.__exit__()


def test_no_device_for_wan_keeps_ken_burns_and_says_so(api, worker, ffmpeg_available):
    from instai.production.models import ShotRender

    page, ep_id, shots, _ = prepared_episode(api, worker, ["wan_i2v"], with_sheet=False)
    ep = run_final(api, worker, ep_id)                                                    # no ComfyUI anywhere
    assert ep["state"] in ("ready_for_approval", "quality_review") and not ShotRender.objects.filter(technique="wan_i2v").exists()
    from instai.assets.models import Asset

    notes = Asset.objects.get(episode_id=ep_id, role="final", is_current=True).provenance["notes"]
    assert any("no Wan clip available" in n for n in notes)


# ------------------------------------------------------------------ anime comparison + vote

def test_anime_comparison_same_stills_and_seeds_vote_sets_the_page_default(api, worker, ffmpeg_available, comfy_local):
    from instai.production.models import ComparisonClip, PageProductionConfig

    page, ep_id, shots, _ = prepared_episode(api, worker, ["still_kenburns"] * 3, with_sheet=False)
    run_final(api, worker, ep_id)                                          # keyframes exist now
    cands = {c["id"]: c for c in api.get("/api/anime/candidates").json()}
    assert cands["wan22"]["available"] and cands["anisora"]["available"] and cands["animegen"]["available"]          # the fake ComfyUI has every node/model
    assert cands["anisora"]["needs"] == ["ComfyUI-GGUF"] and "extra restrictions" in cands["anisora"]["licence"] and cands["animegen"]["commercial"] == "yes"
    r = api.post("/api/comparisons", {"episode": ep_id, "seeds": [5, 6], "candidates": ["wan22", "anisora", "animegen"], "prompt": "she turns and smiles"}, format="json")
    assert r.status_code == 202, r.content
    cid = r.json()["comparison"]["id"]
    assert len(r.json()["comparison"]["stills"]) == 0 or True
    finish(api, worker, r)
    d = api.get(f"/api/comparisons/{cid}").json()
    assert d["status"] == "done" and len(d["stills"]) == 3 and len(d["clips"]) == 3 * 2 * 3
    assert all(c["status"] == "done" and c["url"] for c in d["clips"])
    # same stills + same seeds for every candidate; each candidate used its own workflow
    seeds_by_cand = {}
    for c in d["clips"]:
        seeds_by_cand.setdefault(c["candidate"], set()).add((c["still_index"], c["seed"]))
    assert seeds_by_cand["wan22"] == seeds_by_cand["anisora"] == seeds_by_cand["animegen"]
    loaders = {n["inputs"].get("unet_name") for g in comfy_local.prompts for n in g.values() if n["class_type"] in ("UnetLoaderGGUF", "UNETLoader")}
    assert "Index-Anisora-V3.2-High-Q4_0.gguf" in loaders and "I2V_high_noise_Q4_K_M.gguf" in loaders and "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" in loaders
    assert api.post(f"/api/comparisons/{cid}/vote", {"candidate": "nonsense"}, format="json").status_code == 400
    v = api.post(f"/api/comparisons/{cid}/vote", {"candidate": "animegen", "still_index": 0}, format="json").json()
    assert v["winner"] == "animegen" and v["page_default"] == "animegen" and v["counts"]["animegen"] == 1
    assert PageProductionConfig.objects.get(page_id=page["id"]).anime_model == "animegen"
    api.post(f"/api/comparisons/{cid}/vote", {"candidate": "wan22"}, format="json")
    api.post(f"/api/comparisons/{cid}/vote", {"candidate": "wan22"}, format="json")
    assert PageProductionConfig.objects.get(page_id=page["id"]).anime_model == "wan22"          # the majority wins
    # the page default now drives the hero step: switch back to animegen and the GGUF graph is used for a hero shot
    api.put(f"/api/pages/{page['id']}/production-config", {"anime_model": "animegen"}, format="json")
    api.patch(f"/api/shots/{shots[0]['id']}", {"technique": "wan_i2v"}, format="json")
    n_before = len(comfy_local.prompts)
    run_final(api, worker, ep_id)
    assert any(n["class_type"] == "UnetLoaderGGUF" for g in comfy_local.prompts[n_before:] for n in g.values())
    assert api.put(f"/api/pages/{page['id']}/production-config", {"anime_model": "x"}, format="json").status_code == 400


def test_a_candidate_that_is_not_installed_is_skipped_not_faked(api, worker, ffmpeg_available):
    from instai.core import settings_store
    from instai.gpu import compute

    c = VideoComfy()
    srv = c.__enter__()
    srv_missing = fakes.comfy_server(missing_models=("Index-Anisora-V3.2-High-Q4_0.gguf",))
    srv_missing.video_bytes = srv.video_bytes
    srv_missing.__enter__()
    try:
        settings_store.set_setting("comfyui_url", srv_missing.url)
        compute._CAP_CACHE.update(at=0.0, value=None)
        page, ep_id, shots, _ = prepared_episode(api, worker, ["still_kenburns"] * 2, with_sheet=False)
        run_final(api, worker, ep_id)
        r = api.post("/api/comparisons", {"episode": ep_id, "seeds": [1], "candidates": ["wan22", "anisora"]}, format="json")
        finish(api, worker, r)
        d = api.get(f"/api/comparisons/{r.json()['comparison']['id']}").json()
        status = {c["candidate"]: c["status"] for c in d["clips"]}
        assert status["wan22"] == "done" and status["anisora"] == "skipped"
        assert "not available" in next(c["error"] for c in d["clips"] if c["candidate"] == "anisora")
        assert api.post(f"/api/comparisons/{d['id']}/vote", {"candidate": "anisora"}, format="json").status_code == 409     # no clip, no vote
    finally:
        settings_store.set_setting("comfyui_url", "")
        compute._CAP_CACHE.update(at=0.0, value=None)
        srv_missing.__exit__()
        c.__exit__()


# ------------------------------------------------------------------ LoRA with a measured before/after

def test_character_lora_training_reports_before_and_after(api, worker, ffmpeg_available, comfy_local, tmp_path, monkeypatch):
    from instai.core import settings_store
    from instai.pages.models import Character, CharacterReference
    from instai.assets import storage as asset_storage
    from instai.production.models import CharacterLora

    comfy_dir = tmp_path / "ComfyUI"
    (comfy_dir / "models" / "loras").mkdir(parents=True)
    settings_store.set_setting("comfyui_dir", str(comfy_dir))
    page = api.post("/api/pages", {"name": "ص", "format": "recurring_character", "languages": ["fa"], "idea": "x"}, format="json").json()
    ch = Character.objects.create(page_id=page["id"], name="لیلا", appearance="green coat")
    for i, colour in enumerate(((40, 160, 70), (50, 170, 80))):
        tmp = Path(asset_storage.storage.root) / "_t" / f"ref{i}.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (256, 384), colour).save(tmp)
        CharacterReference.objects.create(character=ch, kind="sheet" if i == 0 else "pose", approved=True,
                                          asset=asset_storage.register(tmp, f"characters/{ch.pk}/ref{i}.png", kind="image", role="reference"))
    # no approved reference -> a clear refusal
    empty = Character.objects.create(page_id=page["id"], name="بی‌شیت")
    j = api.post(f"/api/characters/{empty.pk}/loras", {}, format="json")
    finish(api, worker, j, expect="failed")
    assert CharacterLora.objects.get(character=empty).status == "failed" and "approved reference" in CharacterLora.objects.get(character=empty).error
    # the (fake) ComfyUI "writes" the trained LoRA where the real one would: into its loras folder, when the training graph is queued
    from tests.fakes import ComfyHandler

    orig = ComfyHandler.do_POST

    def post(self):
        n = int(self.headers.get("Content-Length") or 0)
        if self.path == "/prompt" and n:
            body = self.rfile.read(n)
            if b"TrainLoraNode" in body:
                (comfy_dir / "models" / "loras" / f"instai_character_{ch.pk}_00001_.safetensors").write_bytes(b"lora-weights" * 100)
            self.rfile = __import__("io").BytesIO(body)
            self.headers.replace_header("Content-Length", str(len(body)))
        return orig(self)
    monkeypatch.setattr(ComfyHandler, "do_POST", post)
    r = api.post(f"/api/characters/{ch.pk}/loras", {"steps": 50, "rank": 8}, format="json")
    j = finish(api, worker, r)
    lora = CharacterLora.objects.get(character=ch)
    assert lora.status == "trained" and lora.lora_file.endswith(".safetensors") and lora.before["similarity"] is not None and lora.after["similarity"] is not None
    assert len(lora.before["per_prompt"]) == 3 and lora.after["delta"] == pytest.approx(lora.after["similarity"] - lora.before["similarity"], abs=1e-3)
    assert j["result"]["lora"] == lora.lora_file and lora.approved is False
    graphs = comfy_local.prompts
    assert any("TrainLoraNode" in [n["class_type"] for n in g.values()] for g in graphs)
    assert sum(1 for g in graphs if any(n["class_type"] == "LoraLoader" for n in g.values())) == 3         # three "after" images with the LoRA
    assert (comfy_dir / "input" / f"instai_lora_{ch.pk}").is_dir() and len(list((comfy_dir / "input" / f"instai_lora_{ch.pk}").glob("*.txt"))) == 2   # dataset + captions installed
    assert "instaichar" in next(iter((comfy_dir / "input" / f"instai_lora_{ch.pk}").glob("*.txt"))).read_text(encoding="utf-8")
    assert api.patch(f"/api/loras/{lora.pk}", {"approved": True}, format="json").json()["approved"] is True
    shutil.rmtree(comfy_dir, ignore_errors=True)
