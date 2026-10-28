"""Developer tool: writes the ComfyUI API-graph templates of Phase 3 into instai/providers/comfy/templates/.

    python scripts/gen_comfy_templates.py

Node ids are fixed so the bindings in providers/comfy/workflows.py stay valid. Graphs marked UNVERIFIED were written from the node
documentation of ComfyUI (they are NOT copies of the owner's working graphs) and have never run on a real ComfyUI: the first run on the
GPU PC is their test (availability is checked against /object_info before anything is queued).
The Wan graphs are the owner's wan22_i2v template (high/low experts + lightx2v rank64 8-step LoRA) with the first/last-frame node or GGUF loaders.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "instai" / "providers" / "comfy" / "templates"
NEG_WAN = "flicker, jitter, sudden camera shake, morphing, unstable identity, blurry, low quality, deformed, extra limbs, subtitles, watermark, text artifacts"
NEG_IMG = "blurry, low resolution, distorted, deformed, bad anatomy, watermark, logo, unreadable text"
LORA = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"


def wan_graph(*, flf: bool, gguf: tuple[str, str] | None) -> dict:
    hi = "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
    lo = "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
    loader = lambda name: ({"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": name}} if gguf else
                           {"class_type": "UNETLoader", "inputs": {"unet_name": name, "weight_dtype": "default"}})
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "@input:start.png"}},
        "2": loader(gguf[0] if gguf else hi),
        "3": loader(gguf[1] if gguf else lo),
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 8.0}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["3", 0], "shift": 8.0}},
        "6": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "8": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["4", 0], "lora_name": LORA, "strength_model": 3.0}},
        "9": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["5", 0], "lora_name": LORA, "strength_model": 1.5}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["6", 0], "text": "placeholder prompt"}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["6", 0], "text": NEG_WAN}},
        "12": {"class_type": "WanFirstLastFrameToVideo" if flf else "WanImageToVideo",
               "inputs": {"positive": ["10", 0], "negative": ["11", 0], "vae": ["7", 0], "start_image": ["1", 0], "width": 480, "height": 832, "length": 81,
                          "batch_size": 1}},
        "13": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["8", 0], "positive": ["12", 0], "negative": ["12", 1], "latent_image": ["12", 2],
                                                            "add_noise": "enable", "noise_seed": 1, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                                                            "start_at_step": 0, "end_at_step": 4, "return_with_leftover_noise": "enable"}},
        "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["9", 0], "positive": ["12", 0], "negative": ["12", 1], "latent_image": ["13", 0],
                                                            "add_noise": "disable", "noise_seed": 0, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                                                            "start_at_step": 4, "end_at_step": 10000, "return_with_leftover_noise": "disable"}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["7", 0]}},
        "16": {"class_type": "CreateVideo", "inputs": {"images": ["15", 0], "fps": 16.0}},
        "17": {"class_type": "SaveVideo", "inputs": {"video": ["16", 0], "filename_prefix": "InstAI/Videos", "format": "auto", "codec": "auto"}},
    }
    if flf:
        g["18"] = {"class_type": "LoadImage", "inputs": {"image": "@input:end.png"}}
        g["12"]["inputs"]["end_image"] = ["18", 0]
    return g


def flux_img2img() -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "FLUX.1 [dev] FP8.safetensors"}},
        "2": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["8", 0], "negative": ["3", 0], "latent_image": ["11", 0], "seed": 1, "steps": 24,
                                                   "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 0.62}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEG_IMG}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "placeholder prompt"}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["2", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "InstAI/Keyframes"}},
        "8": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["4", 0], "guidance": 3.5}},
        "9": {"class_type": "LoadImage", "inputs": {"image": "@input:ref.png"}},
        "10": {"class_type": "ImageScale", "inputs": {"image": ["9", 0], "upscale_method": "lanczos", "width": 832, "height": 1472, "crop": "center"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
    }


def flux_lora() -> dict:
    g = json.loads((OUT / "flux_dev_fp8_t2i@1.json").read_text(encoding="utf-8"))
    g["9"] = {"class_type": "LoraLoader", "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": "character.safetensors", "strength_model": 0.9, "strength_clip": 0.9}}
    g["2"]["inputs"]["model"] = ["9", 0]
    g["3"]["inputs"]["clip"] = ["9", 1]
    g["4"]["inputs"]["clip"] = ["9", 1]
    return g


def qwen_edit() -> dict:
    """UNVERIFIED: Qwen-Image-Edit-2509 reference edit (4-step Lightning LoRA), after ComfyUI's own template."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2509_fp8_e4m3fn.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "Qwen-Image-Lightning-4steps-V1.0.safetensors", "strength_model": 1.0}},
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["4", 0], "shift": 3.0}},
        "6": {"class_type": "CFGNorm", "inputs": {"model": ["5", 0], "strength": 1.0}},
        "7": {"class_type": "LoadImage", "inputs": {"image": "@input:ref.png"}},
        "8": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["7", 0], "upscale_method": "lanczos", "megapixels": 1.0}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": "placeholder prompt", "vae": ["3", 0], "image1": ["8", 0]}},
        "10": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": "", "vae": ["3", 0], "image1": ["8", 0]}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["3", 0]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["6", 0], "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["11", 0], "seed": 1, "steps": 4,
                                                    "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": "InstAI/QwenEdit"}},
    }


def train_lora() -> dict:
    """UNVERIFIED: ComfyUI's training nodes (LoadImageTextSetFromFolderNode -> VAEEncode -> TrainLoraNode -> SaveLoRANode). The dataset folder
    (images + same-name .txt captions) is copied into ComfyUI/input/<folder> by the worker before the graph runs."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "FLUX.1 [dev] FP8.safetensors"}},
        "2": {"class_type": "LoadImageTextSetFromFolderNode", "inputs": {"folder": "instai_lora", "clip": ["1", 1], "resize_method": "Stretch", "width": 512, "height": 512}},
        "3": {"class_type": "VAEEncode", "inputs": {"pixels": ["2", 0], "vae": ["1", 2]}},
        "4": {"class_type": "TrainLoraNode", "inputs": {"model": ["1", 0], "latents": ["3", 0], "positive": ["2", 1], "batch_size": 1, "grad_accumulation_steps": 1,
                                                        "steps": 300, "learning_rate": 0.0005, "rank": 16, "optimizer": "AdamW", "loss_function": "MSE", "seed": 1,
                                                        "training_dtype": "bf16", "lora_dtype": "bf16", "algorithm": "lora", "gradient_checkpointing": True,
                                                        "existing_lora": "[None]"}},
        "5": {"class_type": "SaveLoRANode", "inputs": {"lora": ["4", 1], "prefix": "loras/instai_character", "steps": ["4", 3]}},
    }


def write(name: str, graph: dict) -> None:
    (OUT / f"{name}@1.json").write_text(json.dumps(graph, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", name)


if __name__ == "__main__":
    write("wan22_flf_a14b_fp8", wan_graph(flf=True, gguf=None))
    write("anisora_v32_i2v_gguf", wan_graph(flf=False, gguf=("Index-Anisora-V3.2-High-Q4_0.gguf", "Index-Anisora-V3.2-Low-Q4_0.gguf")))
    write("animegen_i2v_gguf", wan_graph(flf=False, gguf=("I2V_high_noise_Q4_K_M.gguf", "I2V_low_noise_Q4_K_M.gguf")))
    write("flux_dev_fp8_img2img", flux_img2img())
    write("flux_dev_fp8_t2i_lora", flux_lora())
    write("qwen_image_edit_ref", qwen_edit())
    write("train_lora_flux", train_lora())
