# Fonts of the cover maker

Every font here is under the **SIL Open Font License 1.1** (free for commercial use and for embedding in pictures; only the font itself may not be sold on its own).
The licence text sits next to each font. The Vazirmatn of `instai/render/fonts/` (also OFL) is used too.

| key | font | weights | role | licence file | source |
|---|---|---|---|---|---|
| `lalezar` | Lalezar | 400 | big, showy headlines | `Lalezar-OFL.txt` | github.com/google/fonts (ofl/lalezar), copyright 2015 The Lalezar Project Authors |
| `sahel` | Sahel | 300, 400, 600, 700, 800 (Black) | warm, round headlines and text | `Sahel-LICENSE.txt` | github.com/rastikerdar/sahel-font |
| `vazirmatn` | Vazirmatn | 400, 700 | readable text | `../../render/fonts/OFL.txt` | github.com/rastikerdar/vazirmatn |

## Why these three (and not Estedad)

The owner's Windows PC has a Pillow without FriBidi, so Persian is shaped by `instai/render/fa_text.py` (contextual forms from the Arabic Presentation Forms blocks, drawn with Pillow's
basic layout). That only works for a font whose cmap has drawable glyphs for those code points:

* **Sahel** and **Vazirmatn** have them.
* **Lalezar** draws its forms through OpenType rules (GSUB) and its cmap lacks 42 of the presentation code points. `Lalezar-Regular.ttf` here is the upstream font with ONLY its cmap extended
  (nothing is drawn differently; no outline is touched): `scripts/gen_cover_fonts.py` finds the glyph the GSUB rules give each form and maps the missing code points to it. Under libraqm the
  picture is the same as before (libraqm ignores those code points).
* **Estedad** (suggested at first) has EMPTY glyphs at the presentation-form code points: its Persian letters exist only as OpenType rules, so the built-in shaper cannot draw it. It was left out
  rather than shipped in a form that breaks on the owner's PC.

Both files keep their original copyright notices and licence. Lalezar is a *modified* file: the only change is the cmap (documented here and in the script), and it is not sold on its own.
