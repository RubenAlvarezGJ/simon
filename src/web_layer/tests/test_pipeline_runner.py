"""Tests for PipelineRunner that swap stub detector + pipeline factories.

These tests run end-to-end against a fake video pipeline (no camera, no
model, no cv_layer dependency). They confirm:
  * publish_frame is called and jpeg_bytes ends up on RuntimeState
  * pipeline_stats / dispatcher_stats / confirmed_snapshot are populated
  * pending reload flags are consumed on the worker thread
  * stop() returns cleanly within timeout
"""

from __future__ import annotations

import logging
import time
import types
from pathlib import Path

import numpy as np
import pytest
import supervision as sv

from web_layer.pipeline_runner import PipelineRunner
from web_layer.runtime_state import RuntimeState


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubDetector:
    pass


def _empty_detections() -> sv.Detections:
    return sv.Detections(
        xyxy=np.zeros((0, 4), dtype=np.float32),
        class_id=np.zeros((0,), dtype=int),
        confidence=np.zeros((0,), dtype=np.float32),
        tracker_id=np.zeros((0,), dtype=int),
    )


class _StubPipeline:
    """Stand-in for VideoPipeline that yields a fixed number of frames."""

    def __init__(self, frames: int = 3) -> None:
        self._frames = frames
        self.stats = {"reader_frames_read": frames}

    def __enter__(self) -> "_StubPipeline":
        return self

    def __exit__(self, *_a) -> bool:
        return False

    def results(self):
        for i in range(self._frames):
            # Solid-color BGR frame, distinguishable per i.
            frame = np.full((48, 64, 3), i * 30 % 255, dtype=np.uint8)
            yield frame, _empty_detections()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _build_runner(state: RuntimeState, tmp_path: Path, frames: int = 3) -> PipelineRunner:
    return PipelineRunner(
        state,
        source="stub",
        zones_path=str(tmp_path / "zones.json"),  # nonexistent => bypass mode
        rules_path=str(tmp_path / "rules.json"),  # nonexistent => bypass mode
        jsonl_path=str(tmp_path / "alerts.jsonl"),
        detector_factory=lambda: _StubDetector(),
        pipeline_factory=lambda _det: _StubPipeline(frames=frames),
    )


def test_publish_frame_populates_runtime_state(tmp_path: Path) -> None:
    state = RuntimeState()
    runner = _build_runner(state, tmp_path, frames=3)
    try:
        runner.start(wait_for_first_frame=True, timeout=5.0)
        # Give the worker a beat to drain its 3 frames.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and state.frame_id < 3:
            time.sleep(0.02)
    finally:
        runner.stop(timeout=5.0)

    assert state.frame_id >= 1
    assert state.jpeg_bytes is not None
    # JPEG magic bytes: FF D8 FF
    assert state.jpeg_bytes[:3] == b"\xff\xd8\xff"
    assert state.frame_shape == (48, 64)


def test_stop_returns_within_timeout(tmp_path: Path) -> None:
    state = RuntimeState()
    runner = _build_runner(state, tmp_path, frames=2)
    runner.start(wait_for_first_frame=True, timeout=5.0)
    t0 = time.monotonic()
    runner.stop(timeout=5.0)
    assert time.monotonic() - t0 < 5.0
    assert not runner.is_running
    assert runner.fatal_error is None


def test_reload_flags_drained(tmp_path: Path) -> None:
    """Reload flags requested from the main thread are cleared by the worker."""
    state = RuntimeState()
    state.request_zones_reload()
    state.request_rules_reload()
    runner = _build_runner(state, tmp_path, frames=2)
    try:
        runner.start(wait_for_first_frame=True, timeout=5.0)
        # Give the worker enough iterations to drain flags.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and (
            state.pending_zones_reload or state.pending_rules_reload
        ):
            time.sleep(0.02)
    finally:
        runner.stop(timeout=5.0)
    assert state.pending_zones_reload is False
    assert state.pending_rules_reload is False


def test_pipeline_stats_published(tmp_path: Path) -> None:
    state = RuntimeState()
    runner = _build_runner(state, tmp_path, frames=2)
    try:
        runner.start(wait_for_first_frame=True, timeout=5.0)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and "reader_frames_read" not in state.pipeline_stats:
            time.sleep(0.02)
    finally:
        runner.stop(timeout=5.0)
    assert state.pipeline_stats.get("reader_frames_read") == 2
    assert "enqueued" in state.dispatcher_stats


# ---------------------------------------------------------------------------
# Detector factory configuration
# ---------------------------------------------------------------------------


def test_default_detector_factory_passes_model_and_device(monkeypatch, tmp_path):
    """The factory-builder wires configuration into AdaptiveDetector."""
    import cv_layer.detector.adaptive_detector as adaptive_module
    from web_layer.pipeline_runner import _default_detector_factory

    weights = tmp_path / "custom.pt"
    weights.write_bytes(b"not-a-real-model")

    seen: dict[str, object] = {}

    class _FakeAdaptive:
        def __init__(self, model_path, device=None):
            seen["model_path"] = model_path
            seen["device"] = device

    monkeypatch.setattr(adaptive_module, "AdaptiveDetector", _FakeAdaptive)

    factory = _default_detector_factory(str(weights), "cpu")
    factory()

    assert seen["model_path"] == str(weights)
    assert seen["device"] == "cpu"


def test_default_detector_factory_rejects_missing_weights(tmp_path):
    """A bad models/ mount must fail loudly, not download stock weights."""
    from web_layer.pipeline_runner import _default_detector_factory

    factory = _default_detector_factory(str(tmp_path / "missing.pt"), "cpu")
    with pytest.raises(FileNotFoundError):
        factory()


def test_default_detector_factory_logs_resolved_device(monkeypatch, tmp_path, caplog):
    """Important 4: the resolved device must be logged, from the factory.

    On the gpu compose service SIMON_DEVICE defaults to "auto"; if the NVIDIA
    container toolkit is missing the container would otherwise silently fall
    back to CPU with no log line at all.
    """
    import cv_layer.detector.adaptive_detector as adaptive_module
    from web_layer.pipeline_runner import _default_detector_factory

    weights = tmp_path / "custom.pt"
    weights.write_bytes(b"not-a-real-model")

    monkeypatch.setattr(
        adaptive_module, "AdaptiveDetector", lambda model_path, device=None: None
    )

    factory = _default_detector_factory(str(weights), "cpu")
    with caplog.at_level(logging.INFO, logger="web_layer.pipeline_runner"):
        factory()

    assert "device=cpu" in caplog.text
    assert str(weights) in caplog.text


def test_runner_accepts_model_path_and_device(tmp_path):
    """Constructing with the new kwargs must not raise."""
    from web_layer.pipeline_runner import PipelineRunner
    from web_layer.runtime_state import RuntimeState

    runner = PipelineRunner(
        RuntimeState(),
        source=0,
        model_path=str(tmp_path / "weights.pt"),
        device="cpu",
    )
    assert runner is not None
