from __future__ import annotations

from instai.jobs.registry import handler


@handler("publish.export", resource="cpu", timeout=1800)
def export(ctx):
    from instai.publishing import services

    return services.export_package(ctx.payload["publication_id"])


@handler("publish.send", resource="net", timeout=1800)
def send(ctx):
    """The owner pressed "publish": through the adapter of the publication's target (manual package by default, the official API only when every
    requirement is met). Never retried blindly: a post that half-succeeded must not be sent twice."""
    from instai.publishing import adapters
    from instai.publishing.models import Publication
    from instai.publishing.notifications import notify
    from instai.story import services as story_services
    from instai.story import states

    pub = Publication.objects.select_related("episode__series__page", "target").get(pk=ctx.payload["publication_id"])
    ad = adapters.adapter_for(pub.target)
    ctx.progress(0.2, ad.label)
    res = ad.publish(pub)
    if ad.name == "manual":
        return res
    Publication.objects.filter(pk=pub.pk).update(status="published", external_url=str(res.get("external_id") or ""))
    ep = pub.episode
    ep.refresh_from_db()
    if ep.state == states.APPROVED:
        story_services.transition(ep, states.SCHEDULED, actor="user")
        ep.refresh_from_db()
    if ep.state == states.SCHEDULED:
        story_services.transition(ep, states.PUBLISHED, actor="user", reason="published through the official API on the owner's request")
    notify("publish", f"قسمت {ep.number} منتشر شد", level="ok", link=f"/episodes/{ep.pk}", page=ep.series.page, episode=ep, key=f"pub:{pub.pk}", once=True)
    return res
