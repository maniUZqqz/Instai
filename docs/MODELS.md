# Models, tools and licences

Generated from `instai/core/licences.py` by `scripts/gen_docs.py` - edit the registry, not this file.
The Settings page shows the same table as badges.

**How to read "Verified".** "model card read on 2026-10-28" means the licence line on the model's public Hugging Face card was read on that
day; the full licence text was **not** audited and nothing here is legal advice. "brief" means the owner's brief states it. "NOT verified"
means nobody has checked yet. Territorial and sanctions clauses (relevant from Iran) must be read in the full texts before a model is
adopted for published, commercial content.

**Open owner decisions**
1. **FLUX.1 [dev]** - weights are under a non-commercial licence. The model card says generated outputs may be used commercially "as described in
   the licence"; the licence text itself is gated and could not be read here. Until the owner (or a lawyer) accepts it, InstAI is built so that
   the image model is swappable: Qwen-Image and Z-Image are Apache-2.0 per their cards and must be benchmarked against FLUX with the same seeds.
2. **Anime video model** (Index-AniSora V3.2, AnimeGen I2V, Wan 2.2 + anime LoRA) - Phase 3 comparison; each licence (including the extra repo
   terms of AniSora) must be read first. No character/IP LoRAs.
3. **Voices** - the licence of each Piper voice (e.g. `fa_IR-gyro-medium`) must be checked on its model card before publishing commercially.

**Measured numbers** (VRAM at the chosen quantisation, seconds per step, quality notes) are only entered in `docs/BENCHMARKS.md` after the
benchmark has run on the real machine; this table never contains invented numbers (the VRAM column says "to measure" where unknown).

**Finding what is already installed.** InstAI does not ask where the models are: `instai/core/discovery.py` searches the PC (ComfyUI
installs with their launcher, every models folder incl. `extra_model_paths.yaml`, NMarketing's voice engines, Piper, Ollama) and the
**Models** page shows what was found, where, what is missing and which feature each missing file blocks. Model files are matched by file
name in any sub-folder and letter case, plus known aliases (e.g. `FLUX.1 [dev] FP8.safetensors` = `flux1-dev-fp8.safetensors`).

| Model / tool | Role | Licence | Commercial use | Verified | VRAM | Notes |
|---|---|---|---|---|---|---|
| FLUX.1 [dev] (FP8) **(OWNER DECISION)** | image | FLUX.1 [dev] Non-Commercial License | conditional | model card read on 2026-10-28 (licence line only) | 12 GB (fp8) | Weights are non-commercial. The model card says generated outputs may be used commercially 'as described in the licence'; the full text (gated on Hugging Face) was not readable here. Owner/lawyer must read it. Fallback: Qwen-Image / Z-Image (Apache-2.0), to be benchmarked. |
| Qwen-Image / Qwen-Image-Edit | image + edit | Apache-2.0 | yes | model card read on 2026-10-28 (licence line only) | to measure | Supported by the installed ComfyUI. Candidate to replace FLUX; also pose/expression editing from references. |
| Z-Image (Turbo) | image | Apache-2.0 | yes | model card read on 2026-10-28 (licence line only) | to measure | Candidate image model; fast. |
| Animagine XL 4.0 Opt (SDXL anime) | anime image | CreativeML Open RAIL++-M | yes | model card read on 2026-10-29 (licence section: commercial use permitted, use-based restrictions) | to measure (SDXL) | Optional download offered on the Models page (asks first, 6.9 GB). Workflow sdxl_anime_t2i (core nodes only). Anime keyframes instead of the general FLUX model; also a way around the FLUX dev weights licence question. |
| Wan 2.2 I2V A14B (fp8, high/low noise) | video | Apache-2.0 | yes | model card read on 2026-10-28 (licence line only) | 12 GB with fp8 + 8-step LoRA | Card: authors claim no rights over generated content; users remain responsible for lawful use. Planning estimate 8-10 GPU min per 5 s 480p shot - NOT measured. |
| Index-AniSora V3.2 | anime video | Apache-2.0 + additional restrictions (repo LICENSE) when retraining / making derivatives | unknown | HF card + GitHub LICENSE read on 2026-10-28 (not audited) | GGUF Q4_0 ~9 GB per expert | Use of the community GGUF conversion for generation is not retraining, but the extra clauses (legal compliance of outputs, indemnity, downstream binding) must be read by the owner. Needs the ComfyUI-GGUF custom node. Compared against plain Wan 2.2 on the same stills and seeds in Production lab > Compare. Optional download on the Models page (asks first; ~18.1 GB + the node; sha256 pinned). |
| AnimeGen I2V (AIdeaLab) | anime video | Apache-2.0 (card tag: commercial-use) | yes | HF card + LICENSE read on 2026-10-28 (licence line only) | GGUF Q4_K_M ~9.7 GB per expert | Wan 2.2 I2V A14B fine-tune by AIdeaLab. The card recommends an RTX 4090 for the original weights; the community GGUF needs the ComfyUI-GGUF custom node. Comparison candidate. Optional download on the Models page (asks first; ~19.3 GB + the node; sha256 pinned). |
| ComfyUI-GGUF custom node + gguf package | loads GGUF models in ComfyUI | Apache-2.0 (node); MIT (gguf) | yes | GitHub licence field + PyPI classifier read on 2026-10-29 | - | Installed only together with an anime GGUF model, after the owner confirms. Pinned commit 6ea2651; ComfyUI must be restarted afterwards. |
| Wan 2.2 + anime style LoRA | anime video | varies per LoRA | unknown | NOT verified | - | Only if that specific LoRA's licence allows selling output. Many popular ones do not. No character/IP LoRAs. |
| LTX-2 **(EXCLUDED)** | video | requires a not-sanctioned-country representation | no | brief | - | EXCLUDED: the owner cannot make that representation from Iran. |
| HunyuanVideo 1.5 **(EXCLUDED)** | video | territorial / trade-law clauses | no | brief | >= 14 GB | EXCLUDED: territorial clauses and needs more VRAM than the RTX 3060. |
| Wan 2.5 and later **(EXCLUDED)** | video | API only (no open weights) | unknown | brief | - | Not planned: nothing to run locally. |
| MOSS-TTS-Realtime 1.7B + Persian LoRA | speech, voice cloning | Apache-2.0 | yes | model card read on 2026-10-28 (licence line only) | to measure | Best Persian narration; needs its own server (GPU). |
| MOSS-SoundEffect v2.0 | ambience / SFX | Apache-2.0 (per Qasem notes) | unknown | NOT verified | to measure | Phase 3. |
| ACE-Step 1.5 (turbo) | music | MIT | yes | model card read on 2026-10-28 (licence line only) | to measure | Phase 3. |
| Piper (engine) + voice fa_IR-gyro-medium | speech (CPU fallback) | engine MIT; each voice has its own licence | unknown | NOT verified | none (CPU) | The voice licence must be checked on its model card before publishing commercially. |
| Vosk (ASR) | speech recognition | Apache-2.0 (per brief) | yes | brief | CPU | Used later for subtitle timing checks. |
| Pocket-TTS (voice kit) **(WARNING: owner-enabled, not for commercial use)** | speech | CC-BY-NC-4.0 - NON-COMMERCIAL | no | brief | CPU | AVAILABLE ON REQUEST of the owner, with a visible warning wherever it is chosen and in the QC report. Never selected automatically; do not use it for content you publish commercially. |
| Edge TTS (unofficial online endpoint) **(WARNING: owner-enabled, not for commercial use)** | speech | unofficial endpoint, not for commercial use | no | brief | - | AVAILABLE ON REQUEST of the owner, with a visible warning (needs internet; not a licensed service). Never selected automatically. |
| Rhubarb Lip Sync 1.13 | mouth shapes | MIT | yes | brief | CPU | Drives puppet-2D mouths. MEASURED (dev PC): English via PocketSphinx 4.3 s for 7.1 s of speech; Persian via the phonetic recogniser 1.3 s for 6.2 s; pauses are masked by loudness because phonetic labels pauses as speech. |
| Manim (Community) | diagrams for explainers | MIT | yes | brief | CPU | Phase 3 candidate for code-rendered motion graphics (alternative: SVG/Canvas to video). |
| Real-ESRGAN x4v3 | upscale | BSD-3-Clause | yes | NOT verified | small | Already used by NMarketing. |
| BiRefNet-lite | background removal (parallax layers) | MIT (per repo) | unknown | NOT verified | small | Phase 3. |
| InsightFace detector weights **(EXCLUDED)** | talking-head dependency | non-commercial | no | brief | - | EXCLUDED: check every dependency of talking-head tools. |
| FFmpeg 7.1.1 essentials build | assembly | GPL-3.0 build (run as a separate program, not linked) | yes | NOT verified | CPU | Video produced with FFmpeg is not encumbered by the GPL. |
| Vazirmatn font (UI + subtitles) | font | SIL Open Font License 1.1 | yes | OFL.txt shipped with the package | - | Bundled in the repo with its licence text. |
| FLUX.1 [schnell] FP8 (all-in-one checkpoint) | image (fast, 4 steps) | Apache-2.0 | yes | model card licence field + repository read on 2026-11-13 (not audited) | 12 GB (fp8) | The commercially usable FLUX; take it when the work is published. |
| FLUX text encoders + VAE (t5xxl fp8, clip_l, ae) | image (split loaders) | Apache-2.0 (encoder cards; the VAE is an ungated repack) | yes | model card licence field + repository read on 2026-11-13 (not audited) | T5 fp8 about 5 GB while encoding | For the split FLUX loaders and GGUF models. |
| Stable Diffusion XL base 1.0 | image | CreativeML Open RAIL++-M | yes | model card licence field + repository read on 2026-11-13 (not audited) | 7-9 GB | Commercial use allowed with use-based restrictions; the base of SDXL ControlNet / IP-Adapter. |
| RealVisXL V4.0 | photoreal image | CreativeML Open RAIL++-M | yes | model card licence field + repository read on 2026-11-13 (not audited) | about 7 GB | A permissive photoreal SDXL checkpoint. |
| ControlNet Union SDXL (promax) | pose / depth / edges control | Apache-2.0 | yes | model card licence field + repository read on 2026-11-13 (not audited) | about 2.5 GB | Keeps a character's pose and composition across shots. |
| IP-Adapter Plus / Plus-Face (SDXL) + CLIP-ViT-H + ComfyUI_IPAdapter_plus | consistent characters | Apache-2.0 (models); GPL-3.0 (the ComfyUI node) | yes | model card licence field + repository read on 2026-11-13 (not audited) | about 4.3 GB | The node only runs inside ComfyUI; it is not linked into InstAI. |
| PuLID for FLUX + EVA-CLIP + InsightFace antelopev2 **(WARNING: owner-enabled, not for commercial use)** | consistent faces | PuLID Apache-2.0; InsightFace antelopev2 NON-COMMERCIAL | no | model card licence field + repository read on 2026-11-13 (not audited) | FLUX fp8 + about 3 GB | Off by default; its download needs a separate confirmation because of the InsightFace weights. |
| Real-ESRGAN x4plus | upscale | BSD-3-Clause | yes | model card licence field + repository read on 2026-11-13 (not audited) | small | Comfy-Org repack. |
| 4x-UltraSharp **(WARNING: owner-enabled, not for commercial use)** | upscale | CC-BY-NC-SA-4.0 - NON-COMMERCIAL | no | model card licence field + repository read on 2026-11-13 (not audited) | small | Off by default; its download needs a separate confirmation. |
| Wan 2.2 TI2V-5B (fp16) + Wan 2.2 VAE + umT5 encoder | video (text + image to video) | Apache-2.0 | yes | model card licence field + repository read on 2026-11-13 (not audited) | comfortable on 12 GB | The light Wan 2.2; shares the umT5 encoder with the 14B package. |
| LTX-Video 2B 0.9.8 distilled (FP8) | fast video | LTX-Video licence (card says 'other') | unknown | model card licence field + repository read on 2026-11-13 (not audited) | about 4.5 GB + T5 | Read the licence text before commercial use; off by default (needs a separate confirmation). |
| RIFE v4.25 (frame interpolation) | smoother video | MIT + Apache-2.0 | yes | model card licence field + repository read on 2026-11-13 (not audited) | under 1 GB | Needs a ComfyUI with the frame-interpolation nodes. |
| Piper voices fa_IR amir / ganji / ganji_adabi / reza_ibrahim | speech (CPU) | CC0 training data (each voice's MODEL_CARD) | yes | model card licence field + repository read on 2026-11-13 (not audited) | CPU | Read each voice's card before publishing commercially. |
| Remotion 4 (code-to-video: remotion, bundler, renderer, player) **(OWNER DECISION)** | video built with code (titles, kinetic text, explainers) | Remotion License: free for an individual, a for-profit organisation with up to 3 employees, a non-profit, or evaluation; a Company License for larger companies | conditional | LICENSE.md of remotion-dev/remotion read on 2026-11-13 (not legal advice) | CPU | Installed from npm on the owner's PC (scripts/setup_remotion.py); nothing of Remotion is copied into this repository. OWNER: confirm that the organisation using InstAI is within the free tier, otherwise buy the Company License. |
| Node.js 24 LTS (portable zip) | runs Remotion | MIT | yes | nodejs.org (checksum pinned in setup_remotion.py) | CPU | Used from the PC when it is already installed, else the portable zip is unpacked into tools/node (nothing system-wide). |
| Qwen3 / Qwen3.5 (Ollama) | text | Apache-2.0 (per model cards; verify the exact tag) | unknown | NOT verified | 8-9B fit 12 GB | Preferred default for Persian script drafts; measure with the benchmark. |
| Gemma 3 / TranslateGemma (Ollama) | text | Gemma Terms of Use (custom) | conditional | NOT verified | 12B fits | Custom terms with use restrictions; read before commercial use. |
| gpt-oss:20b (Ollama) | text | Apache-2.0 (per brief list) | unknown | NOT verified | 20B offloads to RAM | Slow on 12 GB. |
| Dorna / partai dorna-llama3 (Persian) | text | Llama 3 community licence (derivative) | conditional | NOT verified | 8B Q4 | Persian-specialised; check the licence of the exact build. |

## Optional downloads (offered on the Models page, downloaded only after the owner confirms)

The list lives in `manifests/*.json` (packages with an `offer` block). Before anything is fetched the page shows the name, the size still
to download, the licence (with a link) and why it is better; the API refuses a download without `confirm: true`. Files the ComfyUI InstAI
uses can already see are never downloaded again; downloads resume and every file has a pinned sha256. Quality and speed on the RTX 3060
are NOT measured yet; the anime video candidates are judged in Production lab > Compare on the same stills and seeds as plain Wan 2.2.

| Candidate | For | Size (all files) | Needs | Licence | Commercial use |
|---|---|---|---|---|---|
| Animagine XL 4.0 Opt (anime images) (`animagine`, workflow `sdxl_anime_t2i`) | anime image | 6.9 GB | - | CreativeML Open RAIL++-M (model card read 2026-10-29: commercial use allowed, use-based restrictions) | yes |
| Index-AniSora V3.2 (GGUF Q4_0) (`anisora`, workflow `anisora_v32_i2v_gguf`) | anime video | 18.1 GB | comfy-gguf, umt5_xxl_fp8, wan21_vae, lightx2v_rank64 | Apache-2.0 + extra restrictions for retraining/derivatives (bilibili Index-anisora LICENSE) | unknown |
| AnimeGen I2V by AIdeaLab (GGUF Q4_K_M) (`animegen`, workflow `animegen_i2v_gguf`) | anime video | 19.3 GB | comfy-gguf, umt5_xxl_fp8, wan21_vae, lightx2v_rank64 | Apache-2.0 (card tag commercial-use) | yes |

## Added in 0.8.0 (identity)

| Workflow | Models | Licence | State |
|---|---|---|---|
| `qwen_image_edit_multiref` (up to three character model sheets -> a new picture) | the same four files as `qwen_image_edit_ref` (Qwen-Image-Edit-2509 fp8 20.4 GB, Qwen2.5-VL 7B fp8 9.4 GB, Qwen-Image VAE, Qwen-Image-Edit-2509 Lightning 4-step LoRA bf16): since 0.9.0 they are one offer in `manifests/image.json` (package `qwen_edit`, about 31 GB, pinned commits and sha256 read from the Hugging Face API on 2026-11-13; the old workflows named the text-to-image Lightning LoRA, which is not the editing one - corrected) | Apache-2.0 | graph written from ComfyUI's template documentation, **never run** on a real ComfyUI; needs the model downloads |
