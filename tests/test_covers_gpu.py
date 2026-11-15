"""The real FLUX path of the cover maker: runs ONLY on the GPU PC against the real ComfyUI (`pytest -m gpu -s tests/test_covers_gpu.py`, or Test-GPU.bat). Skips cleanly everywhere else.
Not part of the default run (the conftest points the services at dead ports; this file clears that override like tests/test_gpu_smoke.py)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.gpu, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def real_comfyui():
    from instai.core import settings_store

    settings_store.set_setting("comfyui_url", os.environ.get("INSTAI_REAL_COMFYUI_URL", "http://127.0.0.1:8188"))
    settings_store.set_setting("image_engine", "comfyui")
    settings_store.clear_cache()
    yield
    settings_store.set_setting("comfyui_url", "")
    settings_store.set_setting("image_engine", "placeholder")


def test_a_real_background_goes_under_a_real_cover(tmp_path):
    from PIL import Image

    from instai.covers import background, selftest
    from instai.covers.engine import fixtures
    from instai.covers.engine import formats as F
    from instai.covers.engine import render as R
    from instai.covers.engine.styles import STYLES
    from instai.gpu import compute
    from instai.providers.base import ProviderError

    st = background.engine_state()
    if not st["available"]:
        pytest.skip("ComfyUI or the image workflow is not available on this machine")
    ctx = SimpleNamespace(job=SimpleNamespace(pk=0, priority=0), check=lambda: None, waiting=lambda t: None, log=lambda *a: None, progress=lambda *a: None, add_gpu_seconds=lambda s: None)
    try:
        out = background.probe(ctx, tmp_path)
    except ProviderError as e:
        pytest.skip(f"the GPU task could not start: {e}")
    keep = Path(os.environ.get("INSTAI_GPU_SAMPLES", tmp_path)) / "covers-bg-real.png"
    shutil.copyfile(out["path"], keep)
    with Image.open(out["path"]) as im:
        bg = im.convert("RGB")
    print(f"background {bg.size} on {out.get('device')} in {out.get('seconds')} s -> {keep}")
    assert bg.size == (512, 512) and selftest._stddev(bg) > 6
    inp = selftest.sample_inputs()
    inp.background = bg
    sp = R.clean_spec({"format": "youtube", "style": "episode_card", "lang": "fa", "content": fixtures.sample_content("fa"), "background": {"kind": "ai"}}, STYLES)
    res = R.render(sp, inp, scale=0.6)
    assert not selftest.judge(res, F.get("youtube"))
    res.image.save(keep.with_name("covers-episode-card-real.png"))
    assert compute.workflow_available(st["workflow"])
