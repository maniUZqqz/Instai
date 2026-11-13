# Self-test: the animation-studio pipeline (identity, ladder, choice stories, channels)

Almost all of this feature is CPU work and is covered by the ordinary test suite (`tests/test_stick_kit.py`, `test_identity.py`, `test_ladder.py`, `test_choice_stories.py`, `test_channel.py`).
What needs the GPU PC (ComfyUI / Ollama) and therefore has a real-machine check is below. Each check is one small real job and a pass condition.

## 1. Identity sheets with the image model (`identity.sheets`)

* Needs: ComfyUI up, image workflow `flux_dev_fp8_t2i` ready, `image_engine` not `placeholder`.
* Job: `POST /api/characters/<id>/identity/sheets` after `POST /api/characters/<id>/identity/anchor` (or an anchor typed by hand). Payload run by the worker: `{"character_id": <id>}`.
* Pass: job `succeeded`; `result.references.sheet` and `result.references.expression` are CharacterReference ids; both pictures exist and are larger than 50 kB; `GET /api/characters/<id>/identity`
  shows `lock.refs.sheet` and `lock.refs.expressions`. (A human then looks at the sheet and locks; the lock is never automatic.)

## 2. Multi-reference keyframe (`qwen_image_edit_multiref`)

* Needs: the Qwen-Image-Edit-2509 model files (Models page offer) and two characters with locked identities and approved sheets.
* Job: produce an episode with a shot that names both characters (`POST /api/episodes/<id>/produce {"mode": "preview"}`), or run the workflow by hand with
  `{"prompt": "...", "image": "@input:ref.png", "image2": "@input:ref2.png", "width": 832, "height": 1472}` and the two sheets as inputs `ref.png`, `ref2.png`.
* Pass: `Asset.provenance.workflow == "qwen_image_edit_multiref"` and `provenance.reference == true`; the keyframe is 832x1472; `POST /api/episodes/<id>/consistency/run` reports
  both characters `ok` (colour key). If the workflow is missing on every PC the plan falls back by itself (sheet edit, LoRA, identity words) and the provenance note says which.

## 3. Deep consistency check (vision model)

* Needs: an Ollama vision model (`qwen3-vl:8b` or similar).
* Job: `POST /api/episodes/<id>/consistency/run {"deep": true}`.
* Pass: every check row has `vision_score` (not null) and `method` ends with `+vision`; with no vision model installed the rows carry the note `vision_not_run` and the result is unchanged.

## 4. Ladder stages with a real text model

* Job: `POST /api/episodes/<id>/ladder/<stage>/generate` for beat_sheet, dialogue, shot_list, layout, sound_design, grade (and `POST /api/series/<id>/ladder/<stage>/generate` for logline, treatment).
* Pass: job `succeeded`, a new version with `author == "ai"` and `provenance.model` set, the data has the stage's fields (`/api/ladder/catalogue`), and a model that answers invalid
  JSON three times fails the job and leaves the stage unchanged.

## 5. Choice story and season planning with a real text model

* Jobs: `POST /api/choice-stories/<id>/plan` and `POST /api/series/<id>/channel/plan`.
* Pass: `result.fallback == false`; `GET /api/choice-stories/<id>/report` has `validation.ok`; `GET /api/series/<id>/channel` has `validation.ok`. With `fallback == true` the model's answer was
  invalid and the deterministic plan was used (also valid) - the check still passes for the pipeline but not for the model's quality.

Failure modes (all visible in the queue and the screens, none need a click): ComfyUI or the model missing -> the job waits (`comfy_down` / `ollama_down`) and is retried; an invalid model answer ->
fallback plan + a banner on the screen; a locked identity whose workflow is not available on any PC -> the next strategy is used and named in the provenance.
