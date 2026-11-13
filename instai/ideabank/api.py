"""Idea bank API: list / search / filter, create, edit, copy, favourite, hide, random, generate more with the model, and start a project from an idea."""
from __future__ import annotations

from django.urls import path, register_converter
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.core.errors import DomainError

from . import bank
from .seed_base import CATEGORIES


class IdeaKeyConverter:
    """A bank idea key always starts with a letter (`mind_...`, `u_...`). The studio boards own `/ideas/<number>`; without this the bank's
    catch-all `ideas/<key>` answered those with 404."""
    regex = "[a-z][a-z0-9_]*"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return str(value)


register_converter(IdeaKeyConverter, "ideakey")


def _flag(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


@api_view(["GET", "POST"])
def ideas(request):
    if request.method == "POST":
        return Response(bank.create_idea(request.data if isinstance(request.data, dict) else {}), status=201)
    q = request.query_params
    rows = bank.list_ideas(q=q.get("q", ""), category=q.get("category", ""), tag=q.get("tag", ""), fmt=q.get("fmt", ""), favorite=_flag(q.get("favorite", "")),
                           source=q.get("source", ""), include_hidden=_flag(q.get("hidden", "")))
    return Response({"ideas": rows, **bank.facets(), "shown": len(rows)})


@api_view(["GET"])
def random_view(request):
    row = bank.random_idea(request.query_params.get("category", ""))
    if not row:
        raise DomainError("not_found", http_status=404)
    return Response(row)


@api_view(["POST"])
def generate_view(request):
    """Ask the text model for more ideas in a category. A job: it waits by itself when Ollama is not running; the new ideas appear as 'mine'."""
    from instai.jobs import queue
    from instai.jobs.api import job_response

    d = request.data if isinstance(request.data, dict) else {}
    category = str(d.get("category") or "mystery")
    if category not in CATEGORIES:
        raise DomainError("validation_error", "دستهٔ نامعتبر است.", http_status=400, details={"category": ["invalid"]}, message_en="Invalid category.")
    try:
        count = max(1, min(8, int(d.get("count") or 5)))
    except (TypeError, ValueError):
        count = 5
    job = queue.enqueue("ideas.generate", {"category": category, "count": count, "instruction": str(d.get("instruction") or "")[:500]},
                        title=f"ایده‌های تازه: {CATEGORIES[category]['fa']}")
    return job_response(job)


@api_view(["GET", "PATCH", "DELETE"])
def idea_detail(request, key):
    if request.method == "DELETE":
        bank.delete_idea(key)
        return Response(status=204)
    if request.method == "PATCH":
        return Response(bank.update_idea(key, request.data if isinstance(request.data, dict) else {}))
    row = bank.get_idea(key)
    if not row:
        raise DomainError("not_found", http_status=404)
    return Response(row)


@api_view(["POST"])
def idea_duplicate(request, key):
    return Response(bank.duplicate_idea(key, request.data if isinstance(request.data, dict) else {}), status=201)


@api_view(["POST"])
def idea_mark(request, key):
    d = request.data if isinstance(request.data, dict) else {}
    return Response(bank.set_mark(key, favorite=_flag(d["favorite"]) if "favorite" in d else None, hidden=_flag(d["hidden"]) if "hidden" in d else None))


@api_view(["POST"])
def idea_start(request, key):
    """«شروعِ پروژه از این ایده»: creates the series (and the page when none is given) and returns where to go next."""
    return Response(bank.start_project(key, request.data if isinstance(request.data, dict) else {}), status=201)


urlpatterns = [
    path("ideas", ideas),
    path("ideas/random", random_view),
    path("ideas/generate", generate_view),
    path("ideas/<ideakey:key>", idea_detail),
    path("ideas/<ideakey:key>/duplicate", idea_duplicate),
    path("ideas/<ideakey:key>/mark", idea_mark),
    path("ideas/<ideakey:key>/start", idea_start),
]
