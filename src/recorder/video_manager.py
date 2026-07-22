"""Background footage-retention manager.

Periodically prunes recorded footage so the ``footage/`` directory does not grow
without bound. Two independent policies run on every sweep:

  1. **TTL expiration** - delete any segment older than ``ttl_seconds``.
  2. **Directory size budget** - while the total footage size exceeds
     ``max_bytes``, delete the oldest segment until back under budget.

The manager runs on its own daemon thread and is
wired into the FastAPI lifespan next to ``VideoRecorder``. It never touches
ffmpeg or the CV pipeline - it only deletes files on disk.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionConfig:
    """Configuration for the footage-retention sweep.

    Args:
        footage_path:           Directory holding recorded ``cam_*.mkv`` segments.
        max_bytes:              Total footage-size budget in bytes; when the sum of
                                segment sizes exceeds this, oldest files are deleted
                                until back under budget. ``None`` disables the budget.
        ttl_seconds:            Maximum segment age (seconds, by mtime); older files
                                are deleted. ``None`` disables TTL expiration.
        sweep_interval_seconds: Delay between sweeps. Because the budget is only
                                enforced at sweep time, the directory can
                                transiently exceed ``max_bytes`` by roughly one
                                segment per sweep interval elapsed. Keep this at
                                or below the recorder's segment duration (60s) so
                                the overshoot stays within a single segment.
        glob_pattern:           Glob used to select footage files (matches the
                                recorder's ``cam_%Y-%m-%d_%H-%M-%S.mkv`` naming).
    """

    footage_path: str | Path = "footage"
    max_bytes: Optional[int] = 10 * 1024 ** 3
    ttl_seconds: Optional[float] = 24 * 3600
    sweep_interval_seconds: float = 60.0
    glob_pattern: str = "cam_*.mkv"


class VideoManager:
    """Owns the periodic footage-retention sweep on a background thread.

    Usage (typical):
        manager = VideoManager(RetentionConfig(footage_path="footage"))
        manager.start()
        ...
        manager.stop()

    Usage (context manager):
        with VideoManager(config) as manager:
            ...
    """

    def __init__(self, config: RetentionConfig = RetentionConfig()) -> None:
        self._config = config
        self._footage_path = Path(config.footage_path)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._fatal_error: Optional[BaseException] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("VideoManager is already running.")
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="VideoManager", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("VideoManager: worker did not exit within %.1fs", timeout)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def fatal_error(self) -> Optional[BaseException]:
        return self._fatal_error

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._loop()
        except BaseException as exc:
            self._fatal_error = exc
            logger.exception("VideoManager: fatal error in worker loop")

    def _loop(self) -> None:
        # Sweep once immediately, then on every interval until stopped.
        # Event.wait(interval) returns True the moment stop() fires, giving a
        # prompt, interruptible periodic sleep.
        self._safe_sweep()
        while not self._stop_event.wait(self._config.sweep_interval_seconds):
            self._safe_sweep()
        logger.info("VideoManager: loop exiting cleanly")

    def _safe_sweep(self) -> None:
        try:
            self._sweep()
        except Exception:
            logger.exception("VideoManager: sweep failed; will retry next interval")

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    def _sweep(self) -> None:
        cfg = self._config
        if not self._footage_path.is_dir():
            return

        # Snapshot (path, mtime, size); skip files that vanished mid-listing.
        entries: list[tuple[Path, float, int]] = []
        for path in self._footage_path.glob(cfg.glob_pattern):
            try:
                st = path.stat()
            except OSError:
                continue
            entries.append((path, st.st_mtime, st.st_size))

        if not entries:
            return

        # Sort oldest-first by mtime; protect the newest (last) segment - ffmpeg
        # is still stream-copying into it, so deleting it would corrupt the live
        # recording.
        entries.sort(key=lambda e: e[1])
        candidates = entries[:-1]

        scanned = len(entries)
        deleted = 0
        freed = 0
        now = time.time()
        # Total bytes on disk, including the protected newest segment; both
        # passes decrement it so the budget reflects real directory size.
        total = sum(size for _, _, size in entries)

        # 1. TTL pass.
        survivors: list[tuple[Path, float, int]] = []
        if cfg.ttl_seconds is not None:
            for path, mtime, size in candidates:
                age = now - mtime
                if age > cfg.ttl_seconds:
                    if self._delete(path):
                        deleted += 1
                        freed += size
                        total -= size
                        logger.info("DELETED | ttl    | %s | age=%.0fs", path.name, age)
                else:
                    survivors.append((path, mtime, size))
        else:
            survivors = list(candidates)

        # 2. Budget pass - delete oldest survivors until directory size <= max_bytes.
        if cfg.max_bytes is not None:
            for path, _mtime, size in survivors:
                if total <= cfg.max_bytes:
                    break
                if self._delete(path):
                    deleted += 1
                    freed += size
                    total -= size
                    logger.info("DELETED | budget | %s | freed=%dB", path.name, size)

        if deleted:
            logger.info(
                "VideoManager: sweep done | scanned=%d | deleted=%d | freed=%dB",
                scanned,
                deleted,
                freed,
            )

    def _delete(self, path: Path) -> bool:
        """Delete a segment, tolerating a concurrent recorder/rotation race."""
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError:
            logger.exception("VideoManager: failed to delete %s", path)
            return False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "VideoManager":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
