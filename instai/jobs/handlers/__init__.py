"""Importing this package registers every job handler."""
from instai.ops import pcselftest  # noqa: F401 - the automatic self-test of this PC (system.selftest)
from . import bench, downloads, ideas, models_test, phase3, prod, publish, remotion, story, studio, styles  # noqa: F401
