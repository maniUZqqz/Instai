"""The automatic self-test of this PC (0.14.0): the report, and a button to run it now.

  GET  /api/system/selftest   {report, running, current_stamp, stale, state, checks: [{key, group, fa, en}]}
  POST /api/system/selftest   {only: [keys]?}  -> a job (the GPU checks run too; the ones whose requirement is missing say "waiting")
"""
from __future__ import annotations

from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.jobs import queue
from instai.jobs.api import job_response
from instai.jobs.models import Job

from . import pcselftest


@api_view(["GET", "POST"])
def pc_selftest(request):
    if request.method == "POST":
        d = request.data if isinstance(request.data, dict) else {}
        only = [str(k) for k in (d.get("only") or []) if str(k) in pcselftest.BY_KEY][:20]
        gpu = (any(pcselftest.BY_KEY[k]["group"] == "gpu" for k in only)) if only else True
        busy = Job.objects.filter(kind="system.selftest", status__in=[Job.QUEUED, Job.RUNNING]).first()
        if busy is not None:                                   # one run at a time: the button pressed twice returns the one that is there
            return job_response(busy)
        return job_response(queue.enqueue("system.selftest", {"gpu": gpu, "only": only}, title="آزمون خودکار این رایانه"))
    rep = pcselftest.load_report()
    busy = Job.objects.filter(kind="system.selftest", status__in=[Job.QUEUED, Job.RUNNING]).exists()
    return Response({"report": rep, "running": busy, "current_stamp": pcselftest.stamp(), "stale": bool(rep and rep.get("stamp") != pcselftest.stamp()),
                     "state": (rep or {}).get("summary", {}).get("state"),
                     "checks": [{"key": c["key"], "group": c["group"], "fa": c["fa"], "en": c["en"]} for c in pcselftest.CHECKS]})


urlpatterns = [
    path("system/selftest", pc_selftest),
]
