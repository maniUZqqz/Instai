"""A GPU job whose service is not there yet WAITS and resumes by itself; it never ends as "failed" (review of 0.9.0: `choice.render` with AI pictures and `identity.sheets`
ended with "ComfyUI is not available" and the owner had to press the button again when the GPU PC came on)."""
from __future__ import annotations

import pytest

from instai.core import settings_store
from instai.gpu import compute
from instai.jobs.models import Job
from instai.providers.base import ProviderError
from tests.conftest import finish, run_jobs
from tests.test_choice_stories import make_page
from tests.test_identity import make_world

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def no_comfyui(monkeypatch):
    """A real image engine is chosen, but no PC can run any ComfyUI workflow (the GPU PC is off)."""
    settings_store.set_setting("image_engine", "comfyui")
    state = {"up": False}
    monkeypatch.setattr(compute, "workflow_available", lambda wid: state["up"])
    return state


def waiting(job_id: int) -> Job:
    j = Job.objects.get(pk=job_id)
    assert j.status == Job.QUEUED and j.wait_code == "comfy_down" and j.attempts == 0, (j.status, j.wait_code, j.attempts, j.error)
    assert "ComfyUI" in j.waiting_reason, j.waiting_reason          # a clear Persian reason, not a stack trace
    return j


def test_require_workflow_raises_the_waiting_error_and_passes_when_a_pc_can_run_it(monkeypatch):
    monkeypatch.setattr(compute, "workflow_available", lambda wid: False)
    with pytest.raises(ProviderError) as e:
        compute.require_workflow("flux_dev_fp8_t2i")
    assert e.value.wait == "comfy_down" and e.value.code == "comfy_down" and e.value.retryable and "ComfyUI" in e.value.fa
    monkeypatch.setattr(compute, "workflow_available", lambda wid: True)
    compute.require_workflow("flux_dev_fp8_t2i")


def test_choice_render_with_ai_pictures_waits_for_the_gpu_pc_and_then_finishes(api, worker, no_comfyui, monkeypatch, tmp_path):
    page = make_page(api)
    sid = api.post(f"/api/pages/{page['id']}/choice-stories", {"template": "prison_escape", "title": "فرار"}, format="json").json()["id"]
    assert api.patch(f"/api/choice-stories/{sid}", {"renderer": "image"}, format="json").status_code == 200
    assert api.post(f"/api/choice-stories/{sid}/approve", {}, format="json").status_code == 200
    r = api.post(f"/api/choice-stories/{sid}/render", {}, format="json")
    assert r.status_code == 202, r.content
    job_id = r.json()["job"]["id"]
    run_jobs(worker)
    waiting(job_id)                                                   # not failed: parked in the durable queue
    # the GPU PC comes on: the same job is released by the queue (no click) and finishes, with its attempts untouched
    from datetime import timedelta
    from types import SimpleNamespace

    from django.utils import timezone

    from instai.render.placeholders import make_placeholder

    def fake_run_task(c, kind, payload, inputs=None):
        out = tmp_path / "gen.png"
        make_placeholder(out, 1080, 1350, "fake ComfyUI", seed="x")
        return SimpleNamespace(of_kind=lambda *s: [out], cleanup=lambda: None, device="test-gpu")

    no_comfyui["up"] = True
    monkeypatch.setattr(compute, "run_task", fake_run_task)
    Job.objects.filter(pk=job_id).update(run_after=timezone.now() - timedelta(seconds=1))
    run_jobs(worker)
    j = Job.objects.get(pk=job_id)
    assert j.status == Job.SUCCEEDED and j.attempts == 1 and j.result["rendered"] > 0, (j.status, j.error)


def test_identity_sheets_wait_for_the_gpu_pc(api, worker, no_comfyui):
    page, series, ep = make_world()
    c = page.characters.get(name="رامین")
    from instai.identity import service

    service.edit_lock(c, {"anchor": "a blue stick figure"})
    r = api.post(f"/api/characters/{c.pk}/identity/sheets", {}, format="json")
    assert r.status_code == 202, r.content
    job_id = r.json()["job"]["id"]
    run_jobs(worker)
    waiting(job_id)


def test_design_sheet_pictures_wait_for_the_gpu_pc(api, worker, no_comfyui):
    page, series, ep = make_world()
    r = api.post(f"/api/episodes/{ep.pk}/studio/design-sheets", {"kind": "prop", "subject": "red scarf", "prompt": "a red scarf"}, format="json")
    assert r.status_code in (200, 201), r.content
    r = api.post(f"/api/design-sheets/{r.json()['id']}/image", {}, format="json")
    assert r.status_code == 202, r.content
    job_id = r.json()["job"]["id"]
    run_jobs(worker)
    waiting(job_id)


def test_the_stick_renderer_and_demo_mode_never_wait(api, worker):
    """Nothing changes for the work that needs no ComfyUI: stick pictures are drawn by code and demo mode uses placeholders."""
    page = make_page(api)
    sid = api.post(f"/api/pages/{page['id']}/choice-stories", {"template": "prison_escape", "title": "فرار"}, format="json").json()["id"]
    api.post(f"/api/choice-stories/{sid}/approve", {}, format="json")
    j = finish(api, worker, api.post(f"/api/choice-stories/{sid}/render", {}, format="json"))
    assert j["result"]["rendered"] > 0
