"""Model / tool licence table (single source of truth: shown as badges in Settings and rendered into docs/MODELS.md).

`verified` records WHAT was checked and when. "model card 2026-10-28" means the licence line on the model's public card was read;
the full licence text was NOT audited. Everything else is "brief" (stated by the owner's brief) or unverified.
`commercial`: yes | conditional | no | unknown. `decision`: True when only the owner can decide.
"""
from __future__ import annotations

CHECKED = "model card read on 2026-10-28 (licence line only)"

MODELS: list[dict] = [
    # ---- images
    {"id": "flux-dev", "name": "FLUX.1 [dev] (FP8)", "role": "image", "licence": "FLUX.1 [dev] Non-Commercial License", "commercial": "conditional",
     "verified": CHECKED, "decision": True, "vram": "12 GB (fp8)", "package": "flux",
     "notes": "Weights are non-commercial. The model card says generated outputs may be used commercially 'as described in the licence'; the full text "
              "(gated on Hugging Face) was not readable here. Owner/lawyer must read it. Fallback: Qwen-Image / Z-Image (Apache-2.0), to be benchmarked."},
    {"id": "qwen-image", "name": "Qwen-Image / Qwen-Image-Edit", "role": "image + edit", "licence": "Apache-2.0", "commercial": "yes", "verified": CHECKED,
     "vram": "to measure", "package": None, "notes": "Supported by the installed ComfyUI. Candidate to replace FLUX; also pose/expression editing from references."},
    {"id": "z-image", "name": "Z-Image (Turbo)", "role": "image", "licence": "Apache-2.0", "commercial": "yes", "verified": CHECKED,
     "vram": "to measure", "package": None, "notes": "Candidate image model; fast."},
    {"id": "animagine-xl-4", "name": "Animagine XL 4.0 Opt (SDXL anime)", "role": "anime image", "licence": "CreativeML Open RAIL++-M", "commercial": "yes",
     "verified": "model card read on 2026-10-29 (licence section: commercial use permitted, use-based restrictions)", "vram": "to measure (SDXL)",
     "package": "animagine", "notes": "Optional download offered on the Models page (asks first, 6.9 GB). Workflow sdxl_anime_t2i (core nodes only). "
                                      "Anime keyframes instead of the general FLUX model; also a way around the FLUX dev weights licence question."},
    # ---- video
    {"id": "wan22-i2v", "name": "Wan 2.2 I2V A14B (fp8, high/low noise)", "role": "video", "licence": "Apache-2.0", "commercial": "yes", "verified": CHECKED,
     "vram": "12 GB with fp8 + 8-step LoRA", "package": "wan22",
     "notes": "Card: authors claim no rights over generated content; users remain responsible for lawful use. Planning estimate 8-10 GPU min per 5 s 480p shot - NOT measured."},
    {"id": "anisora", "name": "Index-AniSora V3.2", "role": "anime video", "licence": "Apache-2.0 + additional restrictions (repo LICENSE) when retraining / making derivatives", "commercial": "unknown",
     "verified": "HF card + GitHub LICENSE read on 2026-10-28 (not audited)", "vram": "GGUF Q4_0 ~9 GB per expert", "package": "anisora",
     "notes": "Use of the community GGUF conversion for generation is not retraining, but the extra clauses (legal compliance of outputs, indemnity, downstream binding) must be read by the owner. "
              "Needs the ComfyUI-GGUF custom node. Compared against plain Wan 2.2 on the same stills and seeds in Production lab > Compare. "
              "Optional download on the Models page (asks first; ~18.1 GB + the node; sha256 pinned)."},
    {"id": "animegen", "name": "AnimeGen I2V (AIdeaLab)", "role": "anime video", "licence": "Apache-2.0 (card tag: commercial-use)", "commercial": "yes", "verified": "HF card + LICENSE read on 2026-10-28 (licence line only)",
     "vram": "GGUF Q4_K_M ~9.7 GB per expert", "package": "animegen",
     "notes": "Wan 2.2 I2V A14B fine-tune by AIdeaLab. The card recommends an RTX 4090 for the original weights; the community GGUF needs the ComfyUI-GGUF custom node. Comparison candidate. "
              "Optional download on the Models page (asks first; ~19.3 GB + the node; sha256 pinned)."},
    {"id": "comfy-gguf", "name": "ComfyUI-GGUF custom node + gguf package", "role": "loads GGUF models in ComfyUI", "licence": "Apache-2.0 (node); MIT (gguf)",
     "commercial": "yes", "verified": "GitHub licence field + PyPI classifier read on 2026-10-29", "vram": "-", "package": "comfy-gguf",
     "notes": "Installed only together with an anime GGUF model, after the owner confirms. Pinned commit 6ea2651; ComfyUI must be restarted afterwards."},
    {"id": "wan-anime-lora", "name": "Wan 2.2 + anime style LoRA", "role": "anime video", "licence": "varies per LoRA", "commercial": "unknown", "verified": None,
     "vram": "-", "package": None, "notes": "Only if that specific LoRA's licence allows selling output. Many popular ones do not. No character/IP LoRAs."},
    {"id": "ltx2", "name": "LTX-2", "role": "video", "licence": "requires a not-sanctioned-country representation", "commercial": "no", "verified": "brief",
     "excluded": True, "vram": "-", "package": None, "notes": "EXCLUDED: the owner cannot make that representation from Iran."},
    {"id": "hunyuan15", "name": "HunyuanVideo 1.5", "role": "video", "licence": "territorial / trade-law clauses", "commercial": "no", "verified": "brief",
     "excluded": True, "vram": ">= 14 GB", "package": None, "notes": "EXCLUDED: territorial clauses and needs more VRAM than the RTX 3060."},
    {"id": "wan25", "name": "Wan 2.5 and later", "role": "video", "licence": "API only (no open weights)", "commercial": "unknown", "verified": "brief",
     "excluded": True, "vram": "-", "package": None, "notes": "Not planned: nothing to run locally."},
    # ---- voice / audio
    {"id": "moss-tts", "name": "MOSS-TTS-Realtime 1.7B + Persian LoRA", "role": "speech, voice cloning", "licence": "Apache-2.0", "commercial": "yes",
     "verified": CHECKED, "vram": "to measure", "package": "moss-tts", "notes": "Best Persian narration; needs its own server (GPU)."},
    {"id": "moss-sfx", "name": "MOSS-SoundEffect v2.0", "role": "ambience / SFX", "licence": "Apache-2.0 (per Qasem notes)", "commercial": "unknown", "verified": None,
     "vram": "to measure", "package": "moss-sfx", "notes": "Phase 3."},
    {"id": "acestep", "name": "ACE-Step 1.5 (turbo)", "role": "music", "licence": "MIT", "commercial": "yes", "verified": CHECKED, "vram": "to measure",
     "package": "acestep", "notes": "Phase 3."},
    {"id": "piper", "name": "Piper (engine) + voice fa_IR-gyro-medium", "role": "speech (CPU fallback)", "licence": "engine MIT; each voice has its own licence",
     "commercial": "unknown", "verified": None, "vram": "none (CPU)", "package": "piper",
     "notes": "The voice licence must be checked on its model card before publishing commercially."},
    {"id": "vosk", "name": "Vosk (ASR)", "role": "speech recognition", "licence": "Apache-2.0 (per brief)", "commercial": "yes", "verified": "brief", "vram": "CPU",
     "package": None, "notes": "Used later for subtitle timing checks."},
    {"id": "pocket-tts", "name": "Pocket-TTS (voice kit)", "role": "speech", "licence": "CC-BY-NC-4.0 - NON-COMMERCIAL", "commercial": "no", "verified": "brief",
     "warning": True, "vram": "CPU", "package": None,
     "notes": "AVAILABLE ON REQUEST of the owner, with a visible warning wherever it is chosen and in the QC report. Never selected automatically; "
              "do not use it for content you publish commercially."},
    {"id": "edge-tts", "name": "Edge TTS (unofficial online endpoint)", "role": "speech", "licence": "unofficial endpoint, not for commercial use", "commercial": "no",
     "verified": "brief", "warning": True, "vram": "-", "package": None,
     "notes": "AVAILABLE ON REQUEST of the owner, with a visible warning (needs internet; not a licensed service). Never selected automatically."},
    # ---- tools
    {"id": "rhubarb", "name": "Rhubarb Lip Sync 1.13", "role": "mouth shapes", "licence": "MIT", "commercial": "yes", "verified": "brief", "vram": "CPU",
     "package": "rhubarb", "notes": "Drives puppet-2D mouths. MEASURED (dev PC): English via PocketSphinx 4.3 s for 7.1 s of speech; Persian via the phonetic recogniser 1.3 s for 6.2 s; pauses are masked by loudness because phonetic labels pauses as speech."},
    {"id": "manim", "name": "Manim (Community)", "role": "diagrams for explainers", "licence": "MIT", "commercial": "yes", "verified": "brief", "vram": "CPU",
     "package": None, "notes": "Phase 3 candidate for code-rendered motion graphics (alternative: SVG/Canvas to video)."},
    {"id": "realesrgan", "name": "Real-ESRGAN x4v3", "role": "upscale", "licence": "BSD-3-Clause", "commercial": "yes", "verified": None, "vram": "small",
     "package": None, "notes": "Already used by NMarketing."},
    {"id": "birefnet", "name": "BiRefNet-lite", "role": "background removal (parallax layers)", "licence": "MIT (per repo)", "commercial": "unknown",
     "verified": None, "vram": "small", "package": "birefnet", "notes": "Phase 3."},
    {"id": "insightface", "name": "InsightFace detector weights", "role": "talking-head dependency", "licence": "non-commercial", "commercial": "no", "verified": "brief",
     "excluded": True, "vram": "-", "package": None, "notes": "EXCLUDED: check every dependency of talking-head tools."},
    {"id": "ffmpeg", "name": "FFmpeg 7.1.1 essentials build", "role": "assembly", "licence": "GPL-3.0 build (run as a separate program, not linked)", "commercial": "yes",
     "verified": None, "vram": "CPU", "package": "ffmpeg", "notes": "Video produced with FFmpeg is not encumbered by the GPL."},
    {"id": "vazirmatn", "name": "Vazirmatn font (UI + subtitles)", "role": "font", "licence": "SIL Open Font License 1.1", "commercial": "yes",
     "verified": "OFL.txt shipped with the package", "vram": "-", "package": None, "notes": "Bundled in the repo with its licence text."},
    # ---- curated library (0.8.0): packages of manifests/curated.json; every file pinned to a commit with size + sha256
    {"id": "flux-schnell", "name": "FLUX.1 [schnell] FP8 (all-in-one checkpoint)", "role": "image (fast, 4 steps)", "licence": "Apache-2.0", "commercial": "yes",
     "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "12 GB (fp8)", "package": "flux-schnell", "notes": "The commercially usable FLUX; take it when the work is published."},
    {"id": "flux-parts", "name": "FLUX text encoders + VAE (t5xxl fp8, clip_l, ae)", "role": "image (split loaders)", "licence": "Apache-2.0 (encoder cards; the VAE is an ungated repack)",
     "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "T5 fp8 about 5 GB while encoding", "package": "flux-parts", "notes": "For the split FLUX loaders and GGUF models."},
    {"id": "sdxl-base", "name": "Stable Diffusion XL base 1.0", "role": "image", "licence": "CreativeML Open RAIL++-M", "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)",
     "vram": "7-9 GB", "package": "sdxl-base", "notes": "Commercial use allowed with use-based restrictions; the base of SDXL ControlNet / IP-Adapter."},
    {"id": "sdxl-realvis", "name": "RealVisXL V4.0", "role": "photoreal image", "licence": "CreativeML Open RAIL++-M", "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)",
     "vram": "about 7 GB", "package": "sdxl-realvis", "notes": "A permissive photoreal SDXL checkpoint."},
    {"id": "controlnet-union-sdxl", "name": "ControlNet Union SDXL (promax)", "role": "pose / depth / edges control", "licence": "Apache-2.0", "commercial": "yes",
     "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "about 2.5 GB", "package": "controlnet-union-sdxl", "notes": "Keeps a character's pose and composition across shots."},
    {"id": "ipadapter-sdxl", "name": "IP-Adapter Plus / Plus-Face (SDXL) + CLIP-ViT-H + ComfyUI_IPAdapter_plus", "role": "consistent characters", "licence": "Apache-2.0 (models); GPL-3.0 (the ComfyUI node)",
     "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "about 4.3 GB", "package": "ipadapter-sdxl", "notes": "The node only runs inside ComfyUI; it is not linked into InstAI."},
    {"id": "pulid-flux", "name": "PuLID for FLUX + EVA-CLIP + InsightFace antelopev2", "role": "consistent faces", "licence": "PuLID Apache-2.0; InsightFace antelopev2 NON-COMMERCIAL",
     "commercial": "no", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "warning": True, "vram": "FLUX fp8 + about 3 GB", "package": "pulid-flux",
     "notes": "Off by default; its download needs a separate confirmation because of the InsightFace weights."},
    {"id": "upscale-realesrgan", "name": "Real-ESRGAN x4plus", "role": "upscale", "licence": "BSD-3-Clause", "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "small",
     "package": "upscale-realesrgan", "notes": "Comfy-Org repack."},
    {"id": "upscale-ultrasharp", "name": "4x-UltraSharp", "role": "upscale", "licence": "CC-BY-NC-SA-4.0 - NON-COMMERCIAL", "commercial": "no", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "warning": True,
     "vram": "small", "package": "upscale-ultrasharp", "notes": "Off by default; its download needs a separate confirmation."},
    {"id": "wan22-ti2v-5b", "name": "Wan 2.2 TI2V-5B (fp16) + Wan 2.2 VAE + umT5 encoder", "role": "video (text + image to video)", "licence": "Apache-2.0", "commercial": "yes",
     "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "comfortable on 12 GB", "package": "wan22-ti2v-5b", "notes": "The light Wan 2.2; shares the umT5 encoder with the 14B package."},
    {"id": "ltx-distilled", "name": "LTX-Video 2B 0.9.8 distilled (FP8)", "role": "fast video", "licence": "LTX-Video licence (card says 'other')", "commercial": "unknown", "verified": "model card licence field + repository read on 2026-11-13 (not audited)",
     "vram": "about 4.5 GB + T5", "package": "ltx-distilled", "notes": "Read the licence text before commercial use; off by default (needs a separate confirmation)."},
    {"id": "rife", "name": "RIFE v4.25 (frame interpolation)", "role": "smoother video", "licence": "MIT + Apache-2.0", "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "under 1 GB",
     "package": "rife", "notes": "Needs a ComfyUI with the frame-interpolation nodes."},
    {"id": "piper-fa-voices", "name": "Piper voices fa_IR amir / ganji / ganji_adabi / reza_ibrahim", "role": "speech (CPU)", "licence": "CC0 training data (each voice's MODEL_CARD)",
     "commercial": "yes", "verified": "model card licence field + repository read on 2026-11-13 (not audited)", "vram": "CPU", "package": "piper-fa-voices", "notes": "Read each voice's card before publishing commercially."},
    # ---- software
    {"id": "remotion", "name": "Remotion 4 (code-to-video: remotion, bundler, renderer, player)", "role": "video built with code (titles, kinetic text, explainers)",
     "licence": "Remotion License: free for an individual, a for-profit organisation with up to 3 employees, a non-profit, or evaluation; a Company License for larger companies",
     "commercial": "conditional", "verified": "LICENSE.md of remotion-dev/remotion read on 2026-11-13 (not legal advice)", "decision": True, "vram": "CPU",
     "package": None, "notes": "Installed from npm on the owner's PC (scripts/setup_remotion.py); nothing of Remotion is copied into this repository. OWNER: confirm that the "
                                "organisation using InstAI is within the free tier, otherwise buy the Company License."},
    {"id": "nodejs", "name": "Node.js 24 LTS (portable zip)", "role": "runs Remotion", "licence": "MIT", "commercial": "yes", "verified": "nodejs.org (checksum pinned in setup_remotion.py)", "vram": "CPU",
     "package": None, "notes": "Used from the PC when it is already installed, else the portable zip is unpacked into tools/node (nothing system-wide)."},
    # ---- language models (owner's Ollama)
    {"id": "qwen3", "name": "Qwen3 / Qwen3.5 (Ollama)", "role": "text", "licence": "Apache-2.0 (per model cards; verify the exact tag)", "commercial": "unknown",
     "verified": None, "vram": "8-9B fit 12 GB", "package": None, "notes": "Preferred default for Persian script drafts; measure with the benchmark."},
    {"id": "gemma3", "name": "Gemma 3 / TranslateGemma (Ollama)", "role": "text", "licence": "Gemma Terms of Use (custom)", "commercial": "conditional", "verified": None,
     "vram": "12B fits", "package": None, "notes": "Custom terms with use restrictions; read before commercial use."},
    {"id": "gpt-oss", "name": "gpt-oss:20b (Ollama)", "role": "text", "licence": "Apache-2.0 (per brief list)", "commercial": "unknown", "verified": None,
     "vram": "20B offloads to RAM", "package": None, "notes": "Slow on 12 GB."},
    {"id": "dorna", "name": "Dorna / partai dorna-llama3 (Persian)", "role": "text", "licence": "Llama 3 community licence (derivative)", "commercial": "conditional",
     "verified": None, "vram": "8B Q4", "package": None, "notes": "Persian-specialised; check the licence of the exact build."},
]


def table() -> list[dict]:
    return MODELS


def markdown() -> str:
    lines = ["| Model / tool | Role | Licence | Commercial use | Verified | VRAM | Notes |", "|---|---|---|---|---|---|---|"]
    for m in MODELS:
        flag = " **(EXCLUDED)**" if m.get("excluded") else (" **(OWNER DECISION)**" if m.get("decision") else (" **(WARNING: owner-enabled, not for commercial use)**" if m.get("warning") else ""))
        lines.append(f"| {m['name']}{flag} | {m['role']} | {m['licence']} | {m['commercial']} | {m['verified'] or 'NOT verified'} | {m['vram']} | {m['notes']} |")
    return "\n".join(lines) + "\n"
