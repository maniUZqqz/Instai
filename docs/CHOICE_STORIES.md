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
