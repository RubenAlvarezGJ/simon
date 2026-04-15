import queue
import threading
import logging
from typing import Generator, Any

from .video_reader import VideoReader
from .detection_engine import DetectionEngine

logger = logging.getLogger(__name__)

class VideoPipeline:
    """
    Composes VideoReader and DetectionEngine into a single inference pipeline.

    VideoPipeline owns:
      - The two inter-thread queues (frame_queue, result_queue)
      - The shared stop_event
      - The VideoReader and DetectionEngine instances

    It however does not own the detector. The caller creates and passes it in,
    which keeps model loading, device selection, and lifecycle management
    out of the pipeline.

    Usage (typical):
        pipeline = VideoPipeline(source="video.mp4", detector=detector)
        pipeline.start()

        for annotated_frame, detections in pipeline.results():
            cv.imshow("Visual", annotated_frame)
            if cv.waitKey(1) & 0xFF == ord('q'):
                break

        pipeline.stop()

    Usage (context manager):
        with VideoPipeline(source=0, detector=detector) as pipeline:
            for annotated_frame, detections in pipeline.results():
                cv.imshow("Visual", annotated_frame)
                if cv.waitKey(1) & 0xFF == ord('q'):
                    break

    Pipeline topology:
        VideoReader  -->  [frame_queue]  -->  DetectionEngine  -->  [result_queue]  -->  results()
    """

    def __init__(
        self,
        source: str | int,
        detector: Any,
        frame_queue_size: int = 4,
        result_queue_size: int = 4,
        drop_frames_if_full: bool = True,
        fps_window: int = 30,
    ) -> None:
        """
        Args:
            source:               Video file path (str) or camera index (int).
            detector:             An initialised AdaptiveDetector object.
            frame_queue_size:     Max frames buffered between reader and GPU.
                                  Small values reduce latency; large values
                                  absorb bursts but consume RAM.
            result_queue_size:    Max results buffered between GPU and display.
            drop_frames_if_full:  Passed to VideoReader. Drops
                                  incoming frames when frame_queue is full if
                                  set to True.
                                  True is correct for live cameras; False
                                  processes every frame for offline video.
            fps_window:           Rolling window size for FPS smoothing passed
                                  to DetectionEngine.
        """
        self._source = source
        self._detector = detector

        # Queues (owned exclusively by this class)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=frame_queue_size)
        self._result_queue: queue.Queue = queue.Queue(maxsize=result_queue_size)

        # Single shared stop event for the whole pipeline
        self._stop_event: threading.Event = threading.Event()

        # Component instances
        self._reader = VideoReader(
            source=source,
            output_queue=self._frame_queue,
            stop_event=self._stop_event,
            drop_if_full=drop_frames_if_full,
        )
        self._engine = DetectionEngine(
            detector=detector,
            input_queue=self._frame_queue,
            output_queue=self._result_queue,
            stop_event=self._stop_event,
            fps_window=fps_window,
        )

        self._running: bool = False

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def start(self) -> "VideoPipeline":
        """
        Start the reader and inference threads.

        Returns self for optional chaining: ``pipeline.start()``

        Raises:
            RuntimeError: If the pipeline is already running, or if the video
                          source cannot be opened (propagated from VideoReader).
        """
        if self._running:
            raise RuntimeError("VideoPipeline is already running.")

        logger.info("VideoPipeline: starting  source='%s'", self._source)
        self._reader.start()
        self._engine.start()
        self._running = True
        return self

    def stop(self) -> None:
        """
        Gracefully shut down the entire pipeline.

        Sets the shared stop_event, then joins both threads in correct dependency 
        order (reader first, then engine) so the engine always drains any incoming
        frames before exiting.

        Safe to call multiple times.
        """
        if not self._running:
            return

        logger.info("VideoPipeline: stopping...")
        self._stop_event.set()

        # Join reader first, once it stops producing, the engine will drain
        # the remaining frames and exit naturally.
        self._reader.stop()
        self._engine.stop()

        self._running = False
        logger.info(
            "VideoPipeline: stopped.  %s  |  %s",
            repr(self._reader),
            repr(self._engine),
        )

    def results(self) -> Generator[tuple, None, None]:
        """
        Generator that yields (annotated_frame, detections) tuples as they
        come off the result queue.

        Blocks until the next result is available, then yields it.  Exits
        automatically when the end-of-stream sentinel (None) is received or
        when stop_event is set externally.

        This is the main interface between the pipeline and the display loop.
        The caller never touches any of the queues directly.

        Yields:
            (annotated_frame, detections) where annotated_frame is a BGR numpy
            array with bounding boxes drawn, and detections is a list of
            detections within the frame (see AdaptiveDetector.process_frame()).

        Example:
            for annotated_frame, detections in pipeline.results():
                cv.imshow("Visual", annotated_frame)
                if cv.waitKey(1) & 0xFF == ord('q'):
                    break
        """
        while not self._stop_event.is_set():
            try:
                result = self._result_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue

            if result is None:
                # End-of-stream sentinel forwarded from DetectionEngine, so stop.
                logger.info("VideoPipeline: end-of-stream reached")
                break

            yield result

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """True if start() has been called and stop() has not yet completed."""
        return self._running

    @property
    def stats(self) -> dict:
        """
        Snapshot of runtime diagnostics from both components.

        Useful for logging, dashboards, or post-run analysis.

        Returns a dict with keys:
            reader_frames_read      - frames decoded from the source
            reader_frames_dropped   - frames dropped because frame_queue was full
            engine_frames_processed - frames that completed GPU inference
            engine_frames_skipped   - results dropped because result_queue was full
            engine_avg_inference_ms - mean inference latency in milliseconds
        """
        return {
            "reader_frames_read": self._reader.frames_read,
            "reader_frames_dropped": self._reader.frames_dropped,
            "engine_frames_processed": self._engine.frames_processed,
            "engine_frames_skipped": self._engine.frames_skipped,
            "engine_avg_inference_ms": self._engine.avg_inference_ms,
        }

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "VideoPipeline":
        """Start the pipeline and return self for use in a ``with`` block."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Stop the pipeline on exit, whether the block completed normally or
        raised an exception.

        Returns False so exceptions propagate to the caller.
        """
        self.stop()
        return False

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return (
            f"VideoPipeline(source={self._source!r}, status={status}, "
            f"frames_read={self._reader.frames_read}, "
            f"frames_processed={self._engine.frames_processed})"
        )