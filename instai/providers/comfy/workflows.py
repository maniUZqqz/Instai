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


def get_workflow(id_: str) -> WorkflowSpec:
    try:
        return WORKFLOWS[id_]
    except KeyError:
        raise ProviderError(f"unknown workflow {id_}", retryable=False) from None


def _loader_options(object_info: dict, node: str, key: str) -> list[str] | None:
    try:
        opts = object_info[node]["input"]["required"][key][0]
        return list(opts) if isinstance(opts, list) else None
    except (KeyError, IndexError, TypeError):
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
