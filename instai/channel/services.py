"""Channel mode services: settings, cast, the season slate (plan -> review -> approve -> write into the series' episodes), schedule, and the channel context the
script writer receives. The only place where a season plan is written to the database."""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from instai.core.errors import DomainError
from instai.story import services as story_services
from instai.story.models import Series

from . import conventions, planner, season_templates
from .models import Channel


def _bad(code: str, fa: str, en: str, status: int = 409, **details) -> DomainError:
    return DomainError(code, fa, http_status=status, message_en=en, details=details or None)


def get_channel(series: Series) -> Channel:
    ch = Channel.objects.filter(series=series).first()
    if ch is not None:
        return ch
    g = conventions.genre(conventions.DEFAULT_GENRE)
    cast = []
    for i, c in enumerate(series.page.characters.all()[:4]):
        cast.append({"character": c.pk, "name": c.name, "role": conventions.CAST_ROLES[min(i, len(conventions.CAST_ROLES) - 1)] if i else "protagonist", "marker": "", "catchphrase": ""})
    start = (timezone.now() + dt.timedelta(days=3)).date().isoformat()
    pub = series.page.profile("publishing")
    return Channel.objects.create(series=series, genre=conventions.DEFAULT_GENRE, runtime_sec=g["runtime"]["default"], episodes_per_season=max(2, min(30, series.target_episodes or 8)),
                                  cadence={"days": pub.get("days") or ["sat", "mon", "wed"], "time": pub.get("time") or "20:00", "utc_offset": 210, "start": start}, cast=cast,
                                  rules={"max_open_threads": 4, "max_thread_span": 4, "recap_sec": g["recap_sec"], "hook_sec": g["hook_sec"], "cliffhanger_sec": g["cliffhanger_sec"]})


def update(ch: Channel, data: dict) -> Channel:
    if data.get("genre") in conventions.GENRES:
        ch.genre = data["genre"]
    g = conventions.genre(ch.genre)
    if "runtime_sec" in data:
        ch.runtime_sec = max(g["runtime"]["min"] // 2, min(g["runtime"]["max"] * 2, int(data["runtime_sec"] or g["runtime"]["default"])))
    if "episodes_per_season" in data:
        ch.episodes_per_season = max(2, min(60, int(data["episodes_per_season"] or 8)))
    if "season" in data:
        ch.season = max(1, min(50, int(data["season"] or 1)))
    if isinstance(data.get("cadence"), dict):
        c = {**ch.cadence, **{k: v for k, v in data["cadence"].items() if k in ("days", "time", "utc_offset", "start")}}
        c["days"] = [d for d in (c.get("days") or []) if d in planner.DAYS] or ["sat", "mon", "wed"]
        try:
            dt.date.fromisoformat(str(c.get("start")))
        except ValueError:
            raise _bad("validation_error", "تاریخ شروع نامعتبر است.", "The start date is invalid.", 400, start=["invalid"])
        ch.cadence = c
    if isinstance(data.get("cast"), list):
        known = {c.pk: c.name for c in ch.series.page.characters.all()}
        ch.cast = [{"character": r.get("character"), "name": known.get(r.get("character")) or str(r.get("name") or "")[:80], "role": r.get("role") if r.get("role") in conventions.CAST_ROLES else "ally",
                    "marker": str(r.get("marker") or "")[:80], "catchphrase": str(r.get("catchphrase") or "")[:120]} for r in data["cast"] if isinstance(r, dict)][:8]
    if isinstance(data.get("rules"), dict):
        ch.rules = {**ch.rules, **{k: int(v) for k, v in data["rules"].items() if k in ("max_open_threads", "max_thread_span", "recap_sec", "hook_sec", "cliffhanger_sec") and str(v).lstrip("-").isdigit()}}
    if isinstance(data.get("slate"), list):
        set_slate(ch, data["slate"])
    for f, n in (("season_title", 200), ("season_arc", 4000)):
        if f in data:
            setattr(ch, f, str(data[f] or "")[:n])
    ch.save()
    return ch


def set_slate(ch: Channel, rows: list[dict]) -> None:
    clean = []
    for i, r in enumerate(rows[:60], 1):
        if not isinstance(r, dict):
            continue
        clean.append({"number": i, "title": str(r.get("title") or "")[:200], "hook": str(r.get("hook") or "")[:400], "logline": str(r.get("logline") or "")[:600],
                      "escalation": str(r.get("escalation") or "")[:600], "twist": str(r.get("twist") or "")[:600], "cliffhanger": str(r.get("cliffhanger") or "")[:400],
                      "payoff_of_previous": str(r.get("payoff_of_previous") or "")[:400], "characters": [str(c)[:80] for c in (r.get("characters") or [])][:6],
                      "location": str(r.get("location") or "")[:60], "runtime_sec": int(r.get("runtime_sec") or ch.runtime_sec),
                      "opens": [str(t)[:30] for t in (r.get("opens") or [])][:4], "closes": [str(t)[:30] for t in (r.get("closes") or [])][:4], "episode_id": r.get("episode_id")})
    ch.slate = clean
    if ch.status == "approved":
        ch.status = "planned"
    elif clean and ch.status == "draft":
        ch.status = "planned"


def apply_season_plan(ch: Channel, plan: dict) -> Channel:
    for r in plan.get("episodes") or []:      # keep the links to episodes that already exist
        old = next((o for o in ch.slate if o.get("number") == r.get("number")), None)
        if old and old.get("episode_id"):
            r["episode_id"] = old["episode_id"]
    set_slate(ch, list(plan.get("episodes") or []))
    ch.season_title = str(plan.get("season_title") or ch.season_title)[:200]
    ch.season_arc = str(plan.get("season_arc") or ch.season_arc)
    ch.applied = False
    ch.save()
    return ch


# ------------------------------------------------------------------ ready-made seasons

def apply_template(ch: Channel, key: str) -> Channel:
    """Fill the channel from a ready-made season: genre, runtime, the recurring cast (characters created on the page, stick identity drawn and locked), the season slate."""
    from instai.identity import cast

    tpl = season_templates.get(key)
    if tpl is None:
        raise _bad("not_found", "این فصل آماده پیدا نشد.", "That ready-made season does not exist.", 404)
    chars = cast.ensure_cast(ch.series.page, [{**row, "role": conventions.CAST_ROLES_FA.get(row["role"], row["role"])} for row in tpl["cast"]])      # the Characters tab shows the role in Persian
    ch.genre = tpl["genre"]
    ch.runtime_sec = tpl["runtime_sec"]
    ch.episodes_per_season = len(tpl["episodes"])
    ch.cast = [{"character": c.pk, "name": c.name, "role": row["role"] if row["role"] in conventions.CAST_ROLES else "ally", "marker": row["marker"], "catchphrase": row["catchphrase"]}
               for c, row in zip(chars, tpl["cast"])]
    ch.save()
    return apply_season_plan(ch, season_templates.plan_of(tpl))


def report(ch: Channel) -> dict:
    g = conventions.genre(ch.genre)
    cast_names = [c["name"] for c in ch.cast if c.get("name")]
    v = planner.validate(ch.slate, rules=ch.rules, cast_names=cast_names, runtime=ch.runtime_sec, genre_runtime=(g["runtime"]["min"], g["runtime"]["max"]))
    c = ch.cadence or {}
    sched = planner.schedule(str(c.get("start") or timezone.now().date().isoformat()), c.get("days") or [], str(c.get("time") or "20:00"), max(len(ch.slate), 1),
                             utc_offset_minutes=int(c.get("utc_offset") or 210))
    return {"validation": v, "schedule": sched, "beats": conventions.beat_plan(ch.genre, ch.runtime_sec), "genre": {k: v_ for k, v_ in g.items() if k != "beats"},
            "per_week": len(c.get("days") or []), "status": ch.status, "applied": ch.applied}


def approve(ch: Channel) -> Channel:
    rep = report(ch)
    if not rep["validation"]["ok"]:
        raise _bad("not_ready", "برنامهٔ فصل هنوز اشکال دارد؛ اول خطاها را رفع کنید.", "The season plan still has errors; fix them first.", errors=[e["code"] for e in rep["validation"]["errors"]][:20])
    ch.status = "approved"
    ch.save(update_fields=["status", "updated_at"])
    return ch


def revoke(ch: Channel) -> Channel:
    ch.status = "planned" if ch.slate else "draft"
    ch.save(update_fields=["status", "updated_at"])
    return ch


def beats_for_row(ch: Channel, row: dict) -> list[dict]:
    """The beat sheet of one episode from the genre template and the slate row (hook, escalation, twist, cliffhanger), so the ladder starts from the plan."""
    texts = {"hook": row.get("hook", ""), "setup": row.get("logline", ""), "escalation": row.get("escalation", ""), "twist": row.get("twist", ""),
             "crisis": row.get("escalation", ""), "cliffhanger": row.get("cliffhanger", "")}
    runtime = int(row.get("runtime_sec") or ch.runtime_sec)
    out = []
    for b in conventions.beat_plan(ch.genre, runtime):
        out.append({"name": b["name"], "summary": texts.get(b["name"], ""), "seconds": b["seconds"], "purpose": {"hook": "curiosity", "cliffhanger": "to be continued"}.get(b["name"], "")})
    if row.get("payoff_of_previous") and out:
        out[0]["summary"] = (row["payoff_of_previous"] + " " + out[0]["summary"]).strip()
    return out


@transaction.atomic
def write_episodes(ch: Channel) -> Channel:
    """Write the approved slate into the series' episodes (new ones are created, existing ones keep their work) and start each episode's beat sheet from the plan."""
    if ch.status != "approved":
        raise _bad("not_ready", "ابتدا برنامهٔ فصل را تأیید کنید.", "Approve the season plan first.")
    series = ch.series
    eps = ch.slate
    arcs, per = [], 4
    for k in range(0, len(eps), per):
        chunk = eps[k:k + per]
        arcs.append({"title": (f"بخش {len(arcs) + 1}" if series.page.language == "fa" else f"Part {len(arcs) + 1}"), "summary": chunk[0].get("logline", ""), "goal": chunk[-1].get("twist", ""),
                     "cliffhanger": chunk[-1].get("cliffhanger", "")})
    plan = {"arcs": arcs, "episodes": [{"number": e["number"], "title": e["title"] or f"Episode {e['number']}", "logline": e.get("logline", ""), "goal": (e.get("escalation", "") + " " + e.get("twist", "")).strip(),
                                        "cliffhanger": e.get("cliffhanger", ""), "arc": (e["number"] - 1) // per + 1, "duration_sec": int(e.get("runtime_sec") or ch.runtime_sec)} for e in eps]}
    if ch.season_title and not series.title:
        plan["title"] = ch.season_title
    story_services.apply_plan(series, plan, overwrite_header=False)
    from instai.studio import ladder

    for e in series.episodes.all():
        row = next((r for r in ch.slate if r["number"] == e.number), None)
        if row is None:
            continue
        row["episode_id"] = e.pk
        e.notes = "\n".join(f"{k}: {row.get(k, '')}" for k in ("hook", "escalation", "twist", "cliffhanger", "payoff_of_previous") if row.get(k))[:2000]
        e.save(update_fields=["notes", "updated_at"])
        if not ladder.has_versions(series, e, "beat_sheet"):
            ladder.save_version(series, e, "beat_sheet", {"beats": beats_for_row(ch, row)}, author="system", note="from the season slate")
    ch.applied = True
    ch.save()
    return ch


def script_context(series: Series, episode_number: int | None = None) -> dict | None:
    """What the scriptwriter must know about the channel format (None when the series is not a channel)."""
    ch = Channel.objects.filter(series=series).first()
    if ch is None:
        return None
    g = conventions.genre(ch.genre)
    rules = ch.rules or {}
    row = next((r for r in ch.slate if r.get("number") == episode_number), None) if episode_number else None
    return {"genre": ch.genre, "runtime_sec": ch.runtime_sec, "hook_within_sec": rules.get("hook_sec", g["hook_sec"]), "recap_sec": rules.get("recap_sec", g["recap_sec"]),
            "cliffhanger_last_sec": rules.get("cliffhanger_sec", g["cliffhanger_sec"]), "beats": conventions.beat_plan(ch.genre, ch.runtime_sec),
            "cast": [{"name": c["name"], "role": c["role"], "marker": c.get("marker", ""), "catchphrase": c.get("catchphrase", "")} for c in ch.cast],
            "conventions": [c["en"] for c in conventions.CONVENTIONS][:8], "episode_plan": {k: row.get(k) for k in ("hook", "escalation", "twist", "cliffhanger", "payoff_of_previous")} if row else None}


def channel_dict(ch: Channel) -> dict:
    return {"id": ch.pk, "series": ch.series_id, "genre": ch.genre, "runtime_sec": ch.runtime_sec, "episodes_per_season": ch.episodes_per_season, "season": ch.season, "cadence": ch.cadence,
            "cast": ch.cast, "rules": ch.rules, "slate": ch.slate, "season_title": ch.season_title, "season_arc": ch.season_arc, "status": ch.status, "applied": ch.applied, "updated_at": ch.updated_at}
