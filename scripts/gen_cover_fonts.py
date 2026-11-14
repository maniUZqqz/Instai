"""Developer tool (NOT needed to run InstAI): make the display font of the cover maker usable by the built-in Persian shaper.

Why: on the owner's Windows PC Pillow has no libraqm/fribidi, so `instai/render/fa_text.py` shapes Persian itself: it turns every letter into its
contextual form from the Arabic Presentation Forms blocks (U+FB50-FDFF, U+FE70-FEFF) and draws the result with Pillow's BASIC layout. That only
works for a font whose cmap has those code points. Lalezar (SIL OFL 1.1) draws the forms through its GSUB table (init / medi / fina) and its cmap lacks
several of the presentation code points (for example the final / isolated forms of waw, reh, zain), so BASIC layout drew empty boxes.

This script reads the upstream font, finds the glyph that GSUB gives to each form of each letter and adds the MISSING presentation-form code points to the cmap
(nothing is drawn differently, no outline is touched). The result still shapes identically under libraqm (it ignores those code points) and now also under
the built-in shaper. Run it once with `pip install fonttools`:

    python scripts/gen_cover_fonts.py <upstream Lalezar-Regular.ttf> instai/covers/fonts/Lalezar-Regular.ttf

Upstream: https://github.com/google/fonts/tree/main/ofl/lalezar (SIL OFL 1.1, copyright 2015 The Lalezar Project Authors, no Reserved Font Name).
Modified file: the only change is the cmap (documented in instai/covers/fonts/README.md); the licence text is shipped next to it.
"""
from __future__ import annotations

import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from instai.render import fa_text  # noqa: E402  (the table the built-in shaper uses: letter -> isolated, final, initial, medial)

FORMS = {ch: tuple(ord(c) for c in forms) for ch, forms in fa_text._FORMS.items()}
LAM_ALEF = {ch: tuple(ord(c) for c in forms) for ch, forms in fa_text._LAM_ALEF.items()}
ROLE = ("isol", "fina", "init", "medi")


def single_maps(font) -> dict[str, dict[str, str]]:
    """feature tag -> {glyph: substituted glyph} for the single substitutions (the one-glyph-to-one-glyph forms)."""
    gsub = font["GSUB"].table
    out: dict[str, dict[str, str]] = {t: {} for t in ROLE}
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag not in out:
            continue
        for li in fr.Feature.LookupListIndex:
            for st in gsub.LookupList.Lookup[li].SubTable:
                st = getattr(st, "ExtSubTable", st)
                mp = getattr(st, "mapping", None)
                if isinstance(mp, dict):
                    for k, v in mp.items():
                        if isinstance(v, str):
                            out[fr.FeatureTag].setdefault(k, v)
    return out


def main(src: str, dst: str) -> int:
    from fontTools.ttLib import TTFont

    font = TTFont(src)
    cmap = font.getBestCmap()
    maps = single_maps(font)
    glyphs = set(font.getGlyphOrder())
    add: dict[int, str] = {}
    skipped: list[str] = []
    for ch, cps in FORMS.items():
        base = cmap.get(ord(ch))
        if base is None:
            skipped.append(f"{ch}: no base glyph")
            continue
        for role, cp in zip(ROLE, cps):
            if cp in cmap:
                continue
            g = maps[role].get(base) if role != "isol" else (maps["isol"].get(base) or base)
            if g in glyphs:
                add[cp] = g
            else:
                skipped.append(f"{ch} {role}: no single glyph")
    for ch, (iso, fin) in LAM_ALEF.items():
        for cp in (iso, fin):
            if cp not in cmap:
                skipped.append(f"lam-alef {ch}: U+{cp:04X} missing (ligature is not a single substitution)")
    for table in font["cmap"].tables:
        if table.isUnicode() and (table.format in (4, 12)):
            for cp, g in add.items():
                if cp <= 0xFFFF or table.format == 12:
                    table.cmap[cp] = g
    font.save(dst)
    print(f"added {len(add)} code points to the cmap; skipped {len(skipped)}")
    for s in skipped:
        print("  skipped:", s)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
