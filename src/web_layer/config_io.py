from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Write ``payload`` to ``path`` atomically with a rotating ``.bak``.

    Sequence:
      1. Ensure parent directory exists.
      2. If ``path`` exists, copy it to ``path.bak`` (preserving metadata).
      3. Write JSON to ``path.tmp`` + ``flush`` + ``fsync``.
      4. ``os.replace`` swaps ``.tmp`` over the target. Atomic on POSIX *and*
         Windows for same-volume replacements, so a crash between steps never
         leaves a half-written config file readable by ``SpatialEngine`` or
         ``RuleEvaluator``.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())

    os.replace(tmp, path)
