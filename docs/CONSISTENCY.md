# Character consistency: one identity on every page, image and video

The brief: reference sheets generated ONCE, kept identical in every shot, picture and video clip, with a consistency check. Code: `instai/identity/`, `instai/render/stick/`.
UI: page > Characters > a character > "Identity and consistency"; episode > Studio ladder > Key art (the consistency board).

## The lock

`CharacterLock` (one per character): the English **identity anchor** (the same words in every prompt), the **colour key** (hex + role + name), a fixed **identity seed**, the approved
**model sheets** (CharacterReference ids), an optional approved LoRA, the preferred strategy, and for characters drawn by code the **stick spec**. Editing is possible while it is a
draft; "Approve and lock" approves the referenced sheets and bumps `version`. A locked identity is changed only after an explicit "Unlock". The keyframe hash contains the lock
versions of the characters in the shot, so a new lock version makes **only the pictures that show that character** stale (partial regeneration, as everywhere else).

## Strategies (`identity/strategies.py`; `auto` picks the strongest one that can run right now)

| Order | Strategy | How | GPU | Licence |
|---|---|---|---|---|
| 1 | `stick_rig` | The character is DRAWN from its spec (colours, head, cap, scarf...) - identical in every pose, scene, still and puppet video by construction | no | own code |
| 2 | `multiref_edit` | Qwen-Image-Edit-2509 gets the approved model sheets of up to three characters and draws a NEW scene with them (workflow `qwen_image_edit_multiref`). This is the open counterpart of IP-Adapter / PuLID-style conditioning: the model SEES the reference | yes | Apache-2.0 |
| 3 | `sheet_edit` | A keyframe edited from ONE character's sheet (Qwen-Image-Edit or FLUX img2img; the older hero path) | yes | Apache-2.0 / FLUX [dev] non-commercial |
| 4 | `lora` | A character LoRA trained with ComfyUI's TrainLoraNode, used only after the owner approved its measured before/after | yes | FLUX [dev] non-commercial |
| 5 | `anchor_seed` | Identity words + colour key in every prompt, negative "different outfit/colours", fixed identity seed | yes | n/a |

Not used on purpose: **IP-Adapter FaceID / InstantID / PuLID** need InsightFace face weights (non-commercial licence, as the brief already notes) and only understand real
faces, not cartoon, anime or stick characters.

Every prompt for a shot with locked characters goes through `identity.service.plan_for_shot`, called first by `hero.keyframe_inputs` (any technique, up to three characters in one
shot). Stick characters never reach an image model: `identity.stickshots` draws their keyframes (pose, expression and background are read from the words of the shot, English and Persian).

## The stick-figure kit (`instai/render/stick/`)

Pure Pillow, no GPU: 8 expressions, 24 poses, 13 backgrounds, props and accessories as data (`spec.py`); a rig in the format of the puppet renderer (so the existing motion library, blinking
and Rhubarb lip-sync drive it; extra motions run, sneak, panic, shiver, fall, punch, cheer); stills with speech bubbles, captions and effects; a model sheet (front and mirrored view, 8
expressions, 8 poses, colour key, identity words). Persian text is drawn by `instai/render/fa_text.py`: libraqm when it works, otherwise a built-in shaper (contextual forms + simplified
bidi) because Pillow's Windows wheels need a separate fribidi DLL. `tests/test_stick_kit.py` compares both layouts.

## The check (`identity/check.py`)

1. Colour key: every signature colour of the palette (not near-white/black/grey) must be visible. Exact for flat styles. Measured on the stick kit (shares of the picture): a scarf on
   a 0.3-height figure 0.00005, a hat 0.0005, limbs 0.002-0.008; a wrongly coloured character 0. Threshold `MIN_SHARE = 0.00003`, `PALETTE_OK = 0.67`. **Limit:** a background of the same
   colour can hide a missing colour (measured: the bridge background is blue, the desert amber, the lab red).
2. Structure: the existing colour/structure embedding against the sheet. Decides only when the character has no signature colours (heuristic thresholds, not calibrated on real clips).
3. Vision (optional, "Deep check"): a local vision model through Ollama (qwen3-vl, llava, gemma3 ...) is shown the sheet and the picture. Not installed = "not run", never "ok".

A failed check is a **flag**, not an action: the board lists the shots and "Open retake requests" creates ONE `RetakeRequest` per flagged shot (not repeated). Nothing is regenerated or deleted automatically.

## What is UNVERIFIED (needs the GPU PC)

* `qwen_image_edit_multiref@1.json` (and the older `qwen_image_edit_ref`) were written from ComfyUI's template documentation and never run on a real ComfyUI; the Qwen models must be downloaded
  (they are `required_models`; the Models page offers them). Quality of identity transfer from a sheet is not measured.
* The vision check and the LoRA path were not run against real models in this round (the GPU PC was offline).
* Thresholds of the structure score are heuristics (see `production/consistency.py`).
