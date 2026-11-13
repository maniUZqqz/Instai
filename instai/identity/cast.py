"""A ready-made cast: create the characters of a story / season template on a page and draw + lock their stick identity (no GPU, no model).

Used by the choice-story and mini-series templates, so "start from a ready story" gives the owner characters that already look the same in every picture. A character that
already exists on the page (same name) is kept as it is: a locked identity is never touched, a draft one is drawn again from the template's look only when it has none.
"""
from __future__ import annotations

from instai.core.errors import DomainError
from instai.pages.models import Character, ContentPage

from . import service


def ensure_cast(page: ContentPage, rows: list[dict], *, lock: bool = True) -> list[Character]:
    """[{name, role, appearance, spec}] -> the page's characters (created when missing), each with a drawn stick identity (locked when `lock`)."""
    out: list[Character] = []
    for r in rows:
        name = str(r["name"]).strip()
        c = Character.objects.filter(page=page, name=name).first()
        if c is None:
            c = Character.objects.create(page=page, name=name, role=str(r.get("role") or "")[:120], appearance=str(r.get("appearance") or ""), is_original=True)
        lk = service.get_lock(c)
        if lk is None or (lk.status != "locked" and not lk.stick):
            service.build_stick(c, r.get("spec") or {})
            lk = service.get_lock(c)
        if lock and lk is not None and lk.status != "locked":
            try:
                service.lock_identity(c)
            except DomainError:
                pass                                   # the owner can still lock it by hand on the Characters tab
        out.append(c)
    return out
