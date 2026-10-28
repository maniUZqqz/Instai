"""Pure-logic unit tests: schemas/repair, JSON extraction, state machine, profiles, subtitles, camera, timeline, costs, memory, env file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from instai.agents import schemas
from instai.agents.jsonschema_lite import repair, validate
from instai.agents.roles import coverage, normalize_storyboard, reading_stats
from instai.agents.runner import extract_json
from instai.pages import profiles
from instai.render import assemble as asm
from instai.render import camera, subtitles
from instai.story import costs, states


# ------------------------------------------------------------------ schemas, repair, extraction

def test_validate_reports_readable_problems():
    errs = validate({"title": "", "hook": "h", "blocks": [{"speaker": "a"}], "extra": 1}, schemas.SCRIPT)
    joined = " | ".join(errs)
    assert "title" in joined and "blocks" in joined and "text" in joined
    assert validate({"title": "t", "hook": "h", "blocks": [{"speaker": "a", "text": "x"}] * 3}, schemas.SCRIPT) == []


def test_repair_coerces_types_clamps_and_drops_unknown_fields():
    schema = {"type": "object", "additionalProperties": False, "required": ["n"],
              "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 10}, "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
                             "ok": {"type": "boolean"}, "name": {"type": "string", "maxLength": 5}}}
    out = repair({"n": "42", "tags": "solo", "ok": "yes", "name": "abcdefgh", "junk": 1}, schema)
    assert out == {"n": 10, "tags": ["solo"], "ok": True, "name": "abcde"}
    assert repair({"n": 3.0, "tags": ["a", "b", "c"]}, schema)["tags"] == ["a", "b"]
    assert repair({"n": "abc"}, schema)["n"] == "abc", "what cannot be repaired is left for validation to report"


@pytest.mark.parametrize("text", [
    '{"a": 1}', '```json\n{"a": 1}\n```', 'Sure! Here is the JSON:\n{"a": 1}\nHope it helps', 'noise {"a": 1} trailing {"b": 2}',
    '{"a": "brace } inside string", "b": 1}',
])
def test_extract_json_handles_fences_chatter_and_braces_in_strings(text):
    assert extract_json(text)["a"] in (1, "brace } inside string")


def test_extract_json_rejects_garbage():
    with pytest.raises(ValueError):
        extract_json("no json here at all")
    with pytest.raises(ValueError):
        extract_json('{"a": 1')


# ------------------------------------------------------------------ state machine

def test_state_machine_forward_rework_and_terminal_rules():
    s = states
    assert s.allowed_next(s.DRAFT) == [s.PLANNED, s.FAILED, s.CANCELLED]
    assert s.can_transition(s.SCRIPT_REVIEW, s.STORYBOARDING) and s.can_transition(s.SCRIPT_REVIEW, s.SCRIPTING)
    assert not s.can_transition(s.PLANNED, s.STORYBOARDING), "no skipping the script"
    assert s.can_transition(s.ASSET_GENERATION, s.ASSEMBLY), "still-only episodes skip animation"
    assert not s.can_transition(s.ASSET_GENERATION, s.QUALITY_REVIEW)
    for later in (s.STORYBOARDING, s.ASSET_GENERATION, s.ANIMATION, s.ASSEMBLY, s.QUALITY_REVIEW, s.READY_FOR_APPROVAL):
        assert s.can_transition(later, s.SCRIPT_REVIEW), f"rework from {later}"
    assert s.allowed_next(s.APPROVED)[:2] == [s.SCHEDULED, s.READY_FOR_APPROVAL]
    assert s.allowed_next(s.PUBLISHED) == [], "published is final"
    assert s.allowed_next(s.FAILED, s.ASSEMBLY) == [s.ASSEMBLY], "failed resumes where it stopped"
    assert s.allowed_next(s.CANCELLED) == [s.DRAFT]
    assert set(s.LABELS_FA) == set(s.ORDER) | {s.FAILED, s.CANCELLED}, "every state has a Persian label"


# ------------------------------------------------------------------ profiles

def test_profiles_normalise_defaults_types_ranges_and_unknown_keys():
    p = profiles.normalize("production", {"episodes_per_series": "99999", "preset": "nonsense", "unknown": 1, "allowed_techniques": "still_kenburns"})
    assert p["episodes_per_series"] == 60 and p["preset"] == "balanced" and "unknown" not in p
    assert p["allowed_techniques"] == ["still_kenburns"] and p["fps"] == 30
    v = profiles.normalize("visual", {"subtitle": {"size": 80}})
    assert v["subtitle"]["size"] == 80 and v["subtitle"]["font"] == "Tahoma" and v["aspect_ratio"] == "9:16"
    assert profiles.normalize("publishing", None)["auto_publish"] is False, "never auto-publish by default"
    assert profiles.validate_techniques({"allowed_techniques": ["still_kenburns", "magic"]}) == ["magic"]
    for kind in profiles.KINDS:
        assert profiles.normalize(kind, profiles.default_data(kind)) == profiles.default_data(kind)


# ------------------------------------------------------------------ subtitles

def test_subtitle_chunks_cues_and_ass_for_persian():
    text = "فرض کن در آن شب سرنوشت‌ساز، قهرمان داستان تصمیم دیگری می‌گرفت و شهر در سکوت فرو رفته بود."
    chunks = subtitles.split_text(text)
    assert len(chunks) >= 2 and all(len(c.split()) <= subtitles.MAX_WORDS + 1 for c in chunks) and " ".join(chunks) == text
    cues = subtitles.make_cues(text, 2.0, 6.0)
    assert cues[0].start == 2.0 and abs(cues[-1].end - 8.0) < 0.01
    assert all(a.end <= b.start + 1e-6 for a, b in zip(cues, cues[1:])), "cues never overlap"
    ass = subtitles.build_ass(cues, 1080, 1920, {"size": 64, "color": "#FFEE00"})
    assert "PlayResY: 1920" in ass and "Vazirmatn" in ass and "&H0000EEFF" in ass and ass.count("Dialogue:") == len(cues)
    assert "‏" in ass, "RTL mark so numbers/Latin at the line start do not flip the paragraph"
    assert "{" not in subtitles._esc("a {override} b"), "text can never inject ASS override tags"
    assert subtitles._ts(3725.5) == "1:02:05.50"


# ------------------------------------------------------------------ camera + timeline

@pytest.mark.parametrize("move", camera.MOVES)
def test_every_camera_move_builds_a_filter(move):
    f = camera.ken_burns(move, 0.5, 90, 1080, 1920, 30)
    assert "zoompan=" in f and "d=90" in f and "s=1080x1920" in f and f.endswith("format=yuv420p")
    assert "on/89" in f or move == "static"


def test_camera_intensity_and_oversampling():
    assert camera.zmax(0) < camera.zmax(0.5) < camera.zmax(1) and camera.zmax(5) == camera.zmax(1)
    assert "scale=2160:3840" not in camera.ken_burns("zoom_in", 0.5, 10, 1080, 1920, 30), "final uses 1.5x oversampling"
    assert "scale=720:1280" in camera.ken_burns("zoom_in", 0.5, 10, 360, 640, 15), "preview uses 2x"
    par = camera.parallax("pan_left", 0.5, 30, 360, 640, 15)
    assert "[bg]" in par and "[fg]" in par and par.endswith("[out]") and "overlay" in par


def test_timeline_narration_drives_length_and_crossfades_overlap():
    shots = [asm.ShotSpec("a", 3.0, transition="crossfade", audio="a.wav", audio_duration=5.0),
             asm.ShotSpec("b", 4.0, transition="cut"), asm.ShotSpec("c", 2.0, audio="c.wav", audio_duration=1.0)]
    tl = asm.plan_timeline(shots)
    assert tl[0]["duration"] == 5.5, "5.0 s of speech + lead-in + tail extends the 3 s plan"
    assert tl[0]["overlap_next"] == asm.XFADE and tl[1]["start"] == pytest.approx(5.5 - asm.XFADE)
    assert tl[2]["start"] == pytest.approx(tl[1]["end"]) and tl[2]["duration"] == 2.0
    assert asm.total_duration(tl) == tl[-1]["end"] and tl[0]["audio_start"] == asm.LEAD_IN
    assert asm.plan_timeline([]) == []


def test_filter_graph_structure():
    shots = [asm.ShotSpec("a", 3.0, transition="crossfade", audio="a.wav", audio_duration=2.0), asm.ShotSpec("b", 3.0)]
    tl = asm.plan_timeline(shots)
    g = asm.build_filter(shots, tl, asm.RenderOptions.for_mode("preview", music=None), 2, 2, True)
    assert "xfade=transition=fade" in g and "ass=sub.ass:fontsdir=fonts" in g and "loudnorm=I=-16.0" in g and "adelay=150|150" in g
    assert "[aout]" in g and "[vout]" in g and "sidechaincompress" not in g
    g2 = asm.build_filter(shots, tl, asm.RenderOptions.for_mode("final", music="m.mp3"), 2, 2, False)
    assert "sidechaincompress" in g2 and "null[vout]" in g2


def test_render_options_preview_is_cheaper_than_final():
    p, f = asm.RenderOptions.for_mode("preview"), asm.RenderOptions.for_mode("final")
    assert (f.width, f.height, f.fps) == (1080, 1920, 30) and p.height < f.height and p.fps < f.fps and p.crf > f.crf


# ------------------------------------------------------------------ costs, script/storyboard checks

def test_costs_flag_estimates_and_prefer_measured_values(db):
    from instai.core.models import BenchmarkResult, BenchmarkRun

    e = costs.shot_estimate("wan_i2v", 8, "final")
    assert e["gpu_seconds"] == pytest.approx(60 + 2 * 540), "keyframe + two chained 5-second Wan clips"
    assert costs.shot_estimate("wan_i2v", 8, "preview")["gpu_seconds"] < 30, "preview never runs Wan"
    assert costs.shot_estimate("three_d", 4)["notes"] == ["falls_back_to_still_kenburns"]
    assert costs.shot_estimate("motion_graphics", 4)["gpu_seconds"] == 0

    class S:
        technique, duration_sec = "still_kenburns", 4

    est = costs.episode_estimate([S(), S()])
    assert est["source"] == "planning_estimate"
    run = BenchmarkRun.objects.create(status="done")
    BenchmarkResult.objects.create(run=run, step="image", candidate="flux", status="ok", seconds=33.0)
    assert costs.episode_estimate([S()])["source"] == "measured"
    assert costs.shot_estimate("still_kenburns", 4)["gpu_seconds"] == 33.0


def test_reading_stats_and_coverage():
    blocks = [{"speaker": "n", "text": "کلمه " * 20}] * 4
    st = reading_stats({"hook": "h", "blocks": blocks, "cta": "c"}, "fa", 45)
    assert st["word_count"] == 81 and st["ok"] and st["est_duration_sec"] == pytest.approx(81 / 2.4, abs=0.1)
    assert "too_long" in reading_stats({"hook": "h", "blocks": blocks * 3, "cta": "c"}, "fa", 45)["warnings"]
    assert "missing_cta" in reading_stats({"hook": "h", "blocks": blocks}, "fa", 45)["warnings"]
    script = {"blocks": [{"text": "الف ب پ ت"}, {"text": "ث ج چ"}]}
    full = {"scenes": [{"shots": [{"narration": "الف ب پ ت"}, {"narration": "ث ج چ"}]}]}
    half = {"scenes": [{"shots": [{"narration": "الف ب"}]}]}
    assert coverage(script, full) == 1.0 and coverage(script, half) < 0.5


def test_storyboard_guard_rails_remap_techniques_and_clamp_durations():
    sb = {"scenes": [{"title": "s", "shots": [{"technique": "wan_i2v", "duration_sec": 99, "description": "d", "image_prompt": "p"},
                                              {"technique": "puppet_2d", "duration_sec": 0.1, "description": "d", "image_prompt": "p"}]}]}
    out = normalize_storyboard(sb, ["still_kenburns", "puppet_2d"])
    shots = out["scenes"][0]["shots"]
    assert shots[0]["technique"] == "still_kenburns" and shots[1]["technique"] == "puppet_2d", "disallowed technique -> cheapest allowed"
    assert shots[0]["duration_sec"] == 20 and shots[1]["duration_sec"] == 1 and shots[0]["camera"]["move"]


# ------------------------------------------------------------------ env file, redaction

def test_envfile_roundtrip_keeps_comments_and_other_keys(tmp_path):
    from instai.envfile import read_env, write_env_value

    p = tmp_path / ".env"
    p.write_text("# comment\nA=1\nB='two'\n", encoding="utf-8")
    write_env_value("B", "three", p)
    write_env_value("C", "4", p)
    assert read_env(p) == {"A": "1", "B": "three", "C": "4"} and "# comment" in p.read_text()
    with pytest.raises(ValueError):
        write_env_value("X", "a\nb", p)


def test_licence_table_is_honest_about_what_is_verified():
    from instai.core import licences

    by = {m["id"]: m for m in licences.MODELS}
    assert by["ltx2"]["excluded"] and by["hunyuan15"]["excluded"]
    assert by["pocket-tts"]["warning"] and by["edge-tts"]["warning"] and not by["pocket-tts"].get("excluded") and not by["edge-tts"].get("excluded")   # owner asked for them
    assert by["flux-dev"]["decision"] is True and by["flux-dev"]["commercial"] == "conditional"
    assert "not audited" in by["anisora"]["verified"] and "licence line only" in by["animegen"]["verified"]      # read on 2026-10-28, never audited
    assert "NOT verified" in licences.markdown() and "OWNER DECISION" in licences.markdown() and "WARNING" in licences.markdown()
