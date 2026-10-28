"""Studio API: format templates, the development room of a series, and pre-production of an episode."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from instai.agents import llm
from instai.core.errors import DomainError
from instai.jobs import queue
from instai.jobs.api import JobSerializer, job_response
from instai.jobs.models import Job
from instai.pages import formats
from instai.pages.models import ContentPage
from instai.story import services as story_services
from instai.story.api import _source, series_dict
from instai.story.models import Episode, Series, Shot
from instai.styles import library

from . import gates, preprod, services, templates
from .models import DesignSheet, FormatTemplate, Idea, ResearchDoc, RetakeRequest

LANGS = ("fa", "en")


def bad(msg: str, **details) -> DomainError:
    return services.bad(msg, **details)


def _series(pk) -> Series:
    return get_object_or_404(Series.objects.select_related("page"), pk=pk)


def _ep(pk) -> Episode:
    return get_object_or_404(Episode.objects.select_related("series__page"), pk=pk)


def _lang(request) -> str:
    v = str(request.data.get("language") or request.headers.get("X-Lang") or "")[:2]
    return v if v in LANGS else ""


def _unique_template_key(base: str) -> str:
    base = templates.slug(base)
    key, n = f"tpl_{base}"[:55], 2
    while key in templates.BUILTIN_TEMPLATES or FormatTemplate.objects.filter(key=key).exists():
        key, n = f"tpl_{base}"[:50] + f"_{n}", n + 1
    return key


# ================================================================== templates

@api_view(["GET", "POST"])
def templates_view(request):
    if request.method == "POST":
        d = request.data if isinstance(request.data, dict) else {}
        name = str(d.get("name_en") or d.get("name_fa") or "").strip()
        if not name:
            raise bad("نام قالب لازم است.", name_en=["required"])
        key = _unique_template_key(d.get("key") or name)
        FormatTemplate.objects.create(key=key, data=templates.normalize_template(d, key=key))
        return Response(templates.get_template(key), status=201)
    return Response({"templates": templates.all_templates(), "step_kinds": templates.STEP_KINDS,
                     "lenses": [{"key": k, **v} for k, v in templates.LENSES.items()], "formats": list(formats.FORMATS)})


@api_view(["GET", "PATCH", "DELETE"])
def template_detail(request, key):
    if request.method == "GET":
        t = templates.get_template(key)
        if t["key"] != key:
            raise DomainError("not_found", http_status=404)
        return Response(t)
    if key in templates.BUILTIN_TEMPLATES:
        raise DomainError("conflict", "قالب‌های پیش‌فرض را نمی‌توان تغییر داد؛ از آن کپی بگیرید.")
    row = FormatTemplate.objects.filter(key=key).first()
    if not row:
        raise DomainError("not_found", http_status=404)
    if request.method == "DELETE":
        in_use = Series.objects.filter(template_key=key).count() + ContentPage.objects.filter(template_key=key).count()
        if in_use:
            raise DomainError("conflict", f"این قالب در {in_use} صفحه/مجموعه استفاده می‌شود و حذف نمی‌شود.")
        row.delete()
        return Response(status=204)
    row.data = templates.normalize_template({**templates.get_template(key), **request.data}, key=key)
    row.save()
    return Response(templates.get_template(key))


@api_view(["POST"])
def template_duplicate(request, key):
    src = templates.get_template(key)
    if src["key"] != key:
        raise DomainError("not_found", http_status=404)
    data = {**src, "name_en": (src["name_en"] or "Template") + " (copy)", "name_fa": (src["name_fa"] or "قالب") + " (کپی)"}
    data.pop("key", None)
    data.pop("builtin", None)
    k = _unique_template_key(f"{key}_copy")
    FormatTemplate.objects.create(key=k, data=templates.normalize_template(data, key=k))
    return Response(templates.get_template(k), status=201)


# ================================================================== development room

def _look(series: Series) -> dict:
    vis = series.page.profile("visual")
    look = {"style_key": vis.get("style_key", ""), "realism": vis.get("realism", ""), "theme_key": vis.get("theme_key", ""), **(series.look or {})}
    st = library.get_style(look["style_key"]) or {}
    return {**look, "style_name_fa": st.get("name_fa", ""), "style_name_en": st.get("name_en", ""), "inherited": not series.look}


def development_payload(series: Series) -> dict:
    services.ensure_steps(series)
    page = series.page
    tpl = services.template_of(series)
    rows = {r.key: r for r in series.dev_steps.all()}
    steps = []
    for st in tpl["steps"]:
        r = rows[st["key"]]
        item = {**st, "status": r.status, "auto_approved": r.auto_approved, "approved_at": r.approved_at, "needs_human": gates.dev_step_needs_human(page, st["kind"]),
                "has_content": services.has_content(series, r, st), "data": r.data if st["kind"] in ("map", "timeline", "profile") else None}
        if st["kind"] == "brainstorm":
            qs = series.ideas.filter(board=st["params"].get("board", st["key"]))
            item["counts"] = {"total": qs.count(), "approved": qs.filter(status="approved").count(), "rejected": qs.filter(status="rejected").count()}
        steps.append(item)
    boards = {st["params"].get("board", st["key"]) for st in tpl["steps"] if st["kind"] == "brainstorm"}
    running = [j for j in Job.objects.filter(kind__startswith="studio.", status__in=[Job.QUEUED, Job.RUNNING]) if (j.payload or {}).get("series_id") == series.pk]
    return {
        "series": series_dict(series), "template": {k: tpl[k] for k in ("key", "name_fa", "name_en", "base_format", "needs_source", "builtin")}, "steps": steps,
        "ideas": {b: [services.idea_dict(i) for i in series.ideas.filter(board=b)] for b in boards},
        "research": {d.kind: services.doc_dict(d) for d in series.research_docs.all()},
        "sources": [_source(s) for s in series.sources.filter(episode__isnull=True)],
        "bible": services.bible_dict(series), "source": series.source or {}, "look": _look(series),
        "languages": series.languages or page.languages or ["fa"], "dev_status": series.dev_status, "dev_approved_at": series.dev_approved_at,
        "automation_level": page.automation_level, "running_jobs": JobSerializer(running, many=True).data, "has_plan": series.episodes.exists(),
    }


@api_view(["GET", "PATCH"])
def development(request, pk):
    s = _series(pk)
    if request.method == "PATCH":
        d = request.data
        if "template_key" in d:
            if d["template_key"] and templates.get_template(d["template_key"])["key"] != d["template_key"]:
                raise bad("قالب نامعتبر است.", template_key=["invalid"])
            s.template_key = d["template_key"] or ""
        if "languages" in d:
            langs = [l for l in (d["languages"] or []) if l in LANGS]
            if d["languages"] and not langs:
                raise bad("زبان نامعتبر است.", languages=["invalid"])
            s.languages = langs
        if "look" in d:
            look = d["look"] if isinstance(d["look"], dict) else {}
            s.look = {k: v for k, v in look.items() if k in ("style_key", "realism", "theme_key") and v}
        s.save()
    return Response(development_payload(s))


@api_view(["POST"])
def step_status(request, pk, key):
    s = _series(pk)
    services.set_step_status(s, key, str(request.data.get("status") or ""))
    return Response(development_payload(s))


@api_view(["PUT"])
def step_data(request, pk, key):
    s = _series(pk)
    services.save_step_data(s, key, request.data.get("data") if isinstance(request.data.get("data"), dict) else request.data)
    return Response(development_payload(s))


GENERATE_JOBS = {"map": ("studio.map", "پیامدهای تغییر"), "timeline": ("studio.timeline", "خط زمانی جایگزین"), "profile": ("studio.profile", "کتاب شخصیت")}


@api_view(["POST"])
def step_generate(request, pk, key):
    s = _series(pk)
    services.ensure_steps(s)
    sdef = services.step_def(s, key)
    if sdef["kind"] not in GENERATE_JOBS:
        raise bad("این مرحله تولید خودکار ندارد.")
    kind, title = GENERATE_JOBS[sdef["kind"]]
    payload = {"series_id": s.pk, "step_key": key, "instruction": str(request.data.get("instruction") or ""), "language": _lang(request)}
    if sdef["kind"] == "profile":
        payload["brief"] = str(request.data.get("brief") or "")
    return job_response(queue.enqueue(kind, payload, page=s.page_id, title=title))


@api_view(["POST"])
def source_search(request, pk):
    s = _series(pk)
    q = str(request.data.get("query") or "").strip()
    if not q:
        raise bad("نامِ سریال را بنویسید.", query=["required"])
    providers = [p for p in (request.data.get("providers") or []) if isinstance(p, str)]
    job = queue.enqueue("studio.source_search", {"series_id": s.pk, "query": q, "providers": providers, "language": _lang(request) or "en",
                                                  "fandom_wiki": str(request.data.get("fandom_wiki") or "")}, page=s.page_id, title=f"جست‌وجوی سریال: {q}"[:120])
    return job_response(job)


@api_view(["POST"])
def source_choose(request, pk):
    s = _series(pk)
    d = request.data
    cand = d.get("candidate") if isinstance(d.get("candidate"), dict) else d
    services.set_source(s, {**cand, "manual": bool(d.get("manual")), "notes": d.get("notes", cand.get("notes", ""))})
    return Response(development_payload(s))


@api_view(["POST"])
def source_clear(request, pk):
    s = _series(pk)
    s.source, s.franchise = {}, ""
    s.save(update_fields=["source", "franchise", "updated_at"])
    return Response(development_payload(s))


@api_view(["POST"])
def research_run(request, pk):
    s = _series(pk)
    mode = request.data.get("mode") if request.data.get("mode") in ("canon", "topic") else "topic"
    services.ensure_steps(s)
    sdef = next((st for st in services.template_of(s)["steps"] if st["kind"] == "research" and st["params"].get("mode") == mode), None)
    job = queue.enqueue("studio.research", {"series_id": s.pk, "mode": mode, "topic": str(request.data.get("topic") or ""), "step_key": sdef["key"] if sdef else "",
                                            "language": _lang(request), "wikipedia": bool(request.data.get("wikipedia", True))},
                        page=s.page_id, title="پژوهش کانن" if mode == "canon" else "پژوهش با منبع")
    return job_response(job)


@api_view(["PATCH"])
def research_doc(request, pk):
    doc = get_object_or_404(ResearchDoc, pk=pk)
    services.update_research_doc(doc, request.data)
    return Response(services.doc_dict(doc))


# ------------------------------------------------------------------ ideas

@api_view(["GET", "POST"])
def series_ideas(request, pk):
    s = _series(pk)
    board = str(request.query_params.get("board") or request.data.get("board") or "")
    if request.method == "POST":
        if not board:
            raise bad("تختهٔ ایده مشخص نیست.", board=["required"])
        idea = services.add_idea(s, board, request.data, author="human", language=_lang(request))
        return Response(services.idea_dict(idea), status=201)
    qs = s.ideas.filter(board=board) if board else s.ideas.all()
    return Response([services.idea_dict(i) for i in qs])


@api_view(["PATCH", "DELETE"])
def idea_detail(request, pk):
    i = get_object_or_404(Idea, pk=pk)
    if request.method == "DELETE":
        i.delete()
        return Response(status=204)
    return Response(services.idea_dict(services.update_idea(i, request.data)))


@api_view(["POST"])
def idea_status(request, pk):
    i = get_object_or_404(Idea, pk=pk)
    return Response(services.idea_dict(services.set_idea_status(i, str(request.data.get("status") or ""))))


@api_view(["POST"])
def idea_rate(request, pk):
    i = get_object_or_404(Idea, pk=pk)
    return Response(services.idea_dict(services.rate_idea(i, int(request.data.get("rating") or 0))))


@api_view(["POST"])
def ideas_generate(request, pk):
    s = _series(pk)
    board = str(request.data.get("board") or "")
    services.ensure_steps(s)
    if not services.step_for_board(s, board):
        raise bad("تختهٔ ایده نامعتبر است.", board=["invalid"])
    payload = {"series_id": s.pk, "board": board, "count": int(request.data.get("count") or 0), "instruction": str(request.data.get("instruction") or ""),
               "more_like": [int(x) for x in (request.data.get("more_like") or []) if str(x).isdigit()], "language": _lang(request)}
    return job_response(queue.enqueue("studio.ideas", payload, page=s.page_id, title="ایده‌پردازی"))


@api_view(["POST"])
def idea_refine(request, pk):
    i = get_object_or_404(Idea.objects.select_related("series__page"), pk=pk)
    return job_response(queue.enqueue("studio.idea_refine", {"idea_id": i.pk, "series_id": i.series_id, "instruction": str(request.data.get("instruction") or ""),
                                                             "language": _lang(request)}, page=i.series.page_id, title="بازنویسی ایده"))


@api_view(["POST"])
def ideas_merge(request, pk):
    s = _series(pk)
    ids = [int(x) for x in (request.data.get("ids") or []) if str(x).isdigit()]
    cards = list(Idea.objects.filter(series=s, pk__in=ids))
    if len(cards) < 2:
        raise bad("برای ادغام حداقل دو ایده لازم است.", ids=["too_few"])
    if request.data.get("ai"):
        return job_response(queue.enqueue("studio.idea_merge", {"series_id": s.pk, "ids": ids, "instruction": str(request.data.get("instruction") or ""),
                                                                "language": _lang(request)}, page=s.page_id, title="ادغام ایده‌ها"))
    card = services.merge_ideas(s, ids, services.local_merge(cards), language=_lang(request))
    return Response({"idea": services.idea_dict(card)}, status=201)


# ------------------------------------------------------------------ bible, characters, approvals

@api_view(["GET", "PUT"])
def bible(request, pk):
    s = _series(pk)
    if request.method == "PUT":
        services.save_bible(s, request.data.get("data") if isinstance(request.data.get("data"), dict) else request.data)
    return Response(services.bible_dict(s))


@api_view(["POST"])
def bible_generate(request, pk):
    s = _series(pk)
    return job_response(queue.enqueue("studio.bible", {"series_id": s.pk, "instruction": str(request.data.get("instruction") or ""),
                                                       "keep_existing": bool(request.data.get("keep_existing")), "language": _lang(request)},
                                      page=s.page_id, title="کتاب سریال"))


@api_view(["POST"])
def bible_approve(request, pk):
    return Response(services.approve_bible(_series(pk)))


@api_view(["POST"])
def bible_revoke(request, pk):
    return Response(services.revoke_bible(_series(pk)))


@api_view(["POST"])
def profile_sync(request, pk, key):
    s = _series(pk)
    return Response({"characters_added": services.sync_profile_characters(s, services.get_step(s, key))})


@api_view(["POST"])
def development_approve(request, pk):
    s = _series(pk)
    services.approve_development(s)
    return Response(development_payload(s))


@api_view(["POST"])
def development_reopen(request, pk):
    s = _series(pk)
    services.reopen_development(s)
    return Response(development_payload(s))


# ================================================================== pre-production

@api_view(["GET"])
def episode_studio(request, pk):
    return Response(preprod.studio_payload(_ep(pk)))


@api_view(["POST"])
def animatic_build(request, pk):
    e = _ep(pk)
    if not story_services.all_shots(e):
        raise DomainError("not_ready", "ابتدا استوری‌بورد را بسازید.")
    return job_response(queue.enqueue("studio.animatic", {"episode_id": e.pk}, episode=e, page=e.series.page_id, title=f"انیماتیک قسمت {e.number}"))


@api_view(["POST"])
def design_generate(request, pk):
    e = _ep(pk)
    return job_response(queue.enqueue("studio.design", {"episode_id": e.pk, "language": _lang(request)}, episode=e, page=e.series.page_id,
                                      title=f"برگه‌های طراحی قسمت {e.number}"))


@api_view(["GET", "POST"])
def design_sheets(request, pk):
    e = _ep(pk)
    if request.method == "POST":
        return Response(preprod.sheet_dict(preprod.add_sheet(e, request.data)), status=201)
    return Response([preprod.sheet_dict(s) for s in e.design_sheets.select_related("asset")])


@api_view(["PATCH", "DELETE"])
def design_sheet(request, pk):
    s = get_object_or_404(DesignSheet.objects.select_related("episode__series__page"), pk=pk)
    if request.method == "DELETE":
        ep = s.episode
        s.delete()
        if ep:
            preprod.clear_approval(ep, "design")
        return Response(status=204)
    return Response(preprod.sheet_dict(preprod.update_sheet(s, request.data)))


@api_view(["POST"])
def design_image(request, pk):
    s = get_object_or_404(DesignSheet.objects.select_related("episode__series__page"), pk=pk)
    return job_response(queue.enqueue("studio.design_image", {"sheet_id": s.pk, "seed": request.data.get("seed")}, episode=s.episode_id, page=s.page_id,
                                      title=f"تصویر برگهٔ طراحی: {s.subject}"[:120]))


@api_view(["POST"])
def casting_suggest(request, pk):
    e = _ep(pk)
    return job_response(queue.enqueue("studio.casting", {"episode_id": e.pk, "language": _lang(request)}, episode=e, page=e.series.page_id,
                                      title="پیشنهاد انتخاب صدا"))


@api_view(["PUT"])
def casting_set(request, pk):
    e = _ep(pk)
    rows = request.data.get("casting") if isinstance(request.data.get("casting"), list) else []
    chars = {c.pk: c for c in e.series.page.characters.all()}
    for r in rows:
        c = chars.get(int(r.get("character") or 0))
        if c:
            preprod.set_voice(c, str(r.get("voice_id") or ""), str(r.get("language") or ""))
    preprod.clear_approval(e, "casting")
    return Response(preprod.studio_payload(e))


@api_view(["POST"])
def stage_approve(request, pk, key):
    e = _ep(pk)
    preprod.approve_stage(e, key)
    return Response(preprod.studio_payload(e))


@api_view(["POST"])
def stage_revoke(request, pk, key):
    e = _ep(pk)
    preprod.revoke_stage(e, key)
    return Response(preprod.studio_payload(e))


@api_view(["POST"])
def episode_translate(request, pk):
    e = _ep(pk)
    lang = str(request.data.get("language") or "")[:2]
    if lang not in LANGS:
        raise bad("زبان مقصد نامعتبر است.", language=["invalid"])
    return job_response(queue.enqueue("studio.translate", {"episode_id": e.pk, "language": lang}, episode=e, page=e.series.page_id, title=f"ترجمهٔ قسمت {e.number}"))


@api_view(["POST"])
def shot_retake(request, pk):
    s = get_object_or_404(Shot.objects.select_related("scene__episode__series__page"), pk=pk)
    reason = str(request.data.get("reason") or "").strip()
    if not reason:
        raise bad("دلیل بازسازی را بنویسید.", reason=["required"])
    r, jobs = preprod.request_retake(s, str(request.data.get("scope") or "keyframe"), reason, mode=str(request.data.get("mode") or "preview"))
    return Response({"retake": preprod.retake_dict(r), "jobs": JobSerializer(jobs, many=True).data}, status=202)


@api_view(["GET"])
def episode_retakes(request, pk):
    e = _ep(pk)
    return Response([preprod.retake_dict(r) for r in e.retakes.select_related("shot__scene")])


@api_view(["POST"])
def retake_cancel(request, pk):
    r = get_object_or_404(RetakeRequest, pk=pk)
    r.status = "cancelled"
    r.save(update_fields=["status"])
    return Response(preprod.retake_dict(r))


@api_view(["GET"])
def voice_options(request):
    return Response(preprod.voice_options(str(request.query_params.get("language") or "")))


@api_view(["GET"])
def llm_groups(request):
    page = ContentPage.objects.filter(pk=request.query_params.get("page")).first() if request.query_params.get("page") else None
    return Response({"groups": llm.GROUPS, "resolved": llm.describe(page) if page else None})


urlpatterns = [
    path("templates", templates_view),
    path("templates/<str:key>", template_detail),
    path("templates/<str:key>/duplicate", template_duplicate),
    path("series/<int:pk>/development", development),
    path("series/<int:pk>/development/approve", development_approve),
    path("series/<int:pk>/development/reopen", development_reopen),
    path("series/<int:pk>/dev/steps/<str:key>/status", step_status),
    path("series/<int:pk>/dev/steps/<str:key>/data", step_data),
    path("series/<int:pk>/dev/steps/<str:key>/generate", step_generate),
    path("series/<int:pk>/dev/steps/<str:key>/sync-characters", profile_sync),
    path("series/<int:pk>/source/search", source_search),
    path("series/<int:pk>/source", source_choose),
    path("series/<int:pk>/source/clear", source_clear),
    path("series/<int:pk>/research", research_run),
    path("research-docs/<int:pk>", research_doc),
    path("series/<int:pk>/ideas", series_ideas),
    path("series/<int:pk>/ideas/generate", ideas_generate),
    path("series/<int:pk>/ideas/merge", ideas_merge),
    path("ideas/<int:pk>", idea_detail),
    path("ideas/<int:pk>/status", idea_status),
    path("ideas/<int:pk>/rate", idea_rate),
    path("ideas/<int:pk>/refine", idea_refine),
    path("series/<int:pk>/bible", bible),
    path("series/<int:pk>/bible/generate", bible_generate),
    path("series/<int:pk>/bible/approve", bible_approve),
    path("series/<int:pk>/bible/revoke", bible_revoke),
    path("episodes/<int:pk>/studio", episode_studio),
    path("episodes/<int:pk>/studio/animatic", animatic_build),
    path("episodes/<int:pk>/studio/design/generate", design_generate),
    path("episodes/<int:pk>/studio/design-sheets", design_sheets),
    path("design-sheets/<int:pk>", design_sheet),
    path("design-sheets/<int:pk>/image", design_image),
    path("episodes/<int:pk>/studio/casting/suggest", casting_suggest),
    path("episodes/<int:pk>/studio/casting", casting_set),
    path("episodes/<int:pk>/studio/stages/<str:key>/approve", stage_approve),
    path("episodes/<int:pk>/studio/stages/<str:key>/revoke", stage_revoke),
    path("episodes/<int:pk>/translate", episode_translate),
    path("episodes/<int:pk>/retakes", episode_retakes),
    path("shots/<int:pk>/retake", shot_retake),
    path("retakes/<int:pk>/cancel", retake_cancel),
    path("voice-options", voice_options),
    path("llm/groups", llm_groups),
]
