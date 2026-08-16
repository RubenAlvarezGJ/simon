"""Deployment-target resolution.

Keeps hardware and artifact assumptions out of the detector classes so the same
code runs on a CUDA laptop, a CPU-only mini PC, and a Jetson Orin.

**Keep this module stateless.** It is imported under two names —
``cv_layer.device`` and ``src.cv_layer.device`` — which Python treats as
separate modules, so anything held at module level would exist twice and drift.
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

    Input is normalized here rather than at the call sites, so ``"CUDA"``,
    ``" cuda "`` and ``"Auto"`` behave like their lowercase forms whichever
    caller supplies them.
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
