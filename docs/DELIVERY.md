# Delivery: loudness, sound check, the nine networks and the package (0.15)

Ported from NMarketing (backend/services/editing/audioqc.py, audiofx.py, social_sizes.py, export.py, safezones.py, apps/content/caption_guard.py, hashtags.py @ v3.02, c23f861)
and customised for a channel / series producer. Every ported module carries a `SOURCE:` note. InstAI does not import anything from NMarketing at run time.

What the owner gets, in one list:

1. The loudness of every FINAL render is measured after the render with the platforms' meter and corrected to the page's target (-14 LUFS for new pages), true peak under -1 dBTP.
2. Three sound problems are found from the file itself and named by shot and track: the same speech twice (echo), music or an effect as loud as the voice, an out-of-phase mix.
3. A delivery table with the nine networks (Instagram Reels, Story, 4:5 post, square post; YouTube wide and Shorts; TikTok; Telegram; Aparat).
4. The publishing package holds one file per network the page targets, at that network's size, frame rate, quality and loudness - and only those networks.
5. The caption is read before it is copied (broken number, the same line twice, an image-model instruction in the post, an unfinished sentence, too many emoji, glued hashtags) - warnings only, never a rewrite.
6. Two rows in the PC self-test prove 1 and 2 on this very PC by themselves.

## 1. Loudness (`instai/render/loudness.py`)

* `PROFILES`: `social` -14 (YouTube, Shorts, Reels, TikTok), `messenger` -16 (Telegram, Aparat), `broadcast` -23. The stored value stays the number `audio.target_lufs`; the profile is only a name
  for it in the settings screen (a number that is none of the three shows as «Custom»).
* **New pages start at -14. A page made before 0.15 keeps -16** until its owner changes it: `pages/migrations/0004_keep_legacy_loudness.py` writes -16 into every audio profile that lacks the number and gives a
  page that has no audio profile row one (such a page read the default, which is now -14). `tests/test_delivery_migration.py` runs it on the real migration graph.
* `settle(path, target, tp=-1.0, tolerance=0.8, max_rounds=3)` (ported `settle_loudness`): measure the file (`ebur128=peak=true`, decoded, true peak 4x oversampled) -> when off by more than the tolerance
  or the true peak is above the ceiling, re-encode only the SOUND with the missing gain and a peak limiter (the picture stream is copied: seconds, not a render) -> measure the candidate -> adjust the
  limiter ceiling by the measured AAC overshoot (always from the original file: one generation of AAC) -> at most 3 rounds, the best candidate wins, a file that no candidate improves is left as it was.
  Never raises, never leaves a half-written file. `target=None` = peaks only.
* Where: `production/deliveryqc.after_render`, called by `pipeline.step_assemble` right after `assemble.assemble` and BEFORE the file becomes an Asset, so the registered file, its `loudness_lufs` and the
  cover/QC all describe the delivered bytes. A preview keeps the render's own loudness (`{"skipped": "preview"}`); a page can switch the pass off (`audio.loudness_settle = false`, `{"skipped": "off"}`).
* Result on the final Asset: `provenance["loudness"] = {before, lufs, tp, tp_before, tp_ceiling, target, tolerance, adjusted, rounds, gain_db, ok}` (and `provenance["target_lufs"]`).
  The quality panel's `loudness` row says target, before and rounds; the `true_peak` row says the peak against the -1 dBTP ceiling.
* The switch enters the timeline hash only when it is OFF, and the target was already part of it: renders made before 0.15 stay current.

## 2. Sound check (`instai/render/audioqc.py`, `production/deliveryqc.py`)

| Check | Row | How | Line |
|---|---|---|---|
| Echo (the same speech twice, 40 ms - 1.2 s apart) | `audio_echo` | whitened, band-limited (200-3500 Hz) auto-correlation of the final mix, 6 s windows | peak >= 0.16 at the same lag in >= 34% of the speech windows; **per shot** (slice of the mix): >= 0.28 in half the windows |
| Music or an effect over the voice | `audio_masking` | the episode's STEMS rendered through the same filter pieces as the mix (`assemble.track_filters`, `assemble.DUCK_FILTER`): narration, ducked bed (music, ambience), unducked effects; voice against each over the 50 ms frames where the voice speaks, shot by shot | voice < 6 dB above a bed group (and the bed above -60 dB) |
| Phase | `audio_phase` | channel correlation of the final file | correlation < -0.25 |

* A warning names the shot (1-based, the numbering of the storyboard and the ladder) and the track (kind + label, e.g. «جلوه «door slam»»); for an echo it says whether the narration itself plays twice
  (its own stem shows the repeat) or a track carries speech (the narration alone is clean). Persian text in `message`, English in `message_en`.
* **Why per shot**: a single doubled shot in a long episode is far under a third of the file; the file-level line of NMarketing alone would never see it (found while testing: 1 doubled shot of 3).
* **Tonal guard**: a strictly periodic signal (the fake narration engine's sine bursts, a synthetic tone) correlates with itself at many lags; a real echo has one peak. A window with >= 4 strong peaks
  more than 25 ms from the highest is «tonal» and is not called an echo. Without it every fake-provider render got a false echo warning.
* Calibration (docs/BENCHMARKS.md): clean synthetic speech tops out at 0.081, real TTS narration at 0.20; a copy at -12 dB gives 0.23, at -6 dB 0.39, an equal copy 0.49; fake narration has 9-11 far peaks,
  real narration 0-1.
* The results are stored on the final Asset (`provenance["audio_qc"]`); an older render (or a retake) without them is analysed on the file itself (echo and phase only).
* **numpy is the one requirement** (`requirements.txt`: `numpy>=1.26,<2.3`; the START.bat bootstrap reinstalls on the requirements hash). Without it the quality panel has ONE info row saying so and the render goes on.
* NOT ported: music_match (InstAI makes its own music from the mood, nothing to rank), silence_intel (TTS narration has no stumbled pauses), the subject-following reframe.

## 3. The nine networks (`instai/render/delivery.py`)

| Key | Network | Shape | Size | fps | Quality (x264 crf) | Audio | Max length | Safe zone | LUFS |
|---|---|---|---|---|---|---|---|---|---|
| `ig_reel` | Instagram Reels | 9:16 | 1080x1920 | 30 | high (18) | 192k | 90 s | reels | -14 |
| `ig_story` | Instagram Story | 9:16 | 1080x1920 | 30 | high (18) | 192k | 60 s | story | -14 |
| `ig_post` | Instagram post | 4:5 | 1080x1350 | 30 | high (18) | 160k | 60 s | feed | -14 |
| `ig_square` | Square post | 1:1 | 1080x1080 | 30 | high (18) | 160k | 60 s | feed | -14 |
| `yt_wide` | YouTube 16:9 | 16:9 | 1920x1080 | 30 | high (18) | 192k | - | feed | -14 |
| `yt_shorts` | YouTube Shorts | 9:16 | 1080x1920 | 30 | high (18) | 192k | 180 s | shorts | -14 |
| `tiktok` | TikTok | 9:16 | 1080x1920 | 30 | high (18) | 192k | 180 s | tiktok | -14 |
| `telegram` | Telegram / Eitaa | any (16:9 preferred) | short side 720 | 30 | small (27) | 128k | - | feed | -16 |
| `aparat` | Aparat | 16:9 | 1920x1080 | 25 | medium (22) | 160k | - | feed | -16 |

All numbers are NMarketing's and **approximate** (the apps move their limits); every screen and the README say so. NVENC (`h264_nvenc`, cq = crf + 1) is used when this PC's ffmpeg lists it AND the card accepts the
encode; any failure repeats the encode on the CPU and the GPU is not asked again for 10 minutes.

**Shape policy (no crop, ever).** An episode is rendered in one shape today: 9:16 (`render/assemble.py`). The plan of a network says `ready` (the shape matches, or the network plays any shape: Telegram),
`fit` or `needs_aspect`. For `needs_aspect` no file is made and the README says why, in both languages. Two ways out: when the assembly learns to render another shape natively, the plan offers
«re-render in that shape» (`delivery.RERENDER_ASPECTS` = the shapes it can render; today only 9:16, so the offer is not made for any network - it would be a promise nobody keeps); and, chosen per network by the
owner (`PublishTarget.config.fit = "blur"`, the switch in the Publishing tab), **the whole frame in the middle over a blurred copy of itself** - nothing is cut away. A file is never larger than its source.

## 4. The package (`instai/publishing/delivery_package.py`, `services.export_package`)

```
episode-01.mp4                    the finished episode (always)
cover.png                         the publication's cover or the newest cover (as before)
caption.txt                       the caption AS WRITTEN + the hashtags (glued ones repaired)
hashtags.txt                      the repaired hashtags
README.txt                        Persian + English: what is where, what was measured, what to look at
delivery.json                     the same for programs (plan, per-network result, lint, hashtags)
episode-01.srt                    only when the captions work has registered a SubRip file (kind=subtitle, *.srt)
<network>/episode-01-<network>.mp4    one folder per network the page targets AND whose shape fits (or the whole-frame option is on)
<network>/cover.<ext>             a cover made for that network (Asset provenance network/format = key), else the one cover
```

* Networks come from the page's ENABLED publishing targets (`PublishTarget.platform`): any of the nine keys, or the old names `instagram` (= `ig_reel`) and `youtube` (`yt_shorts` for a vertical episode). A target that
  means none of them is named in the README, not dropped silently. A page with no target gets exactly the package it always got (plus `delivery.json` and the checks in the README).
* Each network file: size (never enlarged), frame rate, quality, AAC at the network's bitrate, then `loudness.settle` to the network's target (-14 or -16, measured on the file). A file that already has the
  shape and rate is copied, not re-encoded. One network failing is reported in the README and skipped; the others are kept.
* The soft inputs are looked up, never required: SRT (`captions_to_instai`) and per-network covers (`thumbs_to_instai`). If those ports register them differently, change `find_srt` / `cover_for` only.
* The job `publish.export` has a 3 hour timeout and reports progress per network; nothing is ever posted.

## 5. Caption lint and hashtags (`instai/publishing/caption_lint.py`, `hashtags.py`)

Arithmetic rules only (no model): `broken_number` («۶۰۰٬۰۰»), `repeated` (the same sentence twice - a call to action written twice), `image_prompt` (storyboard / style words in the post),
`emoji` (> 6), `truncated` (a text of 120+ characters that stops mid-sentence), `glued_hashtag`, `duplicate_hashtag`. Dropped from NMarketing: the shop's «never say» list and the price reminders.
Approximate limits are NOTES (`level: "note"`): Instagram caption 2200 characters with its hashtags and 30 hashtags; YouTube title 100, description 5000, tags 500 characters.
The hashtag repair splits a glued tag only when every piece is a known word: a generic everyday-Persian list plus the page's own words (niche, pillars, hashtags, series and episode titles, character names).
The stored caption and hashtags are never changed; the package carries the repaired tags and says so.

## 6. API and screens

* `GET /api/delivery/networks` - the table, the loudness profiles, `rerender_aspects`.
* `GET /api/publications/<id>/delivery` - the plan of the package (per network: status, size, notes in fa + en, offers) and the check; `POST` with `{caption, hashtags}` checks a draft without saving.
* `POST /api/pages/<id>/targets {platform}` accepts the nine keys and the old names (400 otherwise); `PATCH /api/targets/<id> {config: {fit: "blur"|""}, enabled}`.
* Settings -> Audio: «Loudness for» (three profiles + custom) and the switch «Measure and correct the loudness after the render». Production tab: the quality panel shows the new rows in the reader's language.
* Page -> Publishing tab: «Networks of this page» (add, switch on/off, whole-frame option) and, under each publication, «Delivery to the networks» + «Caption and hashtag check».
* Self-test (System screen): `delivery_loudness`, `delivery_echo` (docs/selftests/instai-pc-selftest.md).

## 7. Tests

`tests/test_delivery_loudness.py`, `test_delivery_audioqc.py`, `test_delivery_table.py`, `test_delivery_package.py`, `test_caption_lint.py`, `test_delivery_pipeline.py` (fake providers, real ffmpeg, the real
assembly with music and an effect), `test_delivery_migration.py`, `test_delivery_selftest.py`.

## 8. Suggested version entry (for the lead, with the version bump)

fa: «تحویل حرفه‌ای: بلندیِ صدا بعد از ساخت روی ۱۴- LUFS اندازه‌گیری و اصلاح می‌شود (صفحه‌های قدیمی ۱۶- می‌مانند)، اکو و موسیقیِ هم‌بلندِ گفتار و فازِ برعکس با نامِ شات و ترک پیدا می‌شوند، بسته‌ی انتشار برای هر شبکه‌ای که صفحه هدف گرفته یک فایل با اندازه و بلندیِ همان شبکه دارد و کپشن و هشتگ پیش از انتشار بازبینی می‌شود.»
en: "Professional delivery: the loudness is measured after the render and corrected to -14 LUFS (old pages keep -16), a doubled voice, music as loud as the voice and a reversed phase are found and named by shot and track, the publishing package holds one file per network the page targets at that network's size and loudness, and the caption and hashtags are checked before posting."
