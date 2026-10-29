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
