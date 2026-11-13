"""Shared helpers of the built-in idea bank: categories and the maker used by the `seeds_*.py` files.

Every idea has a Persian and an English title, logline (what it is, in one sentence) and hook (the opening line or question that stops the scroll).
Explainer ideas name well-known, documented concepts and never invent figures, studies or quotes; stories use made-up people only.
"""
from __future__ import annotations

CATEGORIES = {
    "psychology": {"fa": "روان‌شناسی", "en": "Psychology", "order": 1,
                   "styles": ["minimal_bw_essay", "whiteboard_explainer", "flat_vector_motion"]},
    "personal_development": {"fa": "توسعهٔ فردی", "en": "Personal development", "order": 2,
                             "styles": ["minimal_bw_essay", "gouache_storybook", "line_art_mono"]},
    "economy": {"fa": "اقتصاد", "en": "Economy", "order": 3,
                "styles": ["infographic_data", "flat_vector_motion", "stickman_doodle"]},
    "success": {"fa": "موفقیت", "en": "Success", "order": 4,
                "styles": ["cinematic_realistic", "kinetic_typography", "silhouette_cutout"]},
    "business": {"fa": "کسب‌وکار", "en": "Business", "order": 5,
                 "styles": ["corporate_flat_people", "flat_vector_motion", "fast_3d_explainer"]},
    "mystery": {"fa": "سناریوهای رازآلود", "en": "Mystery scenarios", "order": 6,
                "styles": ["noir_bw", "cinematic_realistic", "dark_fantasy_painting"]},
}
FORMAT_OF = {"explainer": "concept_explainer", "story": "custom", "character": "recurring_character"}


def idea(key, kind, tags, title, logline, hook, *, premise=None, styles=None, episodes=None, category=None):
    """One built-in idea. `title` / `logline` / `hook` / `premise` are (persian, english) pairs; kind is explainer | story | character."""
    return key, {
        "category": category, "format": FORMAT_OF[kind], "tags": list(tags), "title_fa": title[0], "title_en": title[1],
        "logline_fa": logline[0], "logline_en": logline[1], "hook_fa": hook[0], "hook_en": hook[1],
        "premise_fa": (premise or ("", ""))[0], "premise_en": (premise or ("", ""))[1],
        "suggested_styles": list(styles or []), "episodes": episodes or (5 if kind == "explainer" else 6),
    }


def bundle(category: str, rows: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """Stamp the category on every idea and prefix its key, so keys are unique across the bank."""
    out = []
    for k, d in rows:
        d = {**d, "category": category}
        if not d["suggested_styles"]:
            d["suggested_styles"] = CATEGORIES[category]["styles"]
        out.append((f"{category[:4]}_{k}", d))
    return out
