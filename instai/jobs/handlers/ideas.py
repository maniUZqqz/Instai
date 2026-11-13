"""ideas.generate: the model writes new idea-bank ideas for a category (the owner's liked ideas steer it); they are saved as the owner's ideas."""
from __future__ import annotations

from instai.agents import llm
from instai.ideabank import agent, bank
from instai.ideabank.seed_base import CATEGORIES
from instai.jobs.registry import handler


@handler("ideas.generate", resource=lambda payload: llm.resource_for(None, "bank_ideas"), timeout=1800)
def ideas_generate(ctx):
    p = ctx.payload
    category = p.get("category") if p.get("category") in CATEGORIES else "mystery"
    have = [i for i in bank.all_ideas() if i["category"] == category]
    liked = [{"title_fa": i["title_fa"], "title_en": i["title_en"], "logline_en": i["logline_en"]} for i in have if i["favorite"]][:5]
    meta = {"category": category, "count": p.get("count") or 5, "instruction": str(p.get("instruction") or "")[:500], "liked": liked,
            "existing_titles": [t for i in have for t in (i["title_en"], i["title_fa"]) if t][:80]}
    ctx.progress(0.1, "ideas")
    provider = llm.resolve(None, "bank_ideas")
    cm = None
    if provider.resource == "gpu":
        from instai.gpu.arbiter import ARBITER

        cm = ARBITER.hold(ctx, "llm", llm.effective_model(provider))
        cm.__enter__()
    try:
        res = agent.idea_generator(meta, provider=provider)
    finally:
        if cm:
            cm.__exit__(None, None, None)
    for n in res.notes:
        ctx.log(n)
    made = bank.add_generated(res.data["ideas"], category)
    return {"created": [m["key"] for m in made], "requested": len(res.data["ideas"]), "meta": res.meta()}
