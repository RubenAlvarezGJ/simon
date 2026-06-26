"""Background thread that drives the full per-frame loop and publishes the
result to a shared ``RuntimeState`` for the FastAPI handlers.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

import cv2

from alert_layer.dispatcher import AlertDispatcher
from alert_layer.overlay import OverlayBuffer, draw_overlay
from alert_layer.sinks import ConsoleSink, JsonlSink, OverlaySink, TelegramSink, Sink
from logic_layer.rule_evaluator import RuleEvaluator
from logic_layer.spatial_engine import SpatialEngine
from logic_layer.state_manager import ActiveThreats

from .broadcast_sink import BroadcastSink
from .runtime_state import RuntimeState

logger = logging.getLogger(__name__)


# Type aliases for the factories used by tests to swap in stubs.
DetectorFactory = Callable[[], Any]
PipelineFactory = Callable[[Any], Any]


def _default_detector_factory() -> Any:
    """Construct the production AdaptiveDetector with CUDA when available."""
    import torch
    from cv_layer.detector.adaptive_detector import AdaptiveDetector

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return AdaptiveDetector("models/yolo11s.pt", device=device)


def _default_pipeline_factory(
    source: str | int,
    drop_frames_if_full: bool,
) -> PipelineFactory:
    """Return a factory that builds the production VideoPipeline."""
    from cv_layer.pipeline.pipeline import VideoPipeline

    def _build(detector: Any) -> Any:
        return VideoPipeline(source, detector, drop_frames_if_full=drop_frames_if_full)

    return _build


class PipelineRunner:
    """Owns the inference + logic + alert chain on a background thread.

    The thread:
      1. consumes pending zones/rules reload flags from ``RuntimeState`` and
         calls ``reload()`` on the appropriate engine (always on this thread);
      2. pulls one (annotated_frame, detections) tuple per iteration;
      3. drives ActiveThreats -> SpatialEngine -> RuleEvaluator;
      4. dispatches alerts to all sinks (including BroadcastSink);
      5. draws the OverlaySink banner onto the annotated frame;
      6. JPEG-encodes the annotated frame once and publishes it to
         ``RuntimeState`` so all MJPEG subscribers share the same bytes.
    """

    def __init__(
        self,
        state: RuntimeState,
        source: str | int = 0,
        *,
        zones_path: str = "src/config/zones.json",
        rules_path: str = "src/config/rules.json",
        jsonl_path: str = "logs/alerts.jsonl",
        jpeg_quality: int = 80,
        drop_frames_if_full: bool = True,
        detector_factory: Optional[DetectorFactory] = None,
        pipeline_factory: Optional[Callable[[Any], Any]] = None,
        extra_sinks: Optional[list[Sink]] = None,
    ) -> None:
        self._state = state
        self._source = source
        self._zones_path = zones_path
        self._rules_path = rules_path
        self._jsonl_path = jsonl_path
        self._jpeg_quality = jpeg_quality

        self._detector_factory = detector_factory or _default_detector_factory
        self._pipeline_factory = pipeline_factory or _default_pipeline_factory(
            source, drop_frames_if_full
        )
        self._extra_sinks: list[Sink] = list(extra_sinks or [])

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._fatal_error: Optional[BaseException] = None

        # Owned engines (created on the worker thread on start to avoid loading
        # CUDA / models on the FastAPI startup loop).
        self._spatial_engine: Optional[SpatialEngine] = None
        self._rule_evaluator: Optional[RuleEvaluator] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, wait_for_first_frame: bool = False, timeout: float = 30.0) -> None:
        if self._thread is not None:
            raise RuntimeError("PipelineRunner is already running.")
        self._stop_event.clear()
        self._started_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="PipelineRunner", daemon=True
        )
        self._thread.start()
        if wait_for_first_frame:
            self._started_event.wait(timeout=timeout)

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("PipelineRunner: worker did not exit within %.1fs", timeout)
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
            logger.exception("PipelineRunner: fatal error in worker loop")

    def _loop(self) -> None:
        detector = self._detector_factory()
        threat_registry = ActiveThreats()
        self._spatial_engine = SpatialEngine(zones_path=self._zones_path)
        self._rule_evaluator = RuleEvaluator(rules_path=self._rules_path)
        overlay_buffer = OverlayBuffer(ttl_seconds=3.0)

        sinks: list[Sink] = [
            ConsoleSink(),
            JsonlSink(self._jsonl_path),
            OverlaySink(overlay_buffer),
            BroadcastSink(self._state),
            TelegramSink(),
            *self._extra_sinks,
        ]

        pipeline = self._pipeline_factory(detector)

        with AlertDispatcher(sinks) as dispatcher, pipeline:
            for annotated_frame, detections in pipeline.results():
                if self._stop_event.is_set():
                    break

                # 1. Hot-reload (always on this thread)
                zones_pending, rules_pending = self._state.consume_reload_flags()
                if zones_pending:
                    try:
                        self._spatial_engine.reload()
                    except Exception:
                        logger.exception("PipelineRunner: zones reload failed")
                if rules_pending:
                    try:
                        self._rule_evaluator.reload()
                    except Exception:
                        logger.exception("PipelineRunner: rules reload failed")

                # 2. Logic chain
                threat_registry.update(detections)
                confirmed = threat_registry.get_confirmed_threats()
                self._spatial_engine.evaluate(confirmed)
                alerts = self._rule_evaluator.evaluate(confirmed)

                # 3. Alerts
                dispatcher.dispatch(alerts)

                # 4. Overlay
                draw_overlay(annotated_frame, overlay_buffer)

                # 5. Encode + publish
                ok, buf = cv2.imencode(
                    ".jpg",
                    annotated_frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(self._jpeg_quality)],
                )
                if not ok:
                    logger.warning("PipelineRunner: cv2.imencode returned False; skipping frame")
                    continue
                jpeg_bytes = buf.tobytes()
                h, w = annotated_frame.shape[:2]
                self._state.publish_frame(jpeg_bytes, (h, w))

                # 6. Replace ref-swap snapshots
                self._state.confirmed_snapshot = [t.to_dict() for t in confirmed]
                self._state.pipeline_stats = dict(pipeline.stats)
                self._state.dispatcher_stats = dict(dispatcher.stats)

                if not self._started_event.is_set():
                    self._started_event.set()

        logger.info("PipelineRunner: loop exiting cleanly")
