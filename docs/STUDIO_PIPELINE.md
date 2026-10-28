# Studio pipeline: how real animation studios work, and how InstAI reproduces it

The owner's brief: *the process must be exactly like a film / anime studio pipeline, with the difference that AI is our crew under our command.*
This file records what real studios do (with sources), then maps every stage to an InstAI stage, the AI role that does it and the human gate that
approves it. Research date: 2026-10-28. Everything not marked **unverified** was read on the page named in the source list (section 8).

## 1. Japanese TV anime (what the sources say)

| Stage | Terms | Who | Output | Approval / gate | Src |
|---|---|---|---|---|---|
| Planning | 企画 kikaku, 製作委員会 production committee | studio planners, producers, sponsors | proposal (business case, story, characters), a release slot, a contract (cours of ~13 episodes) | studio + sponsors; committee meets about monthly | J2 J6 J7 |
| Series composition | シリーズ構成, 構成会議 | series composer + director + producers (+ original author) | series outline split into episodes, writers assigned | composition meeting; director and composer have the last word on scripts | JW2 J4 J5 |
| Script meetings | 脚本, 本打ち hon-uchi | 2-4 writers, composer, director, producers | episode script: first draft in 1-3 weeks, final is usually draft 4-5 | the room approves the final draft; the series director approves nearly everything | J1 J3 J4 |
| Storyboard | 絵コンテ e-konte, コンテ打ち | episode director or storyboard artist | ~300-350 cuts per episode: cut numbers, dialogue, SE, rough pictures, durations; the last step of pre-production | director check, then client / rights-holder / committee see the provisional final | JW3 J2 J11 |
| Settings | 設定, character design, 美術ボード | designers, setting manager, art director | model sheets, "set pack", orders to the studio | concepts are presented, revised, accepted or rejected; series director approves; an animation meeting precedes production | J1 J2 J11 |
| Layout | レイアウト | key animators | per-cut layouts | animation director corrects; episode director checks against the board | J2 J5 JW5 |
| Key animation | 原画 genga | key animators | key drawings + timing sheet | animation director fixes (作監修正), chief AD, final 作画監修; the episode director inspects and can request **retakes**, cleared before in-betweening | J1 J5 J10 JW5 |
| In-betweens | 動画 dōga, 動画検査 | in-betweeners, inspectors | clean lines and in-betweens | inspection before finishing | JW7 J2 |
| Colour design / finishing | 色彩設計, 仕上げ | colour designer, painters | per-character colour charts; painted frames | palettes shown to the director; the colour specifier inspects and issues retakes | J9 JW6 J1 |
| Backgrounds | 美術 | art director, background painters | painted backgrounds | art director inspects all | J1 J11 |
| Compositing | 撮影 | compositing director | composited cuts | episode director sets the policy with the DP | J12 JW9 |
| Editing | 編集 | editor, director, producer | master video | fine cut approved, then locked | J1 |
| Voice recording | アフレコ (after the picture; プレスコ is the opposite) | sound director, actors, director | dialogue takes, often on unfinished footage | sound director checks scripts against boards; casting: director has the last word | JW1 J12 JW4 |
| Music / SE / final mix | BGM, SE, ダビング | composer, sound director, SE staff | final audio | audio director approves; the episode director attends the mix | J1 JW4 JW9 |
| Retake | リテイク | episode director, colour inspector, sound director | redrawn or re-recorded cuts | there is no single formal workflow; each department's inspector can send a cut back | J5 JW6 J12 J10 |

**Unverified** (no opened page defines them): delivery / first print (初号試写, 完パケ); the exact meeting name "kyakuhon kaigi" (found: 本打ち, 構成会議);
official Netflix / Disney / Pixar pipeline documents; Sakuga Blog pages (blocked).

## 2. Western film / TV animation (what the sources say)

| Stage | Terms | Output | Gate | Src |
|---|---|---|---|---|
| Pitch and bible | series bible, pitch bible | logline, characters, world, pilot, episode concepts (Final Draft's template: overview, why now, world, tone, backstory, where we begin, characters, pilot, outlines for five seasons) | shown to executives to get commissioned | W10 W11 |
| Premise / outline | break the story | 3-4 page premise, outline | group revises, then network notes; the outline is written for the network to greenlight before scripting | W12 W13 |
| Script and table read | rewrites, table read | ~38-42 pages; reactions and notes | creators give 1-3 rounds; network approves; locked after recording | W13 W19 |
| Storyboard | re-board | shot-by-shot staging | re-boarded many times before approval | W2 W4 |
| **Animatic / story reel** | animatic, Leica reel | boards timed to (scratch) audio | reviewed until the board is right: "where many expensive disagreements should happen"; the only gate described is director review | W3 W1 W16 |
| Design | model sheets, turnarounds, props, backgrounds, **colour script** | character sheet (turnaround, expressions, poses, props, palette) | layout begins only after designs are approved by the director | W9 W2 |
| Layout, animation, clean-up | rough, pencil test, in-betweens, ink and paint | final drawings | rough scenes are "sweatboxed" with the director until approved | W1 W2 W5 |
| Dailies / sweatbox | rushes | notes | director approves or asks for changes | W5 W6 |
| Retakes | retake notes | revised shots | technical retakes = execution errors; artistic retakes = scope changes; an episode is effectively approved when only 3-5 % of shots are in a third cycle | W8 |
| Post | compositing, edit, sound design, mix, ADR | approved masters | final checks: frame size, codec, sync, naming | W1 W7 |

A **colour script** is a strip of small pastel frames mapping colour, light and mood across the film, used to align a large team and to plan the
emotional arc (W17, W18). In anime the nearest tool is the colour designer's per-character chart (J9). A series bible is a pitch document that
shows the world, characters and central conflict can sustain several seasons (W10, W11). Anime records voices after animation, often on unfinished
footage (JW1); some Western shows record first so boarders can work from performances (W13).

## 3. Mapping: studio stage -> InstAI stage -> AI role -> human gate

| Studio stage | InstAI stage (where) | AI role | Human gate |
|---|---|---|---|
| Kikaku / pitch / series bible | **Development room**: brainstorm boards -> series bible (series screen > Development) | brainstorm facilitator, character designer, series creator (`studio_roles`) | approve ideas; **approve the bible** |
| Source research / "canon" | **Source + canon research** (source lookup AniList / Wikipedia / Fandom, or typed by hand) | canon researcher (uses only the stored extracts) | owner marks the step done; every item cites stored sources |
| Writers' room brainstorm / hon-uchi | **Brainstorm board** per template step (divergence, scenarios, gags, topics, analogies) | brainstorm facilitator, idea editor, idea merger | edit / merge / rate / reject / approve each card; "more like this" |
| What-If analysis | **Consequence map** and **alternative timeline** | story architect, continuity supervisor | edit the tree and rows; step approval |
| Series composition (シリーズ構成) | **Composition** = the episode-by-episode plan (existing plan + apply), now built on the bible | story architect | apply the plan; step approval |
| Greenlight / committee | **Development approval** (gate) | - | owner approves; nothing starts before it |
| Script (脚本) | Episode **script** (existing script editor) | scriptwriter (knows the bible, canon digest, continuity memory) | script review + approval (existing) |
| Storyboard (絵コンテ) | Episode **storyboard** (existing editor) | storyboarder | storyboard approval |
| **Animatic** | **Animatic**: timed stills + scratch narration + subtitles, rendered with the existing render path (`studio.animatic`, never changes the episode state) | - (ffmpeg + TTS) | approve the animatic (a changed shot makes it **stale**) |
| Settings / model sheets / colour script | **Design sheets**: character turnarounds, expressions, backgrounds, props, colour script per scene (prompts the director approves; images rendered with the same image engine as keyframes) | art director | approve each sheet / the stage |
| Casting (キャスティング) | **Voice casting**: one voice per speaking character, per language | casting director | owner confirms; stage approval |
| Production start (layout ... compositing) | hand-off to **production** (keyframes, narration, clips, assembly) | production pipeline (other workstream) | the **pre-production gate**: with `studio_mode` on, `storyboarding -> asset_generation` is refused until it is approved |
| Retake (リテイク / retake notes) | **Retake request** on one shot (reason, scope: image / voice / clip / all) | - | director's note; only that shot is regenerated; shown as open / done |
| Editing, ADR, music, SFX, mix | production's assembly and audio steps (other workstream); the Studio tab shows the status | - | quality review + approval (existing) |
| Delivery / first print | export package (existing, manual) | - | never automatic |

Two things differ on purpose: the crew is AI (every role above is one validated model call; none can write to the database or run commands), and
the owner can open any stage at any time, edit any output, and send a single piece back (a card, a shot, a sheet) without redoing the rest.

## 4. Human gates follow the page's automation level

| Level | Development | Pre-production |
|---|---|---|
| `manual` | every step waits for an explicit approval | every stage waits for an explicit approval |
| `assisted` | bible, composition and the final gate wait; other steps pass by themselves once the AI result exists | storyboard and the final gate wait; animatic, design and casting pass when ready |
| `automatic` | only the final development gate waits (an AI-written bible is approved automatically and marked "auto") | only the final pre-production gate waits |

Passing automatically never hides anything: the step is marked auto-approved, stays editable, and editing it again re-opens it. **Nothing is ever
published automatically**, at any level.

## 5. Templates

Steps are data (`instai/studio/templates.py`). The launch formats are templates:

* **What-If**: source -> canon research -> divergence brainstorm -> consequence map -> alternative timeline -> bible -> composition -> approval.
* **Recurring character**: character brief (-> character bible) -> scenario brainstorm -> gag / series-format brainstorm -> bible -> composition -> approval.
* **Concept explainer**: topic brainstorm -> research with sources -> analogy brainstorm -> fact check -> bible -> composition -> approval.
* **Custom**: series brainstorm -> bible -> composition -> approval.

New templates are made in the UI (Library > Templates): choose step kinds (source, research, brainstorm, profile, map, timeline, factcheck), name them
in both languages, pick the brainstorm lens, reorder. Bible, composition and the final gate are always the last three steps.

## 6. Real-series lookup: sources and licence consequences

The owner can type a series title; the app asks public catalogues for candidates and lets him pick one or enter it by hand. The internet may be slow
or blocked (the owner is in Iran), so every provider is optional, failures are reported per provider, and manual entry always works.

| Provider | Used for | Terms that matter (read 2026-10-28) | Default |
|---|---|---|---|
| AniList GraphQL (`https://graphql.anilist.co`, POST) | titles, year, format, episodes, genres, description, characters, relations | free for low-volume use; "backup / data storage" and "hoarding or mass collection" are prohibited; a commercial licence is needed above about $150 revenue per month; rate limit 90/min (currently degraded to 30/min) (B1 B2 B4) | on |
| Wikipedia / MediaWiki | plot, premise, characters (plain-text extract, section filtered) | CC BY-SA 4.0; commercial use allowed; attribution and share-alike if text reaches a published product; descriptive User-Agent required (WP1-WP6) | on |
| Fandom wikis (`<wiki>.fandom.com/api.php`) | extra canon detail (wiki name typed by the owner) | CC BY-SA (version unverified; check each wiki's rights info); wikitext is cleaned to plain text | opt-in |
| Jikan (unofficial MyAnimeList scraper) | alternative catalogue | MAL's terms are personal / non-commercial and forbid scraping; the official MAL API allows "internal business purposes" only (JK1-JK4) | **off** |

InstAI therefore: fetches one title at a time on request, stores the text only as internal research notes (never as published copy), writes scripts
from its own bible, shows the fan-content notice whenever a real series is chosen, and keeps the commercial-licence question for AniList visible in
the owner's report. Reachability from the dev PC: Wikipedia and Fandom answered, AniList answered a POST, Jikan timed out (unverified why).

## 7. Open points

* Colour script and design images need the production image engine (ComfyUI); without it the sheets hold prompts only (and demo placeholders).
* The animatic uses scratch narration from the page's TTS engine; if none is ready it is silent and timed by reading speed.
* Production should read `Episode.translations[lang]` (script + per-shot narration) and `Character.voice.voices_by_language` for bilingual renders,
  and should compose prompts with `instai.styles.library.compose_for_page(page)` so themes and video fragments are used (see DECISIONS.md).
* Delivery / first-print gates are not described by any verified source, so none is modelled.

## 8. Sources

Japanese pipeline: J1 kanzenshuu.com/animation-production/positions-and-roles; J2 gundamunofficial.com/production/process.html; J3 wavemotioncannon.com/2017/07/05/anime-pre-production-from-story-to-script/;
J4 animenewsnetwork.com/answerman/2022-11-11/.191564; J5 animenewsnetwork.com/feature/2016-08-17/your-ultimate-guide-to-anime-ending-credits-part-iv/.105472; J6 animetics.net/2015/09/15/on-production-committees-and-tv-anime/;
J7 gigazine.net/gsc_news/en/20150402-animation-producer-talk-aj2015; J9 animenewsnetwork.com/interview/2024-11-15/the-complicated-process-of-color-design-in-anime-an-with-nokotan-arisa-komatsu/.216975;
J10 animeanime.jp/article/2022/02/04/67348.html; J11 atriumdotart.substack.com/p/decoding-anime-production; J12 animenewsnetwork.com/interest/2021-03-30/industry-professionals-detail-anime-production-process-at-animejapan/.171252;
JW1-JW9 ja.wikipedia.org (アフレコ, シリーズ構成, 絵コンテ, 音響監督, 作画監督, 色彩設計, 動画_(アニメーション), アニメ監督).

Western pipeline: W1 studioliddell.com/news/the-animation-production-pipeline-a-complete-guide; W2 en.wikipedia.org/wiki/Traditional_animation; W3 en.wikipedia.org/wiki/Animatic; W4 en.wikipedia.org/wiki/Storyboard;
W5 en.wikipedia.org/wiki/Sweat_box; W6 en.wikipedia.org/wiki/Dailies; W7 en.wikipedia.org/wiki/Automated_dialogue_replacement; W8 blog.cg-wire.com/how-to-handle-animation-retakes-in-a-cartoon-tv-show;
W9 blog.cg-wire.com/character-sheet-animation; W10 finaldraft.com/blog/building-your-tv-series-bible-in-final-draft; W11 studiobinder.com/tv-show-bible-examples; W12 michaeldantedimartino.com/post/writing-the-premise;
W13 animationobsessive.substack.com/p/writing-fosters-home-for-imaginary; W16 denki.co.uk/?p=9285; W17 cartoonbrew.com/rip/ralph-eggleston-a-cornerstone-of-pixars-visual-style-dies-at-56-220781.html;
W18 chroniclebooks.com/products/disney-pixar-the-color-of-toy-story; W19 foxnews.com/story/simpsons-gets-ready-for-16th-season.

APIs and licences: B1-B5 anilist.gitbook.io/anilist-apiv2-docs (rate-limiting, terms-of-use, graphql, considerations, reference); JK1 raw.githubusercontent.com/jikan-me/jikan-rest/master/storage/api-docs/api-docs.json;
JK2 github.com/jikan-me/jikan-rest; JK3 myanimelist.net/about/terms_of_use; JK4 myanimelist.net/static/apiagreement.html; WP1 mediawiki.org/wiki/Extension:TextExtracts; WP2 mediawiki.org/wiki/API:Etiquette;
WP3 foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy; WP4 foundation.wikimedia.org/wiki/Policy:Terms_of_Use; WP5 mediawiki.org/wiki/Wikimedia_REST_API; WP6 en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content.
