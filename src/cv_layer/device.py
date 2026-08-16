"""Deployment-target resolution.

Keeps hardware and artifact assumptions out of the detector classes so the same
code runs on a CUDA laptop, a CPU-only mini PC, and a Jetson Orin. This is also
the seam where a TensorRT backend selection would land later.

This module is imported under two distinct names in production: bare
``cv_layer.device`` (e.g. `src/web_layer/pipeline_runner.py`, which relies on
`server.py` inserting `src/` onto `sys.path`) and fully-qualified
``src.cv_layer.device`` (e.g. `src/cv_layer/detector/yolo_detector.py`).
Python treats these as two separate modules with two separate module-level
namespaces. Keep this module stateless: anything stored at module level here
would silently exist twice, out of sync.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch

logger = logging.getLogger(__name__)

# Values that mean "figure it out for me".
_AUTO = {None, "", "auto"}


def resolve_device(preference: str | None = None) -> str:
    """Return a concrete torch device string.

    Parameters:
        preference: ``None`` / ``""`` / ``"auto"`` to auto-detect, or an explicit
            device string such as ``"cpu"``, ``"cuda"``, or ``"cuda:1"``.

    Returns:
        ``"cuda"`` when CUDA is available and wanted, otherwise ``"cpu"``.

    An explicit CUDA request on a machine without CUDA logs a WARNING and
    degrades to CPU rather than raising: a slow pipeline is more useful than a
    dead one, and the warning keeps the degradation visible.

    Normalization (``.strip().lower()``) happens here, not at the caller, so
    every caller is covered uniformly. Previously only the SIMON_DEVICE env
    path normalized (inline inside `os.getenv(...)` in server.py), so
    `--device CUDA` on the CLI reached here unnormalized: `.startswith("cuda")`
    (which checks the lowercase form) missed it, the warn-and-degrade branch
    below was skipped, and `"CUDA"` went straight to `model.to()` -- an opaque
    torch error on a CPU-only box instead of this function's intended warning.
    """
    if preference is not None:
        preference = preference.strip().lower()

    if preference in _AUTO:
        return "cuda" if torch.cuda.is_available() else "cpu"

    if preference.startswith("cuda") and not torch.cuda.is_available():
        logger.warning(
            "Device %r requested but CUDA is unavailable on this machine; "
            "falling back to cpu. Inference will be significantly slower.",
            preference,
        )
        return "cpu"

    return preference


def resolve_model_path(path: str | Path) -> Path:
    """Return ``path`` as a ``Path``, raising if the weights are not present.

    Ultralytics silently *downloads* stock weights when handed a path that does
    not exist. Because ``models/`` is a bind mount in production, a typo'd or
    missing mount would otherwise look like it worked while quietly ignoring the
    intended weights — and on the Jetson would ignore a ``.engine`` entirely.
    """
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Model weights not found at {resolved}. If running in a container, "
            f"check that the models/ volume is mounted; without this check "
            f"Ultralytics would silently download stock weights instead."
        )
    return resolved
