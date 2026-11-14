"""Living next to the NMarketing agent (0.12.0): the voice servers InstAI started hold VRAM too. The NMarketing agent cannot stop a server it did not
start, so a quiet InstAI stops its own (together with the ComfyUI /free it already did) - and only when it has no GPU work."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def voice(monkeypatch):
    from instai.gpu import coexist
    from instai.providers.audio import services

    stopped: list[int] = []
    monkeypatch.setattr(services.MANAGER, "procs", {"moss": object()})
    monkeypatch.setattr(services, "unload_voice", lambda: stopped.append(1))
    coexist.STATE["released_at"] = 0.0
    return stopped


def test_a_quiet_instai_stops_the_voice_servers_it_started(voice):
    from instai.gpu import coexist

    res = coexist.release_idle(idle_for=10 ** 6)
    assert voice == [1] and res["voice"] is True and res["freed"] is True
    assert res["reason"] == "comfy_down", "ComfyUI is not running in the tests; the voice release does not depend on it"
    assert coexist.release_idle(idle_for=10 ** 6)["reason"] == "already" and voice == [1], "once per quiet period"


def test_nothing_to_stop_when_instai_started_no_voice_server(monkeypatch):
    from instai.gpu import coexist
    from instai.providers.audio import services

    monkeypatch.setattr(services.MANAGER, "procs", {})
    monkeypatch.setattr(services, "unload_voice", lambda: pytest.fail("no server of ours is running"))
    coexist.STATE["released_at"] = 0.0
    res = coexist.release_idle(idle_for=10 ** 6)
    assert res["voice"] is False and res["freed"] is False


def test_a_busy_or_just_finished_instai_keeps_its_voice_servers(voice):
    from instai.gpu import coexist
    from instai.jobs import queue
    from instai.jobs.models import Job

    job = queue.enqueue("prod.keyframes", {}, resource="gpu", title="gpu job")
    assert coexist.release_idle()["reason"] == "queued" and voice == []
    Job.objects.filter(pk=job.pk).update(status=Job.RUNNING)
    assert coexist.release_idle()["reason"] == "running" and voice == []
    Job.objects.filter(pk=job.pk).update(status=Job.SUCCEEDED, finished_at=timezone.now() - timedelta(seconds=5))
    assert coexist.release_idle()["reason"] == "recent" and voice == [], "the next shot may need the voice again"
    Job.objects.filter(pk=job.pk).update(finished_at=timezone.now() - timedelta(seconds=coexist.IDLE_RELEASE_SECONDS + 5))
    assert coexist.release_idle()["voice"] is True and voice == [1]


def test_a_voice_server_that_cannot_be_stopped_never_breaks_the_release(monkeypatch):
    from instai.gpu import coexist
    from instai.providers.audio import services

    def boom():
        raise RuntimeError("access denied")

    monkeypatch.setattr(services.MANAGER, "procs", {"sfx": object()})
    monkeypatch.setattr(services, "unload_voice", boom)
    coexist.STATE["released_at"] = 0.0
    res = coexist.release_idle(idle_for=10 ** 6)
    assert res["voice"] is False and res["reason"] == "comfy_down"
