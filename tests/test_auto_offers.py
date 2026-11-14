"""The models the owner's brief depends on are fetched by themselves (night window, enough disk, never against his will), and the manifests that describe them are sound.

Review of 0.9.0: Qwen-Image-Edit (consistent AI-drawn characters) was only an offer; until the owner pressed the button the strategy was "not ready" and its self-test never ran,
which is exactly the kind of task the owner wanted left to the computer. Looking into it also found two broken destination paths in `manifests/image.json`
(`models\\text_encoders` and `models\\vae` had lost a backslash and became a TAB and a vertical tab), so the download could never have worked on Windows."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from instai.core import model_status, runtime, settings_store
from instai.jobs.models import Job
from instai.ops import auto_offers

pytestmark = pytest.mark.django_db(transaction=True)

MANIFESTS = Path(__file__).resolve().parents[1] / "manifests"
GB = 1024 ** 3


# ------------------------------------------------------------------ the manifests

def _strings(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(x, str):
        yield path, x


def test_no_manifest_text_holds_a_control_character_and_every_destination_is_a_clean_windows_path():
    """A JSON escape that swallowed a backslash (\\t, \\v) makes a path with a TAB in it: invalid on Windows, so the file is never saved."""
    for f in sorted(MANIFESTS.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        bad = [(p, repr(s)[:90]) for p, s in _strings(data) if any(ord(c) < 32 and c != "\n" for c in s)]
        assert bad == [], f"{f.name}: control characters in {bad}"
        for it in data.get("items", []) if isinstance(data, dict) else []:
            dest = it.get("dest")
            if dest:
                assert re.fullmatch(r"\{[A-Z_]+\}(\\[A-Za-z0-9._ +()-]+)*", dest), (f.name, it["id"], dest)


def test_the_qwen_files_land_where_comfyui_looks_for_them():
    data = json.loads((MANIFESTS / "image.json").read_text(encoding="utf-8"))
    dest = {it["id"]: it["dest"] for it in data["items"] if it["id"].startswith("qwen_edit:")}
    assert dest["qwen_edit:unet-fp8"].startswith("{COMFYUI}\\models\\diffusion_models\\")
    assert dest["qwen_edit:text-encoder"].startswith("{COMFYUI}\\models\\text_encoders\\")
    assert dest["qwen_edit:vae"].startswith("{COMFYUI}\\models\\vae\\")
    assert dest["qwen_edit:lightning-4step"].startswith("{COMFYUI}\\models\\loras\\")
    from instai.providers.comfy.workflows import WORKFLOWS

    for _kind, _field, name in WORKFLOWS["qwen_image_edit_multiref"].required_models:      # the workflow asks for exactly the files the manifest saves
        assert any(d.endswith("\\" + name) for d in dest.values()), name


# ------------------------------------------------------------------ the automatic decision

def offer(**kw) -> dict:
    base = {"id": "qwen_edit", "name": "Qwen-Image-Edit (consistent characters from the model sheets)", "complete": False, "missing_size": 31 * GB, "needs": []}
    base.update(kw)
    return base


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A ComfyUI folder with plenty of room, a real image engine, and the offers list of the manifests."""
    settings_store.set_setting("image_engine", "comfyui")
    monkeypatch.setattr(runtime, "comfyui_dir", lambda: str(tmp_path))
    monkeypatch.setattr(auto_offers, "free_bytes", lambda: 500 * GB)
    monkeypatch.delenv("INSTAI_AUTO_OFFERS", raising=False)
    auto_offers._LAST_AUTO[0] = 0.0
    state = {"offers": [offer()]}

    def offers(pkg=None):
        return [dict(o, auto=auto_offers.status(o)) for o in state["offers"]]

    monkeypatch.setattr(model_status, "offers", offers)
    return state


def test_the_real_offer_list_carries_the_automatic_state():
    rows = {o["id"]: o for o in model_status.offers(pkg={})}
    assert rows["qwen_edit"]["auto"]["state"] == "no_comfyui"                 # no ComfyUI folder is known in the test environment
    assert all(o["auto"]["state"] == "manual" for k, o in rows.items() if k != "qwen_edit")      # the anime models keep needing his confirmation
    assert rows["qwen_edit"]["licence"].startswith("Apache-2.0") and rows["qwen_edit"]["group"] == "identity"


def test_it_queues_the_download_by_itself_for_the_night_window_with_the_right_packages(world):
    j = auto_offers.auto_queue(force=True)
    assert j is not None and j.kind == "downloads.run"
    assert j.payload["packages"] == ["qwen_edit"] and j.payload["offer"] == "qwen_edit" and j.payload["auto"] is True
    assert j.window == "02:00-07:00" and j.payload["schedule"]["window"] == "02:00-07:00"      # only at night: the Downloads page's window
    assert j.title.startswith("دانلود خودکار شبانه") and j.payload["target"] == "local"
    assert auto_offers.auto_queue(force=True) is None                          # one at a time
    st = auto_offers.status(offer())
    assert st["state"] == "queued" and st["job"] == j.pk and st["window"] == "02:00-07:00"


def test_the_owner_can_say_no_by_cancelling_and_a_failure_is_retried_later(world):
    j = auto_offers.auto_queue(force=True)
    Job.objects.filter(pk=j.pk).update(status=Job.CANCELLED)
    assert auto_offers.status(offer())["state"] == "declined" and auto_offers.auto_queue(force=True) is None     # a "no" stays a "no"
    Job.objects.all().delete()
    j2 = auto_offers.auto_queue(force=True)
    Job.objects.filter(pk=j2.pk).update(status=Job.FAILED)
    assert auto_offers.status(offer())["state"] == "failed_recently" and auto_offers.auto_queue(force=True) is None
    from datetime import timedelta

    from django.utils import timezone

    Job.objects.filter(pk=j2.pk).update(finished_at=timezone.now() - timedelta(seconds=auto_offers.RETRY_S + 60))
    assert auto_offers.auto_queue(force=True) is not None                      # the downloader resumes from the partial files


def test_it_never_fills_the_disk_and_says_so(world, monkeypatch):
    monkeypatch.setattr(auto_offers, "free_bytes", lambda: 40 * GB)            # 31 GB + the 25 GB safety margin do not fit
    st = auto_offers.status(offer())
    assert st["state"] == "low_disk" and st["free_gb"] == 40.0 and st["need_gb"] == 56.0
    assert auto_offers.auto_queue(force=True) is None
    monkeypatch.setattr(auto_offers, "free_bytes", lambda: 60 * GB)
    assert auto_offers.auto_queue(force=True) is not None


def test_it_waits_for_what_it_needs_and_respects_every_switch(world, monkeypatch):
    world["offers"] = [offer(complete=True, missing_size=0)]
    assert auto_offers.status(world["offers"][0])["state"] == "complete" and auto_offers.auto_queue(force=True) is None
    world["offers"] = [offer()]
    monkeypatch.setenv("INSTAI_AUTO_OFFERS", "0")
    assert auto_offers.status(offer())["state"] == "off" and auto_offers.auto_queue(force=True) is None     # the owner can switch it off
    monkeypatch.delenv("INSTAI_AUTO_OFFERS")
    settings_store.set_setting("auto_offers", False)
    assert auto_offers.auto_queue(force=True) is None
    settings_store.set_setting("auto_offers", True)
    monkeypatch.setattr(runtime, "comfyui_dir", lambda: "")
    assert auto_offers.status(offer())["state"] == "no_comfyui" and auto_offers.auto_queue(force=True) is None
    monkeypatch.setattr(runtime, "comfyui_dir", lambda: str(Path(".").resolve()))
    settings_store.set_setting("image_engine", "placeholder")                  # demo mode: no real image models wanted
    assert auto_offers.auto_queue(force=True) is None
    settings_store.set_setting("image_engine", "comfyui")
    assert auto_offers.auto_queue(force=True) is not None


def test_a_needed_part_is_downloaded_first_and_other_offers_are_never_automatic(world):
    world["offers"] = [offer(id="anime_pack", name="Anime pack"), offer(needs=[{"id": "base_pack", "title": "Base", "complete": False, "missing_size": GB, "licence": "Apache-2.0"},
                                                                                {"id": "done_pack", "title": "Done", "complete": True, "missing_size": 0, "licence": "MIT"}])]
    assert auto_offers.status(world["offers"][0])["state"] == "manual"         # not in AUTO: only the owner's confirmation starts it
    j = auto_offers.auto_queue(force=True)
    assert j.payload["packages"] == ["base_pack", "qwen_edit"]                 # what is missing first, then the offer; what is there is not fetched again


def test_the_tick_calls_it_and_the_suite_never_gets_surprise_downloads(world):
    assert auto_offers.auto_queue() is None                                    # INSTAI_TESTING=1 and not forced
    from instai.production import automation

    assert "auto_offers" in Path(automation.__file__).read_text(encoding="utf-8")      # hooked into the automation tick, guarded
