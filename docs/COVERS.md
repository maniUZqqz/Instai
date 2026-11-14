# Cover maker (0.15.0)

Covers for episodes, series, seasons and the channel: YouTube, Aparat, Telegram, Instagram (4:5 and square), Reels / Shorts, a channel banner, a series poster and a season card.
Persian first (the owner reads Persian only), English mirrored (`page.language` decides). Screen: **/covers** (sidebar «کاورساز») and the **Cover** tab of Publishing (a publication has a
thumbnail + «Make or change the cover»). Code: `instai/covers/` (app `covers`), UI: `frontend/src/covers/`, texts: `frontend/src/i18n/packs/covers.ts`.

**Where it comes from.** The engine is the NMarketing thumbnail maker (`backend/apps/thumbs` @ v3.02, c23f861) ported with its tests; every ported module has a
`SOURCE: ported from NMarketing:backend/apps/thumbs/<file> @ v3.02 (c23f861), adapted for series/episode covers` note. **There is no runtime import of NMarketing**
(`tests/test_covers_engine.py` + the grep in `docs/selftests/covers.md`). NMarketing's matting jobs and photo library are NOT used (see "Character picture").

## What was ported and what was customised

| Part | Ported as | InstAI customisation |
|---|---|---|
| `render.py` (spec -> layered picture, avoid zones, auto logo, scrim) | `engine/render.py` | fields: series, episode number + title, hook line, characters, channel + logo (no price / product / store); warnings are `{code, fa, en}`; layer names in English; Persian mirrored for English (`Ctx.start`, `Ctx.word`); `channel tag` placed in a free corner like the logo |
| `primitives.py`, `shapes.py` | `engine/primitives.py`, `engine/shapes.py` | unchanged logic; docstrings in English; numpy is now a requirement (`numpy>=1.26,<2.3`) |
| `typo.py` (Persian text, outline / glow / extrusion) | `engine/typo.py` | shaping goes through `instai.render.fa_text` (libraqm when it works, the built-in shaper otherwise); fonts from `instai/covers/fonts` |
| `palette.py` | `engine/palette.py` | brand colours from the series look (`from_theme`: the 6 roles of a colour theme); the contrast guard stays |
| `formats.py` | `engine/formats.py` | titles / notes in fa + en; **pinterest dropped; `yt_banner` and `season_card` added** |
| `styles.py` (15 layouts) | `engine/styles.py` | 13 kept (`face_text` -> `character_face`, `question_hook` = the cliffhanger question, `cinema_poster` = the series poster, `split_ba` = what-if before / after ...); **`product_hero` and `pinterest_collage` dropped**; the price burst is an episode badge |
| (new) | `engine/styles_instai.py` | `episode_card`, `cliffhanger`, `choice_split` written with the same `StyleDef` API so they can be copied back to NMarketing |
| `archetypes.py` (mood board) | `engine/archetypes.py` | notes for all 16 layouts in fa + en |
| `phrases.py`, `hooks.py`, `ideation.py` | `engine/phrases.py`, `engine/hooks.py`, `ideation.py` | the Persian phrase tools are unchanged; the formulas are episode formulas (cliffhanger, what-if, episode N, question, versus, choice, quote ...) in fa + en; the AI goes through `instai.agents.llm` (task `cover_ideas`, group "brainstorm") with NM's claim guard (risky words, no invented numbers) |
| `aibg.py` | `background.py` | `compute.run_task` + `compute.require_workflow` (a missing ComfyUI is a WAIT), the series look's image prompt; the model never draws text |
| `fixtures.py`, tests | `engine/fixtures.py`, `tests/test_covers_*.py` | a synthetic Chagher-style series (no price, no statistic); matrix style x format x language |

## Formats (all numbers approximate; the UI says so)

| Key | Size | Notes |
|---|---|---|
| `youtube` | 1280x720 | JPEG under 2 MB; the video length covers the bottom right |
| `aparat` | 1280x720 | bottom-left duration |
| `telegram` | 1280x720 | top-left duration |
| `ig_portrait` | 1080x1350 (4:5) | the profile grid crops the sides a little |
| `ig_square` | 1080x1080 | |
| `story` (Reels / Shorts cover) | 1080x1920 | avoid zones: top 13 % and bottom 18 % |
| `poster` (series poster) | 1200x1800 (2:3) | |
| `yt_banner` | 2560x1440 | only the centre of about 1546x423 shows everywhere (labelled approximate) |
| `season_card` | 1920x1080 | |

## Layouts (16)

Ported (13): `character_face`, `split_ba` (what-if), `number_list` (episode number), `question_hook`, `minimal_luxury`, `cinema_poster` (series poster), `sticker_outline`, `neon`, `news_bold`, `versus`,
`magazine_cover`, `retro_poster`, `quote_card`. Written for the studio (3): `episode_card` (series name + a big episode-number badge + the hook line), `cliffhanger` (a dark scene, a spot-lit character,
a headline whose last line fades), `choice_split` (an A / B poster for `instai.choice` stories). Fields (all optional except the title): `title`, `subtitle`, `kicker`, `number`, `badge`, `tagline`, `credits`,
`channel`, `label_a`, `label_b`; the layouts say which they use (`/api/covers/meta`).

## Persian text

`typo._shape` / `typo._kw` use libraqm only when it really works (`fa_text.RAQM_OK`); otherwise `fa_text.shape` (contextual forms + a simplified bidi order, Pillow's basic layout) is used, and zero-width joiners
are dropped after shaping so a font without a glyph for them never draws a box. `tests/test_covers_text.py` compares both paths (width within 8 %, ink within 12 %) and checks that every bundled font can be drawn by
the built-in shaper. `typo.basic_layout()` forces the built-in path. Fonts: `instai/covers/fonts` (Lalezar with an extended cmap, Sahel) + Vazirmatn of `instai/render/fonts`; see `fonts/README.md` and `docs/MODELS.md`.

## The character picture (`subjects.py`)

1. a locked **stick character** is drawn by code (`instai.render.stick`, transparent, the same in every episode);
2. an approved reference picture, or a locked keyframe of an episode shot the character is in;
3. the design sheet (used as a photo: it holds several views);
4. nothing: the layout keeps its own replacement shape (an abstract scene, or the logo).

A picture without a transparent background goes through `instai.render.puppet.cutout.cut_part` (BiRefNet-lite when installed, otherwise the flood fill); when that finds no outline it is used as a photo.
The owner can also upload a picture of their own (`POST /api/covers/upload`, kinds `logo`, `subject`, `background`).

## The AI background and the wait

`background.generate` asks the page's image engine (default `flux_dev_fp8_t2i`) for a ~1 MP picture of the scene (prompt = the layout's scene line + the series look's `image_positive` + "no text, no letters,
no people"; the negative is the look's negative + text words). `compute.require_workflow` raises `ProviderError(wait="comfy_down")` when no PC can run it: the job goes back to the queue with a Persian reason
and **the cover is already finished with the procedural background** (`status = waiting_bg`, usable, and already the episode's cover). When ComfyUI is up the same job draws the background and re-renders every
version (`bg_state = ai`); the chosen version is re-registered. One background serves all A/B versions (they differ in colours, side and seed). Demo mode (`image_engine = placeholder`) never asks a model
(`bg_state = demo`). Persian text is always drawn by Pillow.

## Data, assets, publishing

* `Cover` (one design: spec, options, status, `variants`, `asset` = the chosen version, `parent` for "edit again"). The history keeps every design; nothing is edited in place.
* A version is an `Asset` (`role="other"`, no episode, so it never replaces the episode's cover); `use_cover` registers the chosen one as `Asset(role="cover", episode=...)` and sets `Publication.cover` of the
  episode's publications that are not published yet. `publishing.export_package` already reads `role="cover"`: the package now has `cover.png` and, for covers of this maker, `cover.jpg` (under the format's size cap).
* Job `covers.make` (`KIND_TEXT` fa + en; `job.kind.covers.make` in `i18n/packs/covers.ts`): resource `cpu`, `gpu` only when an AI background is asked for and the image engine is a real one.

## The A/B versions

`service.variant_plan`: **A** is the design as it is; **B** swaps the main / second colour and puts the character on the other side; **C-F** try other moods, one of each palette branch of `palette.build`
(dark, light, cinematic, neon, luxury, vivid - vivid / warm / cool share one branch, so they would look the same), alternating the colour swap; never the design's own mood. Every version has a
note in both languages that names the change (shown under it in the UI). `tests/test_covers_engine.py::test_ab_versions_differ...` renders all six versions of every layout and requires every pair to differ.

## API (`/api/covers/...`)

`GET meta` · `GET context?episode|series|page&lang&fmt&style` · `POST ideas` · `POST preview` (a data-URL JPEG + the report + the guides) · `GET/POST covers` (history / make: 1-6 versions) ·
`GET/PATCH/DELETE covers/<id>` · `POST covers/<id>/use` · `POST covers/<id>/more` · `GET covers/<id>/download?variant=A&fmt=png|jpg` · `GET covers/<id>/zip` · `POST upload`.
(The query parameter is `fmt`, not `format`: DRF reserves `?format=` for the renderer.)

## Tests and self-test

`tests/test_covers_engine.py` (every layout x every format x fa / en at a small scale: exact size, not blank, title drawn, inside the canvas and the safe area, out of the avoid zones; every format at its exact full
size; the three studio layouts; English mirror; spec; palette), `tests/test_covers_text.py` (the two shapers, the fonts), `tests/test_covers_api.py` (API, job, A/B, package zip, publications, the AI background that waits
and finishes by itself, demo mode, ideas offline + AI + claim guard, upload, downloads, the self-test rows). Self-test rows in `instai/ops/pcselftest.py`: `covers` (CPU) and `covers_bg` (GPU); see `docs/selftests/covers.md`.
