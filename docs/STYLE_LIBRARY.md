# The art and animation style library (0.7.0)

The owner's words: *what we took to be the library is a colour theme - keep it, call it «تمِ رنگی» (Color theme); the real MAIN library is the
art/animation styles.* So the library has three tabs: **art and animation styles** (main), **color themes**, **templates**.

## What is in it

* `instai/styles/builtin_styles.py` (the first 44 looks) + `styles_more.py` (72 more) = **116 styles**, in eight browse groups:
  cinematic and realistic, anime and cartoon, drawn and painted, 3D and CGI, handmade and stop-motion, graphic design movements, motion and
  typography, retro and digital. Every one of the owner's named looks is there (pixel art, chalkboard, glow sketch, early-console 3D, comic art,
  flat vector, minimal black-and-white essay, CGI motion, toy bricks, fast 3D explainer, anime, painted pastoral anime, fairytale feature 2D,
  bold angular TV toon, watercolour, cel shading, line art, silhouette, claymation, stop-motion, low poly, voxel, papercraft, origami, isometric,
  photoreal CGI, 2.5D parallax, synthwave, film noir, cyberpunk, steampunk, pop art, stained glass, graffiti, blueprint, glitch, whiteboard,
  kinetic typography, infographic, corporate flat, stickman, flat 2D, 3D clay, glassmorphism, chrome metal type, cineview, risograph, paper
  collage, particles, neo-brutalism, Bauhaus, Memphis, vaporwave) plus researched extras (art deco, art nouveau, ink wash, impressionist oil,
  gouache, charcoal, pencil, linocut, mosaic, embroidery, VHS, 8mm home movie, tilt-shift, double exposure, duotone, holographic foil, Y2K, groovy
  70s, constructivist poster, travel poster, die-cut sticker, terminal/ASCII, wireframe HUD, cozy lo-fi pixel, surreal, dark fantasy, calligraphic
  ink, vinyl toy figure ...).
* `builtin_themes.py`: **24 colour themes** (16 old + 8 new: paper and ink, neon arcade, vapor pastel, risograph duotone, terracotta, steel and
  chrome, Bauhaus primaries, blueprint blue). The API and the stored data keep the key `theme` / `theme_key` (nothing migrates); only the words in
  the UI changed.
* Fields of a style (`schema.py`): id, fa/en name, fa/en description, `image_positive`, `image_negative`, `video_positive`, `video_negative`,
  palette (6 roles), lighting, mood, `realism`, `family`, `animation`, `fps_feel`, `techniques`, `sample_prompt`, default colour theme, tags, and the
  v2 fields **`group`**, **`suitability`** (`image` / `video` / `character`), **`gen`** (base model, alternative model, LoRA hints, sampler,
  scheduler, CFG, guidance, steps, default aspect) and **`motif`** (the pattern of the built-in preview picture). Old user styles and the old
  export bundle (`instai.styles@1`) load unchanged (the new fields default).
* Preview pictures: `preview_svg.py` draws a small SVG from the palette and the motif (no image model, no download, no licence question):
  `/api/library/style/<key>/preview.svg`. **Real samples**: job `styles.preview` renders each style's `sample_prompt` with the owner's own image
  model through `gpu.compute.run_task` (so a worker PC can take it; waits when ComfyUI is down; resumable; each picture is saved at once and
  linked by `StylePreview`; a changed prompt makes the sample "out of date"). The button is in the library; `GET /api/library/previews` says how many
  exist and how long the rest takes.

## Licence rule and search names

No studio, franchise, brand, artist or creator name may appear in a style's name, description, tags or any prompt (`tests/test_style_library.py`
scans for a long list; `tests/test_styles.py` too). The looks are *inspired* generic descriptions ("hand-drawn pastoral anime", "interlocking plastic
toy bricks"), so the output cannot be mistaken for a rights-holder's work. People still search by the names they know, so `aliases.py` holds
**search-only** terms ("ghibli", "lego", "ps2", "dan koe", "zackd", "پیکسار" ...). They are never shown as labels and never sent to a model (a test
checks the composed prompts). `library.matches()` folds Arabic/Persian letter variants, ZWNJ and digit alphabets, and ignores the word "style".

## Where the chosen look goes (one pick per project)

`library.look_of(page, series)`: the **series' own pick** (`Series.look`, made once for the project) wins over the page's visual profile; a series that
picks only a style gets *that style's* default colour theme. The page's free-text style notes always apply. Then `compose_for_*` builds the text.

| Path | Code | What it takes from the look |
|---|---|---|
| Keyframe images | `production/pipeline.py` `style_prompt/style_negative/style_steps`, `keyframe_hash` | positive + negative prompt, recommended steps (final mode) |
| Video clips (Wan) | `pipeline.step_clips`, `hero.generate_chain(negative_extra=)`, `clip_hash` | motion fragment (`video_positive`) and motion negatives |
| Character design sheets | `studio/jobs.py` `design_job`, `design_image_job` | look of that episode's series (page look for page-level sheets), steps |
| Storyboard / development-room LLM | `jobs/handlers/story.py _style`, `studio/jobs.py look_summary` | the same composed text |
| Puppet rigs, anime comparisons, LoRA tests | unchanged | rigs are cut from an already-styled sheet; comparisons use their own fixed prompts |

Because the look is part of `keyframe_hash` and `clip_hash`, changing a project's style makes its keyframes and clips *out of date* and they are made
again at the next production run (finished older episodes that never had a style fragment in their hash will also count as out of date once).

## Hints are advice

`gen.steps` is applied (clamped); model, sampler, scheduler, CFG, LoRA text and aspect are shown in the details panel and for the owner's own
choice. Nothing downloads a LoRA or switches the global image workflow by itself (a LoRA's licence must be read first, see `docs/MODELS.md`).

## Sources and licences

All texts, palettes and prompts were written for this project (no copied datasets). The preview pictures are drawn by code. Style families are
named after art-historical movements and generic techniques (Bauhaus, Memphis, art deco, impressionism, risograph, linocut ...), which are not
anyone's property. Nothing here ships a model file. Display names of the Persian UI are our own wording.

## Adding a style

Add a `mk(...)` row to `styles_more.py` (key, group, realism, family, animation, fps, fa/en name and description, positive prompt, motion prompt,
6 colours, light, mood, techniques, sample prompt, a colour theme from `builtin_themes.py`, tags, suitability letters, motif from
`preview_svg.MOTIFS`, `gen(...)` hints), add its search names to `aliases.py`, run `pytest tests/test_style_library.py tests/test_styles.py`.
