"""Choice-story jobs: plan the graph (model, with the skeleton as the fallback), write the captions, render the post pictures, build the package."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from instai.agents import llm
from instai.agents import pipeline_roles as roles
from instai.agents.runner import AgentError
from instai.assets import storage as asset_storage
from instai.jobs import describe
from instai.jobs.registry import handler

from . import export, render, services, story_templates
from . import graph as G
from .models import ChoiceStory

describe.KIND_TEXT.update({
    "choice.plan": ("طراحی نمودار داستان انتخابی", "Planning the choice-story graph"),
    "choice.captions": ("نوشتن کپشن پست‌ها", "Writing the post captions"),
    "choice.render": ("ساخت تصویر پست‌ها", "Rendering the post pictures"),
    "choice.package": ("ساخت بستهٔ انتشار داستان انتخابی", "Building the choice-story package"),
})


def _story(ctx) -> ChoiceStory:
    return ChoiceStory.objects.select_related("page", "series").get(pk=ctx.payload["story_id"])


def _page(payload: dict):
    s = ChoiceStory.objects.filter(pk=payload.get("story_id")).select_related("page").first()
    return s.page if s else None


def _resource(task: str):
    return lambda payload: llm.resource_for(_page(payload), task)


def _render_resource(payload: dict) -> str:
    s = ChoiceStory.objects.filter(pk=payload.get("story_id")).first()
    if s is None or s.renderer == "stick":
        return "cpu"
    from instai.core import settings_store

    return "cpu" if str(settings_store.effective("image_engine")) == "placeholder" else "gpu"


def _meta(story: ChoiceStory, **extra) -> dict:
    return {"language": story.language, "format": story.page.format, "title": story.title, "premise": story.premise, "genre": story.genre,
            "post_count": (story.settings or {}).get("post_count", 14),
            "characters": [{"name": c.name, "role": c.role, "appearance": c.appearance} for c in story.page.characters.all()][:6],
            "tone": story.page.profile("identity").get("tone", ""), **extra}


def _graph_from(posts: list[dict]) -> dict:
    nodes = [G.new_node(str(p["id"]), choices=p.get("choices") or [], kind=p.get("kind") or "story", ending=p.get("ending") or "") for p in posts]
    return G.renumber(G.normalize({"nodes": nodes}))[0]


def _fallback(story: ChoiceStory, meta: dict, why: dict) -> tuple[dict, dict, bool]:
    """No usable model answer: the hand-written story of this genre when there is one (Persian), else the deterministic skeleton."""
    tpl = story_templates.for_genre(story.genre) if story.language == "fa" else None
    if tpl is not None:
        from instai.identity import cast

        cast.ensure_cast(story.page, tpl["cast"])
        return story_templates.plan_of(tpl), {"provider": "template", "template": tpl["key"], **why}, True
    return G.skeleton_plan(meta["post_count"], fa=story.language == "fa", title=story.title), {"provider": "skeleton", **why}, True


@handler("choice.plan", resource=_resource("choice_plan"), timeout=1800)
def plan(ctx):
    story = _story(ctx)
    ctx.progress(0.2, "planning")
    meta = _meta(story, instruction=ctx.payload.get("instruction", ""))
    fallback = False
    try:
        res = roles.choice_planner(meta, provider=llm.resolve(story.page, "choice_plan"))
        data, info = res.data, {"provider": res.provider, "model": res.model}
    except AgentError as e:        # a weak model never stalls the story: a ready-made story of the genre (else the skeleton) is used and flagged
        data, info, fallback = _fallback(story, meta, {"errors": e.errors[:3]})
    if not G.validate(_graph_from(data["posts"]))["ok"]:   # a plan with errors is replaced too; the owner can still edit everything
        data, info, fallback = _fallback(story, meta, {"note": "the model's graph was invalid"})
    services.apply_plan(story, data, author="system" if fallback else "ai")
    story.refresh_from_db()
    return {"posts": len(G.nodes_of(story.graph)), "fallback": fallback, **info}


@handler("choice.captions", resource=_resource("choice_posts"), timeout=1800)
def captions(ctx):
    story = _story(ctx)
    posts = [{"id": n["id"], "title": n["title"], "text": n["text"], "kind": n["kind"], "ending": n["ending"], "choices": n["choices"]} for n in G.nodes_of(story.graph)]
    ctx.progress(0.2, "captions")
    try:
        res = roles.choice_caption_writer(_meta(story, posts=posts), provider=llm.resolve(story.page, "choice_posts"))
        services.apply_captions(story, res.data)
        return {"captions": len(res.data["posts"]), "provider": res.provider}
    except AgentError as e:
        services.reset_captions(story)
        return {"captions": len(posts), "fallback": True, "errors": e.errors[:3]}


@handler("choice.render", resource=_render_resource, timeout=6 * 3600)
def render_posts(ctx):
    story = _story(ctx)
    only = set(ctx.payload.get("nodes") or [])
    stale = set(render.stale_nodes(story))
    todo = [n for n in G.nodes_of(story.graph) if (n["id"] in only if only else n["id"] in stale)]
    g = story.graph
    for k, n in enumerate(todo):
        ctx.check()
        ctx.progress(k / max(1, len(todo)), f"post {k + 1}/{len(todo)}")
        info = render.register_post(story, n, ctx)
        for m in g["nodes"]:
            if m["id"] == n["id"]:
                m["asset_id"], m["image_hash"] = info["asset_id"], info["hash"]
        ChoiceStory.objects.filter(pk=story.pk).update(graph=g)
    return {"rendered": len(todo), "total": len(G.nodes_of(g))}


@handler("choice.package", resource="cpu", timeout=3600)
def package(ctx):
    from instai.assets.models import Asset
    from instai.providers.base import ProviderError

    story = _story(ctx)
    if story.status != "approved":
        raise ProviderError("داستان باید پیش از ساخت بسته تأیید شود.", retryable=False, code="not_ready")
    work = Path(tempfile.mkdtemp(prefix="cpkg-", dir=settings.MEDIA_ROOT))
    imgs: dict[str, Path] = {}
    for n in G.nodes_of(story.graph):
        a = Asset.objects.filter(pk=n.get("asset_id")).first() if n.get("asset_id") else None
        if a is not None and asset_storage.storage.exists(a.path) and n.get("image_hash") == render.node_hash(story, n, story.graph):
            imgs[n["id"]] = asset_storage.storage.path_for(a.path)
        else:
            p = work / f"{n['id']}.png"
            render.render_post(story, n, p, Path(settings.MEDIA_ROOT) / "stickwork" / f"choice{story.pk}", ctx=ctx)
            imgs[n["id"]] = p
    out = work / "package.zip"
    export.build(story, imgs, out, work)
    a = asset_storage.register(out, f"exports/choice/{story.pk}/story-{story.pk}-v{story.version}.zip", kind="package", role="export", page=story.page,
                               provenance={"purpose": "choice_package", "story": story.pk, "version": story.version, "posts": len(imgs)}, probe=False)
    shutil.rmtree(work, ignore_errors=True)
    return {"asset_id": a.pk, "url": a.url, "posts": len(imgs)}
