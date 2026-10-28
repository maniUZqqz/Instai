"""Notifications shown in the UI: something needs the owner's decision, a render finished, a budget ran out, a publication is due.
`key` de-duplicates: the same event is stored once while its notification is unread (and once per key ever when `once=True`)."""
from __future__ import annotations

from .models import Notification


def notify(kind: str, title: str, *, body: str = "", level: str = "info", link: str = "", page=None, episode=None, key: str = "", once: bool = False) -> Notification | None:
    if key:
        qs = Notification.objects.filter(key=key)
        if not once:
            qs = qs.filter(read=False)
        if qs.exists():
            return None
    return Notification.objects.create(kind=kind, level=level, title=title[:200], body=body, link=link[:200], page_id=getattr(page, "pk", page),
                                       episode_id=getattr(episode, "pk", episode), key=key[:160])


def unread_count() -> int:
    return Notification.objects.filter(read=False).count()


def as_dict(n: Notification) -> dict:
    return {"id": n.pk, "kind": n.kind, "level": n.level, "title": n.title, "body": n.body, "link": n.link, "page": n.page_id, "episode": n.episode_id, "read": n.read,
            "created_at": n.created_at}
