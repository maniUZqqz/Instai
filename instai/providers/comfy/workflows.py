"""Versioned ComfyUI workflow templates.

Each workflow declares its own input schema, hardware needs, licence and expected time; inputs are validated before the
graph is built. `workflow_availability()` tells which workflows can run on the ComfyUI that is up right now (nodes AND
model files), so nothing is assumed. Graph JSON adapted from Qasem processing-server/upmarket_comfyui_flask/workflows.
"""
from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from instai.agents.jsonschema_lite import repair, validate
from instai.providers.base import ProviderError

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class WorkflowSpec:
    id: str
    version: int
    kind: str                       # image | video
    title: str
    input_schema: dict
    bindings: dict[str, list[tuple[str, str]]]          # input name -> [(node id, input key)]
    required_nodes: list[str]
    required_models: list[tuple[str, str, str]]         # (loader node class, input key, file name)
    vram_gb: float
    licence: str
    licence_status: str             # verified | unverified
    expected_seconds: float         # planning estimate; replaced by measured values (see BENCHMARKS.md)
    estimate_source: str = "brief"
    notes: str = ""
    output_kind: str = "images"
    defaults: dict[str, Any] = field(default_factory=dict)

    @property
    def template_file(self) -> Path:
        return TEMPLATE_DIR / f"{self.id}@{self.version}.json"

    def describe(self) -> dict:
        return {"id": self.id, "version": self.version, "kind": self.kind, "title": self.title, "vram_gb": self.vram_gb,
                "licence": self.licence, "licence_status": self.licence_status, "expected_seconds": self.expected_seconds,
                "estimate_source": self.estimate_source, "required_nodes": self.required_nodes, "notes": self.notes,
                "input_schema": self.input_schema}

    def validate_inputs(self, inputs: dict) -> dict:
        data = repair({**self.defaults, **inputs}, self.input_schema)
        errs = validate(data, self.input_schema)
        if errs:
            raise ProviderError("Invalid workflow input: " + "; ".join(errs), retryable=False, code="validation_error")
        return data

    def build(self, inputs: dict) -> dict:
        """Validated inputs -> a ready-to-queue API graph (deep copy of the template with bindings applied)."""
        data = self.validate_inputs(inputs)
        graph = copy.deepcopy(json.loads(self.template_file.read_text(encoding="utf-8")))
        if data.get("seed") in (None, -1):
            data["seed"] = random.randint(1, 2**31 - 1)
        for name, targets in self.bindings.items():
            if name in data and data[name] is not None:
                for node_id, key in targets:
                    graph[node_id]["inputs"][key] = data[name]
        self._check_graph(graph)
        return graph

    @staticmethod
    def _check_graph(graph: dict) -> None:
        for nid, node in graph.items():
            if "class_type" not in node:
                raise ProviderError(f"node {nid} has no class_type", retryable=False)
            for v in node.get("inputs", {}).values():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) not in graph:
                    raise ProviderError(f"node {nid} links to missing node {v[0]}", retryable=False)

    def provenance(self, inputs: dict) -> dict:
        d = self.validate_inputs(inputs)
        return {"workflow": self.id, "workflow_version": self.version, "seed": d.get("seed"), "prompt": d.get("prompt"),
                "width": d.get("width"), "height": d.get("height"), "model": [m[2] for m in self.required_models][:2]}


_IMG_SCHEMA = {
    "type": "object", "required": ["prompt"],
    "properties": {
        "prompt": {"type": "string", "minLength": 1},
        "negative_prompt": {"type": "string"},
        "width": {"type": "integer", "minimum": 256, "maximum": 2048},
        "height": {"type": "integer", "minimum": 256, "maximum": 2048},
        "seed": {"type": ["integer", "null"]},
        "steps": {"type": "integer", "minimum": 1, "maximum": 60},
        "checkpoint": {"type": "string", "minLength": 1},
        "filename_prefix": {"type": "string"},
    },
}

_VID_SCHEMA = {
    "type": "object", "required": ["prompt", "image"],
    "properties": {
        "prompt": {"type": "string", "minLength": 1},
        "negative_prompt": {"type": "string"},
        "image": {"type": "string", "minLength": 1},
        "width": {"type": "integer", "minimum": 256, "maximum": 1280},
        "height": {"type": "integer", "minimum": 256, "maximum": 1280},
        "length": {"type": "integer", "minimum": 5, "maximum": 121},
        "fps": {"type": "number", "minimum": 8, "maximum": 30},
        "seed": {"type": ["integer", "null"]},
        "filename_prefix": {"type": "string"},
    },
}

WORKFLOWS: dict[str, WorkflowSpec] = {
    "flux_dev_fp8_t2i": WorkflowSpec(
        id="flux_dev_fp8_t2i", version=1, kind="image", title="FLUX.1 [dev] FP8 - text to image (9:16)",
        input_schema=_IMG_SCHEMA,
        defaults={"width": 832, "height": 1472, "steps": 24, "seed": None, "negative_prompt": "", "checkpoint": "FLUX.1 [dev] FP8.safetensors"},
        bindings={"prompt": [("4", "text")], "negative_prompt": [("3", "text")], "width": [("5", "width")], "height": [("5", "height")],
                  "seed": [("2", "seed")], "steps": [("2", "steps")], "checkpoint": [("1", "ckpt_name")],
                  "filename_prefix": [("7", "filename_prefix")]},
        required_nodes=["CheckpointLoaderSimple", "KSampler", "CLIPTextEncode", "EmptyLatentImage", "VAEDecode", "SaveImage", "FluxGuidance"],
        required_models=[("CheckpointLoaderSimple", "ckpt_name", "FLUX.1 [dev] FP8.safetensors")],
        vram_gb=12, licence="FLUX.1 [dev] Non-Commercial License (weights); output use: see docs/MODELS.md", licence_status="unverified",
        expected_seconds=60, notes="Graph from the owner's NMarketing node. If the licence is not acceptable, test Qwen-Image / Z-Image (Apache-2.0) "
                                   "- add a template here and compare with the same seed."),
    "wan22_i2v_a14b_fp8": WorkflowSpec(
        id="wan22_i2v_a14b_fp8", version=1, kind="video", title="Wan 2.2 I2V A14B fp8 + lightx2v 8-step (480p, <=81 frames)",
        input_schema=_VID_SCHEMA, output_kind="video",
        defaults={"width": 480, "height": 832, "length": 81, "fps": 16.0, "seed": None, "negative_prompt": ""},
        bindings={"prompt": [("10", "text")], "negative_prompt": [("11", "text")], "image": [("1", "image")],
                  "width": [("12", "width")], "height": [("12", "height")], "length": [("12", "length")],
                  "fps": [("16", "fps")], "seed": [("13", "noise_seed")], "filename_prefix": [("17", "filename_prefix")]},
        required_nodes=["UNETLoader", "ModelSamplingSD3", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly", "WanImageToVideo",
                        "KSamplerAdvanced", "VAEDecode", "CreateVideo", "SaveVideo", "LoadImage"],
        required_models=[("UNETLoader", "unet_name", "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"),
                         ("UNETLoader", "unet_name", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"),
                         ("CLIPLoader", "clip_name", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
                         ("VAELoader", "vae_name", "wan_2.1_vae.safetensors"),
                         ("LoraLoaderModelOnly", "lora_name", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors")],
        vram_gb=12, licence="Apache-2.0 (Wan 2.2, umT5, VAE, lightx2v) - per Qasem manifest notes; re-verify", licence_status="unverified",
        expected_seconds=540, notes="Planning estimate from the brief: 8-10 min per 5 s shot on RTX 3060 12 GB. Measure with the benchmark."),
}


# ------------------------------------------------------------------ Phase 3: hero shots, references, anime candidates, LoRA

_VID_FLF_SCHEMA = {**_VID_SCHEMA, "required": ["prompt", "image", "image_end"],
                   "properties": {**_VID_SCHEMA["properties"], "image_end": {"type": "string", "minLength": 1}}}
_REF_SCHEMA = {
    "type": "object", "required": ["prompt", "image"],
    "properties": {
        "prompt": {"type": "string", "minLength": 1}, "negative_prompt": {"type": "string"}, "image": {"type": "string", "minLength": 1},
        "width": {"type": "integer", "minimum": 256, "maximum": 2048}, "height": {"type": "integer", "minimum": 256, "maximum": 2048},
        "seed": {"type": ["integer", "null"]}, "steps": {"type": "integer", "minimum": 1, "maximum": 60},
        "denoise": {"type": "number", "minimum": 0.2, "maximum": 1.0}, "checkpoint": {"type": "string", "minLength": 1},
        "filename_prefix": {"type": "string"},
    },
}
_WAN_BINDINGS = {"prompt": [("10", "text")], "negative_prompt": [("11", "text")], "image": [("1", "image")], "width": [("12", "width")],
                 "height": [("12", "height")], "length": [("12", "length")], "fps": [("16", "fps")], "seed": [("13", "noise_seed")],
                 "filename_prefix": [("17", "filename_prefix")]}
_WAN_COMMON_MODELS = [("CLIPLoader", "clip_name", "umt5_xxl_fp8_e4m3fn_scaled.safetensors"), ("VAELoader", "vae_name", "wan_2.1_vae.safetensors"),
                      ("LoraLoaderModelOnly", "lora_name", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors")]
_WAN_NODES = ["ModelSamplingSD3", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly", "KSamplerAdvanced", "VAEDecode", "CreateVideo", "SaveVideo", "LoadImage"]
_WAN_DEFAULTS = {"width": 480, "height": 832, "length": 81, "fps": 16.0, "seed": None, "negative_prompt": ""}

WORKFLOWS.update({
    "wan22_flf_a14b_fp8": WorkflowSpec(
        id="wan22_flf_a14b_fp8", version=1, kind="video", title="Wan 2.2 first/last frame (A14B fp8 + lightx2v 8-step): transitions and retakes",
        input_schema=_VID_FLF_SCHEMA, output_kind="video", defaults=_WAN_DEFAULTS,
        bindings={**_WAN_BINDINGS, "image_end": [("18", "image")]},
        required_nodes=["UNETLoader", "WanFirstLastFrameToVideo", *_WAN_NODES],
        required_models=[("UNETLoader", "unet_name", "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"),
                         ("UNETLoader", "unet_name", "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"), *_WAN_COMMON_MODELS],
        vram_gb=12, licence="Apache-2.0 (Wan 2.2) - per Qasem manifest notes; re-verify", licence_status="unverified", expected_seconds=480,
        notes="Same models as the I2V workflow, with ComfyUI's WanFirstLastFrameToVideo node (as the NMarketing regen tool). Estimate only."),
    "anisora_v32_i2v_gguf": WorkflowSpec(
        id="anisora_v32_i2v_gguf", version=1, kind="video", title="Index-AniSora V3.2 (GGUF Q4_0 high/low) - anime I2V candidate",
        input_schema=_VID_SCHEMA, output_kind="video", defaults=_WAN_DEFAULTS, bindings=_WAN_BINDINGS,
        required_nodes=["UnetLoaderGGUF", *_WAN_NODES],
        required_models=[("UnetLoaderGGUF", "unet_name", "Index-Anisora-V3.2-High-Q4_0.gguf"),
                         ("UnetLoaderGGUF", "unet_name", "Index-Anisora-V3.2-Low-Q4_0.gguf"), *_WAN_COMMON_MODELS],
        vram_gb=12, licence="Apache-2.0 + extra restrictions for retraining/derivatives (bilibili/Index-anisora LICENSE); community GGUF conversion",
        licence_status="unverified", expected_seconds=540,
        notes="Needs the ComfyUI-GGUF custom node. Same sampler and lightx2v LoRA as plain Wan so the comparison is like for like. UNVERIFIED graph: never run on a real ComfyUI."),
    "animegen_i2v_gguf": WorkflowSpec(
        id="animegen_i2v_gguf", version=1, kind="video", title="AnimeGen I2V (AIdeaLab, GGUF Q4_K_M high/low) - anime I2V candidate",
        input_schema=_VID_SCHEMA, output_kind="video", defaults=_WAN_DEFAULTS, bindings=_WAN_BINDINGS,
        required_nodes=["UnetLoaderGGUF", *_WAN_NODES],
        required_models=[("UnetLoaderGGUF", "unet_name", "I2V_high_noise_Q4_K_M.gguf"), ("UnetLoaderGGUF", "unet_name", "I2V_low_noise_Q4_K_M.gguf"),
                         *_WAN_COMMON_MODELS],
        vram_gb=12, licence="Apache-2.0 (AIdeaLab; card tag commercial-use; Wan 2.2 base); community GGUF conversion", licence_status="unverified",
        expected_seconds=540, notes="Needs the ComfyUI-GGUF custom node. The model card recommends an RTX 4090 for the original weights; Q4_K_M is ~9.7 GB per expert. UNVERIFIED graph."),
    "flux_dev_fp8_img2img": WorkflowSpec(
        id="flux_dev_fp8_img2img", version=1, kind="image", title="FLUX.1 [dev] FP8 - keyframe from the character sheet (img2img, reference conditioning)",
        input_schema=_REF_SCHEMA,
        defaults={"width": 832, "height": 1472, "steps": 24, "seed": None, "negative_prompt": "", "denoise": 0.62, "checkpoint": "FLUX.1 [dev] FP8.safetensors"},
        bindings={"prompt": [("4", "text")], "negative_prompt": [("3", "text")], "image": [("9", "image")], "width": [("10", "width")], "height": [("10", "height")],
                  "seed": [("2", "seed")], "steps": [("2", "steps")], "denoise": [("2", "denoise")], "checkpoint": [("1", "ckpt_name")],
                  "filename_prefix": [("7", "filename_prefix")]},
        required_nodes=["CheckpointLoaderSimple", "KSampler", "CLIPTextEncode", "FluxGuidance", "LoadImage", "ImageScale", "VAEEncode", "VAEDecode", "SaveImage"],
        required_models=[("CheckpointLoaderSimple", "ckpt_name", "FLUX.1 [dev] FP8.safetensors")], vram_gb=12,
        licence="FLUX.1 [dev] Non-Commercial License (weights); output use: see docs/MODELS.md", licence_status="unverified", expected_seconds=70,
        notes="Core nodes only. The sheet is encoded and partly re-noised (denoise ~0.6) so the new keyframe keeps the character's look. Mid-confidence graph (standard img2img)."),
    "qwen_image_edit_ref": WorkflowSpec(
        id="qwen_image_edit_ref", version=1, kind="image", title="Qwen-Image-Edit 2509 (4-step Lightning) - keyframe edited from the character sheet",
        input_schema={**_REF_SCHEMA, "required": ["prompt", "image"]},
        defaults={"seed": None, "steps": 4, "denoise": 1.0},
        bindings={"prompt": [("9", "prompt")], "image": [("7", "image")], "seed": [("12", "seed")], "steps": [("12", "steps")], "filename_prefix": [("14", "filename_prefix")]},
        required_nodes=["UNETLoader", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly", "ModelSamplingAuraFlow", "CFGNorm", "TextEncodeQwenImageEditPlus",
                        "ImageScaleToTotalPixels", "VAEEncode", "KSampler", "VAEDecode", "SaveImage", "LoadImage"],
        required_models=[("UNETLoader", "unet_name", "qwen_image_edit_2509_fp8_e4m3fn.safetensors"), ("CLIPLoader", "clip_name", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
                         ("VAELoader", "vae_name", "qwen_image_vae.safetensors"), ("LoraLoaderModelOnly", "lora_name", "Qwen-Image-Lightning-4steps-V1.0.safetensors")],
        vram_gb=12, licence="Apache-2.0 (Qwen-Image-Edit)", licence_status="unverified", expected_seconds=60,
        notes="UNVERIFIED graph written from ComfyUI's template documentation; the owner's ComfyUI has the Qwen-Image-Edit nodes but the model files must be downloaded."),
    "flux_dev_fp8_t2i_lora": WorkflowSpec(
        id="flux_dev_fp8_t2i_lora", version=1, kind="image", title="FLUX.1 [dev] FP8 + a character LoRA (text to image)",
        input_schema={**_IMG_SCHEMA, "properties": {**_IMG_SCHEMA["properties"], "lora_name": {"type": "string", "minLength": 1},
                                                    "lora_strength": {"type": "number", "minimum": 0.0, "maximum": 2.0}}},
        defaults={"width": 832, "height": 1472, "steps": 24, "seed": None, "negative_prompt": "", "checkpoint": "FLUX.1 [dev] FP8.safetensors", "lora_strength": 0.9},
        bindings={"prompt": [("4", "text")], "negative_prompt": [("3", "text")], "width": [("5", "width")], "height": [("5", "height")], "seed": [("2", "seed")],
                  "steps": [("2", "steps")], "checkpoint": [("1", "ckpt_name")], "filename_prefix": [("7", "filename_prefix")],
                  "lora_name": [("9", "lora_name")], "lora_strength": [("9", "strength_model"), ("9", "strength_clip")]},
        required_nodes=["CheckpointLoaderSimple", "LoraLoader", "KSampler", "CLIPTextEncode", "EmptyLatentImage", "VAEDecode", "SaveImage", "FluxGuidance"],
        required_models=[("CheckpointLoaderSimple", "ckpt_name", "FLUX.1 [dev] FP8.safetensors")], vram_gb=12,
        licence="FLUX.1 [dev] Non-Commercial License (weights)", licence_status="unverified", expected_seconds=65,
        notes="The LoRA file name is chosen at run time (a trained character LoRA); it is not part of availability."),
    "train_lora_flux": WorkflowSpec(
        id="train_lora_flux", version=1, kind="train", title="Train a character LoRA with ComfyUI's TrainLoraNode (UNVERIFIED, may not fit 12 GB)",
        input_schema={"type": "object", "required": ["folder"], "properties": {
            "folder": {"type": "string", "minLength": 1}, "steps": {"type": "integer", "minimum": 10, "maximum": 4000}, "rank": {"type": "integer", "minimum": 1, "maximum": 128},
            "learning_rate": {"type": "number", "minimum": 0.00001, "maximum": 0.01}, "seed": {"type": ["integer", "null"]}, "width": {"type": "integer", "minimum": 256, "maximum": 1536},
            "height": {"type": "integer", "minimum": 256, "maximum": 1536}, "checkpoint": {"type": "string", "minLength": 1}, "filename_prefix": {"type": "string"}}},
        defaults={"steps": 300, "rank": 16, "learning_rate": 0.0005, "seed": None, "width": 512, "height": 512, "checkpoint": "FLUX.1 [dev] FP8.safetensors"},
        bindings={"folder": [("2", "folder")], "steps": [("4", "steps")], "rank": [("4", "rank")], "learning_rate": [("4", "learning_rate")], "seed": [("4", "seed")],
                  "width": [("2", "width")], "height": [("2", "height")], "checkpoint": [("1", "ckpt_name")], "filename_prefix": [("5", "prefix")]},
        required_nodes=["CheckpointLoaderSimple", "LoadImageTextSetFromFolderNode", "VAEEncode", "TrainLoraNode", "SaveLoRANode"],
        required_models=[("CheckpointLoaderSimple", "ckpt_name", "FLUX.1 [dev] FP8.safetensors")], vram_gb=12,
        licence="FLUX.1 [dev] Non-Commercial License (weights)", licence_status="unverified", expected_seconds=1800,
        notes="UNVERIFIED: written from ComfyUI's training-node documentation and never run. Training a 12B model on a 12 GB card may run out of memory; the job reports that "
              "plainly and the before/after numbers decide whether a LoRA helps at all."),
})


def get_workflow(id_: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[id_]
    except KeyError:
        raise ProviderError(f"unknown workflow {id_}", retryable=False) from None


def _loader_options(object_info: dict, node: str, key: str) -> list[str] | None:
    """Model file names a loader node offers. Handles both /object_info shapes: [[names...], {...}] (classic) and
    ["COMBO", {"options": [names...]}] (newer nodes)."""
    try:
        spec = object_info[node]["input"]["required"][key]
        first = spec[0]
        if isinstance(first, list):
            return list(first)
        if first == "COMBO" and isinstance(spec[1], dict) and isinstance(spec[1].get("options"), list):
            return list(spec[1]["options"])
    except (KeyError, IndexError, TypeError):
        pass
    return None


def workflow_availability(nodes_or_info, ) -> list[dict]:
    """For each workflow: can it run on this ComfyUI? `nodes_or_info` is /object_info (dict) or just the node-name list."""
    info = nodes_or_info if isinstance(nodes_or_info, dict) else None
    names = set(info.keys()) if info is not None else set(nodes_or_info or [])
    out = []
    for w in WORKFLOWS.values():
        missing_nodes = [n for n in w.required_nodes if n not in names]
        missing_models: list[str] = []
        models_checked = False
        if info is not None:
            for node, key, fname in w.required_models:
                opts = _loader_options(info, node, key)
                if opts is not None:
                    models_checked = True
                    if fname not in opts:
                        missing_models.append(fname)
        out.append({"id": w.id, "title": w.title, "kind": w.kind, "available": not missing_nodes and not missing_models,
                    "missing_nodes": missing_nodes, "missing_models": missing_models, "models_checked": models_checked,
                    "vram_gb": w.vram_gb, "licence": w.licence, "licence_status": w.licence_status})
    return out
