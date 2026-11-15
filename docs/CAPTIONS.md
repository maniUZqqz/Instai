# Word-by-word captions (0.18.0)

Shorts, Reels and TikTok viewers watch muted: big captions that mark the word being spoken are read, a fixed subtitle is skimmed. InstAI had one fixed style and never marked
the spoken word. This is NMarketing's tried caption engine (seven presets, ASS through libass, no tag injection) ported to the series / episode producer: the same words as an
SRT file for the platforms that take a subtitle file (YouTube, for one), colours from the series look, safe zones per platform, Persian right to left and English left to right.

Source of the code: NMarketing `backend/services/editing/titles.py`, `captions.py`, `director/tools.py` (CAPTION_STYLES), `safezones.py`, `services/video/subtitles.py` @ v3.02 (c23f861).
Every ported module carries a `SOURCE:` note. Not ported: the node speech-recognition / Whisper plumbing (InstAI already KNOWS the text of every cue) and the editor timeline
(clips, tracks). There is no runtime dependency on NMarketing.

## What the owner sees

* **Page settings, "Look" (ظاهر و تصویر)**: a card "Word-by-word captions" with the eight presets as real pictures, how the captions arrive (on the picture / a separate SRT file / none),
  the platform's safe zone (automatic or a named one), a vertical / landscape preview switch and the safe-zone guides drawn over the previews.
* **Episode, "Production and output"**: a card with the setting in force (the page's choice shows through) and one button that opens the same picker for this one episode (an override on top of the
  page's choice, "back to the page's choice"; the previews are asked for only when it is opened), the last render's setting with the honest "word times estimated" badge, and the SRT download. Changing it makes only the joining step run again (keyframes, narration and shot clips are reused).
* **Publishing package** (`publish.export`, the per-network package of `publishing/delivery_package.py`): `episode-NN.srt` (UTF-8 with BOM) next to the video and a line in its README, only the one that belongs to
  THIS video (`find_srt(ep, video)` looks at `provenance.from`; a file with no recorded origin still counts). Nothing is ever published by itself.
* **System, self-test**: row "Word-by-word captions (seven presets)".

## The pieces

| Module | Job |
|---|---|
| `instai/render/titles_ass.py` | `clean` (any dict -> one clamped clip), `build_ass` (clips -> ONE ASS document), geometry (wrap region, anchor, block height), piecewise-linear animations (fade, slides, pop, zoom, typewriter, blur), karaoke slices, ASS escaping |
| `instai/render/captions.py` | presets, `resolve_style` (preset + look -> colours with the contrast guaranteed), word times (`estimated_words`, `align_words`, `shot_words`), `group_words`, `caption_clips`, `plan` (a whole timeline -> `{ass, srt, clips, info}`), config rules |
| `instai/render/contrast.py` | WCAG relative luminance; a Python twin of `readableOn` / `accentOn` / `mix` in `remotion/src/kit/theme.ts` |
| `instai/render/safezones.py` | eight platform zones (Reels, Story, TikTok, Shorts, feed, YouTube, Telegram, Aparat), `zone_for(frame, platform)` |
| `instai/render/srt.py` | SubRip: wrap on a space, tidy (merge flashes, cap long cues), BOM |
| `instai/render/caption_previews.py` | one-frame lavfi source + the `ass` filter -> the preview PNGs, cached under `media/captions/previews/<hash>.png` |
| `instai/render/captions_check.py` | the real check (self-test row and tests): render, find the ink, test it against the safe zone and the brace rule |
| `instai/production/captions.py` | glue: page + episode config, the look of the series, render options, the hash part, the SRT asset |
| `instai/production/api_captions.py` | `GET /api/captions`, `GET /api/captions/previews`, `GET/PUT/DELETE /api/episodes/<id>/captions` |
| `frontend/src/components/CaptionPicker.tsx`, `pages/episode/CaptionsCard.tsx`, `i18n/packs/captions.ts` | the UI (fa + en) |

## The seven presets (and the plain one)

Sizes are **fractions of the frame height** (the same style is the same picture at 360p and 1080p; landscape, vertical and square all work). The colours are never in the preset.

| key | fa | look | size | highlight |
|---|---|---|---|---|
| `classic` | کلاسیک | InstAI's own plain subtitle (`render/subtitles.py`), untouched | - | none |
| `pop` | درشت و پرانرژی | black cut, thick edge, pop-in | 7.2 | colour + swells |
| `box` | کادرِ تیره | dark box, no edge | 5.6 | colour |
| `karaoke` | کارائوکه (ماژیک) | black cut, a marker behind the spoken word | 6.6 | marker |
| `clean` | ساده و تمیز | thin edge + shadow | 5.2 | colour |
| `neon` | نئونی | black cut, lit accent | 6.8 | colour + swells |
| `typewriter` | ماشین‌تحریر | each line types itself in | 5.8 | colour |
| `lower` | آرام (گفتگو و روایت) | smaller, soft band, no flashing | 4.6 | none (never flashes) |

* **Default behaviour is unchanged**: `visual.caption_style = {preset: "classic", mode: "burned", zone: "auto"}`. A page that never picks keeps the old ASS, the old hashes (no
  re-render is forced) and only gains the soft `episode.srt`.
* `visual.caption_style` (the video's captions) is a different thing from `publishing.caption_style` (the post text's tone), which keeps its name.
* Modes: `burned` (on the picture, plus the SRT), `soft` (the picture stays clean, the words travel as the SRT), `none`.
* The page's `visual.subtitle.position` (bottom / middle / top) is honoured by every preset.

## Colours: the series look, and the contrast rule

`production/captions.look_for` takes the look in force (series pick over page, `styles.library.look_of`) -> `remotion.kit.style_kit` -> palette + typography.

* the **highlight** is the look's accent (else the first of secondary / highlight / primary, else a signal colour) pulled until it reads on its own surface AND differs clearly from the text;
* the highlight must be a REAL colour (`captions.MIN_CHROMA`) at least 0.30 away from the plain words: a pale accent (the Chagher brand's #DBE6FF) or a grey is skipped; a look colour that does not read on
  the surface is brightened with its hue kept (`contrast.vivid_on`: the brand teal #126F85 becomes #1EBADF, not a muddy grey); a look with only greys gets a signal colour (#FFD400, #39FF88, #FFB703, #00E5FF).
  `neon` takes the look colour at its brightest that still reads (8:1) so it looks lit;
* the **box / outline surface** is the look's background (darkened when it is light, so a pale look still gets dark boxes and white letters);
* the **text** is the theme's `subtitle_color` when it reads, else white or black;
* the theme's `title_weight` moves the preset's weight one step (regular lighter, black heavier);
* the guarantee: plain words >= 4.5:1, the spoken word >= 4.5:1, the letters on the karaoke marker >= 4.5:1 against their own surface; a see-through box is made as solid as needed so
  the same holds over a **pure white** picture (`contrast.worst_text / worst_highlight`). Tested with 150 random palettes plus the awkward ones (all white, all black, accent equal to the text...).

## Lines: the estimate is never lower than what libass draws

`titles_ass.geometry` / `captions._line_fit` size the block from an estimated number of lines. `titles_ass.wrap_budget` keeps the estimate on the safe side: 5 % safety, minus the outline on both sides, minus the
marker that grows around the spoken word (`box` mode), 5 % less when the spoken word swells (`scale` mode). Found by viewing a real render (a thick-edged preset drew 3 lines where 2 were allowed) and held by
`tests/test_captions_render.py::test_no_word_state_of_a_real_sentence_draws_more_lines_than_the_preset_allows` (every preset x Persian + English x the moments the words are spoken).

## Word times: estimated or real

InstAI knows the text of every cue and the real duration of each shot's TTS audio, but no engine reports word times today.

1. `shot_words(text, start, duration, heard=None)`: with `heard` ([{w, s, e}] in seconds from the start of the shot's audio) the words are matched in order onto OUR spelling (difflib on a folded
   form that ignores Arabic diacritics, ZWNJ, digits alphabet) and unmatched words are filled between their neighbours; without it the words are spread over the narration by their length with a
   short pause after a full stop or a comma.
   Before spreading, `assemble.caption_segments` finds the AUDIBLE part of the narration WAV (`captions.speech_span`: 10 ms windows within 38 dB of the loudest, stdlib `wave`; an mp3 or an unreadable
   file keeps the whole duration), so the first word is not highlighted during the breath before the voice and the last one ends with the voice (`info.trimmed` = how many shots were trimmed).
2. The result says so: `info.estimated = true` unless EVERY word was matched; it is in the video's `provenance.captions` and in the job result (the screens show "word times estimated").
3. A voice engine (or a future recogniser) feeds real times by setting `TTSResult.words`; `prod.tts` stores them in the narration asset's `provenance.words` and `shot_specs` passes them as `ShotSpec.words`.

## Fonts

`instai/render/fonts/`: `Vazirmatn-Regular|Bold|Black|Light.ttf` (SIL OFL 1.1, `OFL.txt` beside them). The `ass` filter gets `fontsdir=fonts` (relative: a Windows drive letter in a filter graph is an
escaping trap); `assemble` copies the folder next to `sub.ass`. NM's font keys `vazir`, `vazir_black`, `vazir_light` map to these files; `FONTS[...]["line"]` is the ASS Fontsize / em ratio (1.713 on the
bundled files, measured against libass in `tests/test_captions_render.py::test_the_measured_text_width_is_what_libass_draws`: within 3 %). English captions use the Latin glyphs of the same family, left to right.

## Safe zones (approximate on purpose: apps move their buttons)

Fractions of the frame (top / bottom / left / right): Reels .13/.22/.05/.14, Story .13/.13/.05/.05, TikTok .11/.24/.05/.17, Shorts .10/.20/.05/.14, feed .05 all round, YouTube / Aparat landscape bottom .12, Telegram
landscape bottom .10. `zone_for` picks it from the frame shape and the page's publishing platform (vertical: Instagram -> Reels, TikTok, YouTube -> Shorts, Telegram / Aparat -> feed; landscape: the platform's own).

## Tests (all through the real ffmpeg + libass; skipped when this ffmpeg has no `ass` filter)

* `tests/test_captions_engine.py`: cleaner, ASS writer and injection, karaoke slices, estimated vs heard times, grouping, clips inside the zone, the presets, contrast for any look, config, zones, SRT, plan.
* `tests/test_captions_render.py`: reading order (RTL / LTR / digits first), the highlight modes, box / stroke / shadow, the line width ratio of each font, the number of lines, animations, hostile text, the seven presets x
  vertical + landscape x every platform zone, English, a pale look, the see-through box over white.
* `tests_ui/test_captions_screens.py` (browser, fa + en, desktop + phone): the eight presets as decoded pictures in the page settings, the landscape switch, saving, the episode card, an override and going back.
* `tests/test_captions_wiring.py`: the profile, the catalogue, real previews (and the cache), the episode override, a full episode render with fake providers for classic / a preset / soft / none, the
  publishing package, the staleness hash, English.
* `tests/test_pc_selftest.py`: the `captions` row.

Self-test row: see `docs/selftests/captions.md`.
