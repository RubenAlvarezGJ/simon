"""Tests for the footage-retention sweep + thread lifecycle.

The sweep is exercised directly (``manager._sweep()``) against a tmp footage dir
of fake ``cam_*.mkv`` files — no real thread, no ffmpeg. Ages are set by
back-dating mtimes with ``os.utime``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from recorder.video_manager import RetentionConfig, VideoManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(footage: Path, name: str, size: int, age_seconds: float) -> Path:
    """Create a fake footage file of ``size`` bytes with mtime ``age_seconds`` old."""
    path = footage / name
    path.write_bytes(b"\0" * size)
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))
    return path


def _names(footage: Path) -> set[str]:
    return {p.name for p in footage.glob("cam_*.mkv")}


# ---------------------------------------------------------------------------
# Sweep — TTL
# ---------------------------------------------------------------------------


def test_ttl_deletes_old_keeps_new(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    # newest is protected regardless, so add a distinct fresh newest segment.
    _make_segment(footage, "cam_old.mkv", 10, age_seconds=1000)
    _make_segment(footage, "cam_mid.mkv", 10, age_seconds=500)
    _make_segment(footage, "cam_new.mkv", 10, age_seconds=1)

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=600, max_bytes=None)
    )
    mgr._sweep()

    # old (>600s) deleted; mid (<600s) and newest survive.
    assert _names(footage) == {"cam_mid.mkv", "cam_new.mkv"}


def test_ttl_none_disables(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    _make_segment(footage, "cam_old.mkv", 10, age_seconds=10_000)
    _make_segment(footage, "cam_new.mkv", 10, age_seconds=1)

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=None, max_bytes=None)
    )
    mgr._sweep()

    assert _names(footage) == {"cam_old.mkv", "cam_new.mkv"}


# ---------------------------------------------------------------------------
# Sweep — budget
# ---------------------------------------------------------------------------


def test_budget_deletes_oldest_until_under(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    # 4 x 100B = 400B total; budget 250B -> must drop to <= 250B.
    _make_segment(footage, "cam_1.mkv", 100, age_seconds=400)
    _make_segment(footage, "cam_2.mkv", 100, age_seconds=300)
    _make_segment(footage, "cam_3.mkv", 100, age_seconds=200)
    _make_segment(footage, "cam_4.mkv", 100, age_seconds=1)  # newest, protected

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=None, max_bytes=250)
    )
    mgr._sweep()

    # Oldest-first: delete cam_1, cam_2 -> remaining cam_3 (100) + cam_4 (100) = 200 <= 250.
    assert _names(footage) == {"cam_3.mkv", "cam_4.mkv"}


def test_budget_none_disables(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    _make_segment(footage, "cam_1.mkv", 1000, age_seconds=400)
    _make_segment(footage, "cam_2.mkv", 1000, age_seconds=1)

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=None, max_bytes=None)
    )
    mgr._sweep()

    assert _names(footage) == {"cam_1.mkv", "cam_2.mkv"}


# ---------------------------------------------------------------------------
# Newest-segment protection
# ---------------------------------------------------------------------------


def test_newest_segment_never_deleted(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    # The single newest segment violates both TTL and budget, but is the active
    # recording target and must survive.
    _make_segment(footage, "cam_only.mkv", 10_000, age_seconds=10_000)

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=1, max_bytes=1)
    )
    mgr._sweep()

    assert _names(footage) == {"cam_only.mkv"}


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_missing_dir_is_noop(tmp_path: Path) -> None:
    mgr = VideoManager(RetentionConfig(footage_path=tmp_path / "does_not_exist"))
    mgr._sweep()  # must not raise


def test_empty_dir_is_noop(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    mgr = VideoManager(RetentionConfig(footage_path=footage))
    mgr._sweep()  # must not raise
    assert _names(footage) == set()


def test_unlink_race_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    _make_segment(footage, "cam_1.mkv", 100, age_seconds=1000)
    _make_segment(footage, "cam_2.mkv", 100, age_seconds=900)
    _make_segment(footage, "cam_new.mkv", 100, age_seconds=1)

    real_unlink = Path.unlink

    def flaky_unlink(self: Path, *a, **k):  # first delete races and vanishes
        if self.name == "cam_1.mkv":
            raise FileNotFoundError(self)
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    mgr = VideoManager(
        RetentionConfig(footage_path=footage, ttl_seconds=500, max_bytes=None)
    )
    mgr._sweep()  # must not raise despite the racing delete

    # cam_2 still deleted; cam_1 raised (left on disk); newest kept.
    assert "cam_2.mkv" not in _names(footage)
    assert "cam_new.mkv" in _names(footage)


# ---------------------------------------------------------------------------
# Thread lifecycle
# ---------------------------------------------------------------------------


def test_start_stop_clean(tmp_path: Path) -> None:
    footage = tmp_path / "footage"
    footage.mkdir()
    mgr = VideoManager(
        RetentionConfig(footage_path=footage, sweep_interval_seconds=60)
    )
    mgr.start()
    assert mgr.is_running
    mgr.stop(timeout=5.0)
    assert not mgr.is_running
    assert mgr.fatal_error is None


def test_double_start_raises(tmp_path: Path) -> None:
    mgr = VideoManager(RetentionConfig(footage_path=tmp_path, sweep_interval_seconds=60))
    mgr.start()
    try:
        with pytest.raises(RuntimeError):
            mgr.start()
    finally:
        mgr.stop()


def test_stop_before_start_is_noop(tmp_path: Path) -> None:
    mgr = VideoManager(RetentionConfig(footage_path=tmp_path))
    mgr.stop()  # must not raise
    assert not mgr.is_running
