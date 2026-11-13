"""Stick-figure kit: original characters drawn by code (identical in every pose, scene and clip), poses, backgrounds, stills and clips."""
from . import parts, poses, scenes, spec  # noqa: F401
from .compose import SIZES, compose_still, model_sheet, render_clip, size_for  # noqa: F401
