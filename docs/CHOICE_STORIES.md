# Interactive choice stories for Instagram

A branching story posted as numbered posts: each post ends with choices ("if you choose A go to post 7, if B see post 9"), like the stick-figure prison-escape phone game the owner mentioned.
Code: `instai/choice/` (`graph.py` rules, `services.py`, `render.py`, `export.py`, `api.py`, `jobs.py`). UI: page > "Choice stories" > a story. Nothing is posted by the app.

## The rules the planner and the validator enforce (`graph.validate`, tested in `tests/test_choice_stories.py`)

* One **start** post, and it is post 1. Every post is **reachable** from it.
* **No dead ends**: only ENDING posts (good / bad / secret / neutral) have no choices; a post can be marked "intended dead end" explicitly.
* **Numbering = posting order, every choice points FORWARD** (to a higher number). Numbers come from the depth of each post (longest distance from the start), ties by list order, so
  every edge raises the number. A deliberate "try again" loop is allowed only when the choice is flagged `loop`; any other cycle or backward number is an error.
* No self-loops, no two choices to the same post, no empty label, at most 4 choices (3 advised: they must fit on the picture), labels up to 28 characters, text up to 220 characters (warnings).
* At least one ending; a good ending is advised. Every post must be able to reach an ending.
* Captions never contain hard-coded numbers: they carry `{go:<post id>}` placeholders that are filled from the CURRENT numbering when the picture and the package are made, so inserting or
  moving a post can never leave a wrong number behind. A placeholder to a post that does not exist is an error (and stays visible as `{?id}`).
* Approval is refused while there are errors; any edit withdraws the approval.

## The flow

1. **Plan**: job `choice.plan` (model; the deterministic skeleton planner - a spine of decisions with early bad-ending detours, side routes that merge back, one good ending, a secret ending when
   there is room - is the fallback and also the fake provider's answer; a model graph that fails validation is replaced by the skeleton and flagged). Posts: 6-60.
2. **Edit**: the graph map (SVG, columns = depth), the post editor (text, ending type, background, pose, expression, caption, hashtags, choices with a target menu "number - title"), insert / delete /
   reconnect posts (every edit renumbers; versions are kept and can be restored), and "play it like a reader".
3. **Captions**: job `choice.captions` (model) or plain captions (no model).
4. **Approve** the graph (rules satisfied).
5. **Pictures**: job `choice.render`: stick-figure scenes drawn by code (no GPU, identical characters from the locked stick identities) or the image model with the locked identities
   (`ai_base`; placeholder in demo mode). Each picture carries the number badge, the text, the choice buttons with "-> post N" and, for endings, the banner and "go back to post 1". Only posts whose
   text, choices, target numbers, scene or character lock changed are drawn again.
6. **Package** (approved graphs only): `NNN.png` in posting order, `captions.txt` with the real numbers, `schedule.csv` (per_day posts from the start date at the hour, local time of the page and UTC),
   `graph.json`, `map.png`, `README`. The owner uploads it by hand, in order.

Honest limits: the planner's creative quality with a real model is not measured (GPU PC offline); the image-model renderer for posts is untested on a real ComfyUI; Instagram's own link features
(e.g. linking a caption to another post) are not used - the numbers are plain text.

## Ready-made stories (0.9.0)

`instai/choice/story_templates.py`: six complete, hand-written Persian stories with ORIGINAL characters (a cast of stick specs and 12-16 posts each). They work with no text model: **"Start with this story"** (page > Choice stories,
or inside an empty / existing story) creates the story, the characters on the page (stick identity drawn and locked) and the graph in one step; every word stays editable and renders like any other story.

| Key | Genre | Posts | Endings |
|---|---|---|---|
| `prison_escape` | prison escape (the owner's reference idea, written from scratch) | 16 | 5 bad, 1 good, 1 secret |
| `zombie_survival` | survival | 15 | 2 bad, 1 good, 1 neutral, 1 secret |
| `haunted_house` | gentle horror | 14 | 2 bad, 1 good, 1 secret |
| `detective_clock` | detective | 13 | 2 bad, 1 good, 1 secret |
| `space_oxygen` | space station | 13 | 2 bad, 1 good, 1 secret |
| `chagher_coach` | brand demo for the owner's product Chagher (genre `custom`) | 14 | 3 bad, 1 good, 1 neutral, 1 secret |

* `tests/test_story_templates.py` runs every story through `graph.validate` with zero warnings, checks the backgrounds / poses / expressions / cast exist, the text and label limits, and that nothing is a placeholder.
* The planner job falls back to the story of the same genre when no model answers (`provider: template`, a banner says so); a genre without one (`custom`) still gets the deterministic skeleton.
* **Chagher story rules**: only facts published on chagher.ir (a draft of the athlete's workout and meal plan in under a minute, sign-up in under a minute with a free start and no credit card, the coach's own standing instruction,
  a branded PDF, "the final decision is the coach's"). No price, no statistic, no invented customer, no promise of a result, never "replaces the coach" (a test enforces the forbidden words).
