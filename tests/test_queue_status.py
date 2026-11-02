"""The queue says exactly what is happening: what step, what it is for (page / series / episode / shot), which model on which device, the live line
(tokens so far, sampler step x of y), an estimate - in plain Persian and English. Plus the Persian error line of a failed job."""
from __future__ import annotations

import pytest

from tests import fakes
from tests.conftest import finish

pytestmark = pytest.mark.django_db(transaction=True)
GB = 1024 ** 3


def make_episode():
    from instai.pages.models import ContentPage
    from instai.story.models import Episode, Series

    page = ContentPage.objects.create(name="صفحهٔ تاریخ")
    series = Series.objects.create(page=page, title="اگر رم سقوط نمی‌کرد")
    return Episode.objects.create(series=series, number=3, title="شبِ آتش")


def job(kind="story.script", status="running", live=None, episode=None, resource="gpu", **kw):
    from instai.jobs.models import Job
    from django.utils import timezone

    return Job.objects.create(kind=kind, status=status, resource=resource, live=live or {}, episode=episode,
                              page_id=episode.series.page_id if episode else None, started_at=timezone.now() if status == "running" else None, **kw)


def act(j):
    from instai.jobs.describe import activity

    j.refresh_from_db()
    return activity(j)


def test_llm_job_says_step_target_model_device_and_tokens():
    ep = make_episode()
    a = act(job(live={"phase": "generating", "model": "qwen3:8b", "device": "gpu", "gpu_pct": 100, "tokens": 120, "tps": 18.2}, episode=ep))
    assert a["title_fa"] == "نوشتن فیلم‌نامه" and a["title_en"] == "Writing the script"
    assert a["for_fa"] == "صفحهٔ «صفحهٔ تاریخ» · سریال «اگر رم سقوط نمی‌کرد» · قسمت ۳ «شبِ آتش»"
    assert a["for_en"] == "page “صفحهٔ تاریخ” · series “اگر رم سقوط نمی‌کرد” · episode 3 “شبِ آتش”"
    assert a["model"] == "qwen3:8b" and a["device"] == "gpu" and a["warn"] is False and "GPU" in a["device_fa"]
    assert a["phase"] == "generating" and a["tokens"] == 120 and a["tps"] == 18.2
    assert a["line_fa"] == "۱۲۰ توکن تا الان نوشته شد · ۱۸٫۲ توکن در ثانیه" and a["line_en"] == "120 tokens written so far · 18.2 tokens/s"


def test_a_model_partly_on_the_cpu_is_flagged_as_slow():
    a = act(job(live={"phase": "generating", "model": "qwq:32b", "device": "mixed", "gpu_pct": 38, "tokens": 5}))
    assert a["device"] == "mixed" and a["warn"] is True
    assert "۳۸٪" in a["device_fa"] and "CPU" in a["device_fa"] and "کند" in a["device_fa"] and "38%" in a["device_en"]
    c = act(job(live={"phase": "generating", "model": "qwq:32b", "device": "cpu", "gpu_pct": 0}))
    assert c["device"] == "cpu" and c["warn"] is True and "نه کارت گرافیک" in c["device_fa"], "a GPU job that really runs on the CPU says so"
    cpu_job = act(job(kind="prod.assemble", resource="cpu", live={"device": "cpu"}))
    assert cpu_job["warn"] is False and cpu_job["device_fa"] == "روی CPU", "ffmpeg on the CPU is normal"


def test_comfyui_shot_job_shows_step_of_steps_and_the_shot():
    ep = make_episode()
    a = act(job(kind="prod.keyframes", live={"phase": "sampling", "step": 8, "steps": 20, "eta_sec": 95, "shot": 3, "shots": 8, "model": "FLUX.1 [dev] FP8",
                                              "device": "gpu"}, episode=ep))
    assert a["title_fa"] == "ساخت تصویرهای کلیدی" and a["for_fa"].endswith("شات ۳ از ۸") and a["for_en"].endswith("shot 3 of 8")
    assert a["line_fa"] == "گام ۸ از ۲۰" and a["line_en"] == "step 8 of 20" and a["eta_sec"] == 95 and a["step"] == 8 and a["steps"] == 20
    assert a["model"] == "FLUX.1 [dev] FP8" and a["device"] == "gpu"


def test_phases_before_the_first_token_or_step_are_explained():
    texts = {p: act(job(live={"phase": p}))["line_fa"] for p in ("loading_model", "prefill", "starting_comfy", "speaking", "retry")}
    assert "بارگذاری" in texts["loading_model"] and "اولین کلمه" in texts["prefill"] and "ComfyUI" in texts["starting_comfy"]
    assert "صدا" in texts["speaking"] and "تلاش" in texts["retry"]
    assert act(job(live={"phase": "generating", "tokens": 3, "attempt": 2, "attempts": 3}))["line_fa"].startswith("تلاش ۲ از ۳")


def test_waiting_for_the_gpu_is_translated():
    a = act(job(waiting_reason="GPU busy: another program uses 8.1 GB of VRAM"))
    assert a["phase"] == "waiting_gpu" and "۸٫۱ گیگابایت" in a["line_fa"] and a["line_en"].startswith("GPU busy")
    assert "منتظر" in act(job(waiting_reason="waiting for another GPU job of InstAI"))["line_fa"]


def test_queued_job_and_planned_device():
    q = act(job(status="queued", resource="gpu"))
    assert q["phase"] == "queued" and "در صف" in q["line_fa"] and q["device"] == "gpu" and "قرار است" in q["device_fa"]
    assert act(job(status="queued", resource="net"))["device"] == "net"


def test_finished_job_keeps_what_it_used_but_makes_no_promise():
    done = act(job(status="succeeded", live={"model": "qwen3:8b", "device": "gpu", "tokens": 900}))
    assert done["model"] == "qwen3:8b" and done["device"] == "gpu" and done["line_fa"] == ""
    bare = act(job(status="failed", resource="gpu"))
    assert bare["device"] == "" and bare["device_fa"] == ""


def test_estimate_when_the_code_has_none_comes_from_the_job_estimate():
    from datetime import timedelta

    from django.utils import timezone

    j = job(estimated_sec=600)
    j.started_at = timezone.now() - timedelta(seconds=100)
    j.save()
    assert 480 <= act(j)["eta_sec"] <= 500


def test_job_api_carries_live_and_activity_and_does_not_query_per_job(api, django_assert_max_num_queries):
    ep = make_episode()
    ids = [job(episode=ep, live={"phase": "generating", "tokens": i, "model": "m", "device": "gpu"}).pk for i in range(1, 9)]
    d = api.get(f"/api/jobs/{ids[0]}").json()
    assert d["live"]["tokens"] == 1 and d["activity"]["title_fa"] == "نوشتن فیلم‌نامه" and d["activity"]["for_fa"].startswith("صفحهٔ «")
    with django_assert_max_num_queries(14):
        m = api.get("/api/monitor").json()
    assert len(m["active"]) == 8 and all(j["activity"]["for_en"].startswith("page") for j in m["active"])
    assert {j["activity"]["tokens"] for j in m["active"]} == set(range(1, 9))


def test_live_is_throttled_and_flushed(monkeypatch):
    from instai.jobs import queue
    from instai.jobs.context import JobContext
    from instai.jobs.models import Job

    queue.enqueue("models.test", {"id": "x"}, resource="cpu")
    j = queue.claim("w", ("cpu",))
    ctx = JobContext(j, "w")
    ctx.live(phase="generating", tokens=1)                  # first write goes out at once
    assert Job.objects.get(pk=j.pk).live == {"phase": "generating", "tokens": 1}
    ctx.live(tokens=2)
    ctx.live(tokens=3)                                      # inside the same second: kept in memory
    assert Job.objects.get(pk=j.pk).live["tokens"] == 1
    ctx.flush_live()
    assert Job.objects.get(pk=j.pk).live["tokens"] == 3
    ctx.live(phase="parsing")                               # a phase change is written at once
    assert Job.objects.get(pk=j.pk).live["phase"] == "parsing"
    ctx.live(tokens=None)                                   # None removes a key
    ctx.flush_live()
    assert "tokens" not in Job.objects.get(pk=j.pk).live
    queue.requeue(Job.objects.get(pk=j.pk))
    assert Job.objects.get(pk=j.pk).live == {}, "a new run starts with a clean slate"


def test_a_provider_error_is_stored_with_its_persian_line_first(worker):
    from instai.jobs import queue, registry
    from instai.jobs.models import Job
    from instai.providers.base import ProviderError

    def boom(ctx):
        raise ProviderError("Ollama sent nothing for 900 s (model qwq:32b)", retryable=False, code="llm_timeout",
                            fa="مدل «qwq:32b» تا ۹۰۰ ثانیه هیچ پاسخی نداد. مدل کوچک‌تری انتخاب کنید.")

    registry.HANDLERS["test.boom"] = boom
    try:
        j = queue.enqueue("test.boom", resource="cpu", max_attempts=1)
        worker.drain()
    finally:
        registry.HANDLERS.pop("test.boom", None)
    j = Job.objects.get(pk=j.pk)
    lines = j.error.splitlines()
    assert j.status == "failed" and j.error_code == "llm_timeout"
    assert lines[0].startswith("مدل «qwq:32b»") and lines[1].startswith("Ollama sent nothing"), "Persian first (what to do), English technical text after"


def test_story_strategy_through_streaming_ollama_shows_model_and_device(api, worker, monkeypatch):
    """The job the owner saw time out: a story.strategy run on Ollama. It streams, picks a model that fits the card, and the queue knows the details."""
    from instai.core import hardware, settings_store

    monkeypatch.setattr(hardware, "gpu_status", lambda: {"name": "NVIDIA GeForce RTX 3060", "total_mb": 12288, "used_mb": 900, "free_mb": 11388, "driver": "x",
                                                          "utilization": 1, "temperature": 40, "processes": []})
    details = {"qwq:32b": {"size": int(19.9e9), "parameter_size": "32.8B"}, "qwen3:8b": {"size": int(5.2e9), "parameter_size": "8.2B"}}
    with fakes.ollama_server(models=("qwq:32b", "qwen3:8b"), loaded=("qwq:32b",), details=details, placement={"qwen3:8b": (5 * GB, 5 * GB)}, pieces=10) as o:
        settings_store.set_setting("llm_provider", "ollama")
        settings_store.set_setting("ollama_url", o.url)
        try:
            j = finish(api, worker, api.post("/api/strategy", {"page_name": "صفحه", "format": "anime_whatif", "language": "fa", "idea": "ایده"}, format="json"))
        finally:
            settings_store.set_setting("llm_provider", "")
            settings_store.set_setting("ollama_url", "")
        assert j["result"]["strategy"]
        chats = [r["body"] for r in o.requests if r["path"] == "/api/chat"]
        assert chats and all(c["model"] == "qwen3:8b" and c["stream"] is True for c in chats), "the model that fits, not the first or biggest one"
        assert {"model": "qwq:32b", "keep_alive": 0} in [r["body"] for r in o.requests if r["path"] == "/api/generate"], "the model left in VRAM was unloaded first"
        assert j["live"]["model"] == "qwen3:8b" and j["live"]["device"] == "gpu"
        a = j["activity"]
        assert a["title_fa"] == "پیشنهاد استراتژی صفحه" and a["model"] == "qwen3:8b" and a["device"] == "gpu" and a["tokens"] == 100
