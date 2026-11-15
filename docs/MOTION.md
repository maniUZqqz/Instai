# Motion graphics: the scene-plan engine (0.18.0)

**For the owner, in Persian.** نماهایی که تکنیکشان «گرافیک متحرک» است (نمودار، عدد، فهرست، تیتر کلمه‌به‌کلمه، کارت قسمت، کارت پایانی ...) دیگر به تصویر ثابت با حرکت دوربین تبدیل نمی‌شوند: برای هر نما یک «طرح صحنه» از روی گفتار همان نما نوشته می‌شود (با مدل متنی وقتی روشن است، وگرنه با ساختاری که هیچ مدلی نمی‌خواهد)، با قاعده‌ها سنجیده و اصلاح می‌شود، با Remotion کشیده می‌شود و جای کلیپ ویدئویی همان نما می‌نشیند. رنگ، فونت و حرکت از سبکِ سریال می‌آید (یکی از ۱۱۶ سبک). در صفحهٔ «ویدئو با کد» هر ۱۹ قطعهٔ آماده را می‌توانید جدا ببینید و بسازید؛ در برگهٔ استوری‌بورد هر نمای گرافیک متحرک بخش «طرح صحنه» دارد: پیش‌نمایش زنده، درخواست به زبان ساده («تیتر بزرگ‌تر شود»)، برگشت، کنترل روی فریم‌های واقعی و نقد تصویری با مدل بینایی‌ای که در Ollama نصب کرده‌اید (اگر Ollama خاموش باشد کار منتظر می‌ماند و خودش ادامه می‌دهد). عددهای نمودار و آمار تا وقتی منبع تأییدشده ندارند برچسب «نمونهٔ نمایشی» می‌خورند.

This is the InstAI port of the NMarketing motion-studio v2 engine (component library + scene plan + QA + visual critique), adapted for a channel / series producer.

## What it is

```
narration of one shot ──> scene plan (JSON) ──> rule checks + frame geometry ──> Remotion render ──> shot_clip asset ──> assembly
   (the pipeline)        role.write_plan          qa.run_loop (3 rounds)         remotion.render        (no Ken Burns)
                      model  |  fallback.make_plan       + optional critique.run (vision model)
```

* `instai/motion_plan/` (Python): `components.py` (19 components, fa+en), `specs.py` (the plan and its validation), `fallback.py` (the plan from a narration with NO model), `role.py` + `promptkit.py` (the text-model role),
  `patch.py` + `plans.py` (versioned patches, undo / redo), `qa.py` + `qa_browser.py` (rules + real frames), `critique.py` (the vision model), `shots.py` (the pipeline side), `jobs.py` (the job handlers), `api.py`, `selftest.py`.
* `remotion/src/components/` (TSX): the component library (`registry.ts`), `ScenePlan.tsx` (plays a plan), `ctx.tsx` (the style adapter), `defs.ts` (what the page lists), `qa.tsx` (the geometry probe).
* `remotion/render.mjs` gained a `qa` mode (many frames of many compositions with ONE browser, geometry of every text block) and `scale`.

SOURCE: ported from NMarketing `backend/apps/motion` + `motion/remotion/src` (motion v2), every ported file carries a `SOURCE:` line. There is no runtime import of NMarketing.

## The 19 components (of NMarketing's 33)

| group | components (id) |
|---|---|
| basic scenes | `title` (episode card: series, number, title, hook), `quote`, `stat` (big number), `list` (key points), `logo` (series sting) |
| numbers and charts | `counter`, `bar_chart`, `line_chart`, `donut`, `before_after` («what if»), `countdown` (premiere) |
| text and display | `kinetic_title`, `lower_third` (character name), `checklist`, `steps`, `captions` (word by word), `sticker`, `social_cta` (subscribe + «next episode»), `image_hero` (key art) |

Left out on purpose (shop vocabulary): product, price_card, app, comparison_table, testimonial, rating, tags, ticker, feature_cards, icon_grid, progress_ring, progress_bars, cta, compare. A test (`test_the_shop_vocabulary_was_left_out`) keeps them out.
Overlays (can lie over another scene): `lower_third`, `captions`, `sticker`, `social_cta`.

## Style: the adapter (not NMarketing's 66 styles)

`remotion/src/components/adapter.json` is ONE table read by the bundle (`ctx.tsx styleFromKit`) and by Python (`motionlib.py`):
* the 10 InstAI motion personalities (`live_camera ... painted_parallax`, the keys of `schema.ANIMATIONS`) -> enter animation, spring, transition kind and frames;
* the 8 families (`schema.FAMILIES`) -> radius, border, shadow, text effect;
* the six palette roles of the kit -> the eight roles of the components (`paletteFromKit`): `ink` = `readableOn(bg)`, the three accents = `accentOn(bg, ., 4.5)`, `paper` / `bg2` / `muted` are mixes. **A colour is never used without readableOn / accentOn** (`test_colour_rules_match_the_renderers_and_every_palette_role_reads` checks all 116 kits).
* `Look.tsx` (the drawn surface of the style) stays behind everything (`Stage`), so every component is drawn in the art style of the series.

Fonts: only Vazirmatn (SIL OFL, `remotion/public/fonts/OFL.txt`), as before. NMarketing's fonts were not brought.

## Fields and honesty

* Fields of the series: `series`, `number` (episode), `title`, `hook` (cliffhanger line), `next_episode`, character name (`lower_third`). Sizes: landscape / vertical / square (`catalog.ts SIZES`).
* **Numbers are examples unless a verified source is named.** The five number components (`stat`, `counter`, `bar_chart`, `line_chart`, `donut`) carry `source` / `example`; `specs._honesty` forces `example: true` whenever there is no `source` that belongs to the episode's VERIFIED sources (`Source.verified`), and the chip («نمونهٔ نمایشی؛ اعدادِ واقعی نیستند») cannot be switched off in the renderer. The deterministic plan only credits a number to a verified source whose own text contains it (`fallback._source_for`). The model never writes a `source` (it is not even in its JSON schema).
* The on-screen text of the deterministic plan is a piece of the narration: nothing is invented (`test_a_plan_comes_from_the_narration_alone_with_no_model`).

## In the pipeline

* `costs.IMPLEMENTED` now has `motion_graphics`; its estimate is CPU seconds (`motion_cpu_per_sec` 4.0 final / 1.5 preview + 25 s fixed; planning estimates until measured), no GPU, no keyframe.
* A motion shot has **no keyframe** (`missing_keyframes` skips it). When the narration exists, `pipeline.advance` enqueues one `remotion.render` job per missing shot (`motion_plan.shots.enqueue`; payload `shot_id`). The job (`motion_plan/jobs.py render_shot`): `ensure_plan` -> `quality_check` (rules + frame geometry, preview: 1 round x 1 frame per scene, final: 3 rounds x 2 frames) -> render at the episode's size and scale -> `Asset(role='shot_clip')` with `provenance.engine = 'remotion'` and `input_hash` of plan + look + size + length. `shot_specs` uses the clip in both modes, so the assembly carries **no Ken Burns note**.
* A motion shot whose clip is missing at assembly time (the file was removed) is one of the visible downgrades of `production/fallbacks.py` (code `no_motion_clip`: shot list, quality check, job log); normally `advance` never reaches the assembly without the clip.
* **Waiting is not failing**: Remotion not ready -> the job waits (`remotion_setup`, the setup starts by itself); the plan is kept. A failed job moves the episode to `failed` like any production step.
* A generated plan follows the narration: `MotionPlan.source_hash` = hash of the narration, length, look and series; a changed hash writes an UNEDITED plan again, an edited one (a version made by the owner, the chat or a patch) is kept - the owner can ask for a new one (`POST /api/shots/<id>/motion {action: write}`).
* The text model (`llm.resolve(page, 'storyboard')`) is asked first; a model that is off or answers badly gives the deterministic plan (never an error). Models are never asked to write colours, curves or sources: they pick names from `motionlib.py` lists.

## Quality loop

1. `qa.static_findings`: reading time (0.32 s per Persian word + 0.7 s entrance), speech longer than the scene, crowding, accent colour on the background.
2. `qa.geometry_findings`: from real frames (`INSTAI_QA:` console lines of `qa.tsx` + the picture): overflow / clipping, overlap, the platform's safe area (Shorts, Reels, story, TikTok, feed, YouTube, Telegram/Aparat; approximate figures), least font size (1.8 % of the height), WCAG contrast sampled from the pixels behind the text.
3. `qa.run_loop`: fix (`patch.py` operations: shrink, longer, readable colour, move an overlay, split a crowded scene) -> measure again, at most 3 rounds; every fix is a version of the plan (source `qa`).
4. `critique.run` (optional, the page's button / `motion.critique` job): 3-6 key frames + the plan -> the owner's vision model through **InstAI's own Ollama provider** (`identity.check._vision_model`: qwen3-vl, llava, minicpm-v, gemma3 ...) -> issues + a JSON patch -> every op validated alone -> applied -> frames again, at most 3 rounds, `before` / `after` pictures kept. **No cloud fallback**: Ollama off = the job WAITS (`ollama_down`); Ollama on without a vision model = state `unavailable` with the reason (the rules still ran).

## Pages and API

* `/remotion` lists 24 compositions: the four old ones, `ScenePlan` (JSON editor + templates + «plan from narration» + live rule checks) and the 19 components, each with a live `@remotion/player` preview and a render button.
* The storyboard's shot card (technique `motion_graphics`) has the **Motion-graphics scene plan** block: scenes, preview in the series' own look, a request box, undo / redo, versions, QA result, critique rounds.
* API: `/api/motion/components`, `/api/motion/plan/validate`, `/api/motion/plan/fallback`, `/api/shots/<id>/motion`, `/api/motion/plans/<id>` (+ `patch`, `undo`, `redo`, `restore`, `qa`, `critique`). Job kinds: `remotion.render` (with `shot_id`), `motion.plan`, `motion.qa`, `motion.critique`.

## Tests and self-test

* `tests/test_motion_plan.py` (56 tests: Python = Remotion registry / vocabulary / timeline (run through node + esbuild), plans, patches, versions, QA, prompts, roles, critique, API), `tests_ui/test_motion_plan_card.py` (the shot card in a real browser, fa / en, desktop / phone), `tests/test_motion_pipeline.py` (the pipeline with a stand-in renderer that makes real mp4 clips with ffmpeg: no keyframe, plan, QA, clip, assembly without Ken Burns, waiting, one-shot redraw, critique waiting for Ollama; and **the real run**), `tests/test_remotion.py` (every motif still has a look; the 24 compositions).
* The real run (`INSTAI_REMOTION_REAL=1 python -m pytest tests/test_motion_pipeline.py -k real_toolchain`, or `python -m instai.motion_plan.selftest <folder>`): one frame of every component x 3 sizes through the real toolchain, `qa.py` over the geometry, a montage per size.
* PC self-test rows (`instai/ops/pcselftest.py`): `motion_library` (always), `motion_frames` (when Remotion is ready: the 57 frames above), `motion_critique` (when Ollama runs and has a vision model). See `docs/selftests/instai-gpu-remotion-update.md`.

## Measured (this server, Linux, headless Chromium, no GPU; the owner's PC will be faster in the browser and the same in Python)

See `docs/BENCHMARKS.md` ("Motion-graphics components").

## Port provenance (read this before the next sync)

Ported on 2026-11-14 from the motion-studio v2 STAGING copy (`/root/stage/motion2`, the files unchanged since 11:46 UTC of that day: `components.py`, `specs.py`, `plans.py`, `patch.py`, `qa.py`, `critique.py`, `promptkit.py`, `timeline.py`, `motionlib.py`, `qa_browser.py` and `motion/remotion/src/{scenes,comp-data,comp-text,ctx,kit,fit,anim,text,qa,registry,presets,timeline,types,util}`, plus `motion/tools/qa.mjs`), because the v2 deploy (`motion2-integrate.log`) had not finished yet. NMarketing v3.02 is at `c23f861`. The live NM tree must be compared with this port when v2 lands: every NM file that this port copied is named in a `SOURCE:` line.

| NM file | InstAI file | what changed |
|---|---|---|
| `components.py` | `instai/motion_plan/components.py` | 19 of 33, fa+en labels / samples, `series` / `hook` / `next_episode` / `source` fields |
| `specs.py` | `specs.py` | style = a kit, `size` instead of `aspect`, `series` instead of `brand`, no audio block, SpecError / notes in fa+en, the honesty rule |
| `plans.py` + `models.py` | `plans.py` + `models.py` | a plan belongs to a shot, not a store / user |
| `patch.py` | `patch.py` | no brand / audio keys, English rules next to the Persian ones |
| `qa.py` + `qa_browser.py` | `qa.py` + `qa_browser.py` | colours from the kit (`colors.py`), fa+en findings, render.mjs `qa` mode instead of qa.mjs |
| `critique.py` + `promptkit.py` | `critique.py` + `promptkit.py` + `role.py` | InstAI's Ollama + vision model, no cloud, wait on `ollama_down`; episode / explainer prompts |
| `timeline.py` + `motionlib.py` | `timeline.py` + `motionlib.py` | the style's transition from `adapter.json` |
| `motion/remotion/src/*` | `remotion/src/components/*` | `ctx.tsx styleFromKit` (adapter), `ScenePlan.tsx` instead of `Template.tsx`, the series card, `SourceNote`, no shop pieces |
| (new) | `fallback.py`, `shots.py`, `jobs.py`, `api.py`, `selftest.py`, `defs.ts`, `adapter.json` | InstAI's own: the deterministic plan, the pipeline, the page |
