import queue
import threading
import time
import logging
from collections import deque
from typing import Any, Self

logger = logging.getLogger(__name__)


class DetectionEngine:
    """
    Pulls frames from an input queue, runs GPU inference via AdaptiveDetector class,
    and pushes (annotated_frame, detections) result tuples onto an output queue on a 
    dedicated background thread.

    This decouples the GPU from both the frame reader (I/O-bound) and the display
    loop (main-thread-bound), so the GPU is never idle waiting on either.

    Usage:
        engine = DetectionEngine(
            detector=detector,
            input_queue=frame_queue,
            output_queue=result_queue,
            stop_event=stop_event,
        )
        engine.start()
        # ... consume result_queue elsewhere ...
        engine.stop()

    Note:
        The engine forwards the ``None`` sentinel it receives from VideoReader
        downstream to result_queue, so the display loop can detect end-of-stream
        without polling a shared flag.
    """

    def __init__(
        self,
        detector: Any,
        input_queue: queue.Queue,
        output_queue: queue.Queue,
        stop_event: threading.Event,
        fps_window: int = 30,
    ) -> None:
        """
        Args:
            detector:       AdaptiveDetector object. Must be fully initialised and have
                            its model already loaded before being passed in.
            input_queue:    Queue of raw BGR numpy frames from VideoReader.
                            A ``None`` value signals end-of-stream.
            output_queue:   Queue of ``(annotated_frame, detections)`` tuples
                            for the display/consumer thread.
            stop_event:     Shared threading.Event; set by any thread to request
                            graceful shutdown of the whole pipeline.
            fps_window:     Number of recent frame durations used to compute the
                            rolling-average FPS passed to ``process_frame``.
                            Larger values are smoother while smaller values react
                            faster to throughput changes.
        """
        self._detector = detector
        self._input_queue = input_queue
        self._output_queue = output_queue
        self._stop_event = stop_event
        self._fps_window = fps_window

        self._thread: threading.Thread | None = None

        # Diagnostics
        self._frames_processed: int = 0
        self._frames_skipped: int = 0   # result dropped because output queue full
        self._total_inference_time: float = 0.0

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def start(self) -> Self:
        """
        Launch the background inference thread.

        Returns self for optional chaining: ``engine.start()``
        """
        self._thread = threading.Thread(
            target=self._inference_loop,
            name="DetectionEngine",
            daemon=True,
        )
        self._thread.start()
        logger.info("DetectionEngine: inference thread started")
        return self

    def stop(self) -> None:
        """
        Signal the inference thread to stop and block until it has exited.

        Safe to call multiple times or before ``start()``.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        logger.info(
            "DetectionEngine: stopped.  "
            "frames_processed=%d  frames_skipped=%d  avg_inference_ms=%.1f",
            self._frames_processed,
            self._frames_skipped,
            self.avg_inference_ms,
        )

    @property
    def is_alive(self) -> bool:
        """True while the background thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def frames_processed(self) -> int:
        """Total frames that completed inference."""
        return self._frames_processed

    @property
    def frames_skipped(self) -> int:
        """
        Results dropped because the output queue was full.
        Non-zero means the display loop is slower than the GPU.
        """
        return self._frames_skipped

    @property
    def avg_inference_ms(self) -> float:
        """Mean inference time in milliseconds over all processed frames."""
        if self._frames_processed == 0:
            return 0.0
        return (self._total_inference_time / self._frames_processed) * 1000

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _inference_loop(self) -> None:
        """
        Main loop executed on the background thread.

        Pulls frames from ``_input_queue``, runs ``detector.process_frame``,
        and puts results on ``_output_queue``.  Exits when:
          - ``_stop_event`` is set (pipeline shutdown requested), or
          - A ``None`` sentinel is dequeued (end of stream from VideoReader).

        The ``None`` sentinel is forwarded downstream before the thread exits.
        """
        logger.debug("DetectionEngine: inference loop started")

        # Rolling window of recent frame durations for stable FPS estimation.
        # deque with maxlen automatically evicts the oldest entry.
        frame_durations: deque[float] = deque(maxlen=self._fps_window)
        prev_time: float = time.perf_counter()

        while not self._stop_event.is_set():
            try:
               frame = self._input_queue.get(block=True, timeout=0.1)
            except queue.Empty:
                # Timeout exceeded, try again.
                continue
 
            if frame is None:
                # Sentinal value detected.
                logger.info("DetectionEngine: end-of-stream sentinel received")
                self._forward_sentinel()
                break

            # --- FPS (rolling average) ---
            curr_time = time.perf_counter()
            frame_durations.append(curr_time - prev_time)
            prev_time = curr_time
            fps = self._rolling_fps(frame_durations)

            # --- GPU Inference ---
            t0 = time.perf_counter()
            annotated_frame, detections = self._detector.process_frame(frame)
            inference_time = time.perf_counter() - t0

            self._frames_processed += 1
            self._total_inference_time += inference_time

            logger.debug(
                "DetectionEngine: frame %d  fps=%.1f  inference=%.1fms",
                self._frames_processed,
                fps,
                inference_time * 1000,
            )

            self._enqueue_result(annotated_frame, detections)

        logger.debug("DetectionEngine: inference loop exiting")

    def _rolling_fps(self, durations: deque) -> float:
        """
        Compute FPS as the inverse of the mean frame duration over the rolling
        window.  Falls back to 0.0 if no durations have been recorded yet.

        Using the mean rather than the most recent delta avoids the large FPS
        spike that appears on the very first frame (where prev_time is the loop
        start, not a previous frame).

        Args:
            durations: A deque of recent inter-frame durations in seconds.

        Returns:
            Smoothed FPS as a float.
        """
        if not durations:
            return 0.0
        mean_duration = sum(durations) / len(durations)
        return 1.0 / mean_duration if mean_duration > 0 else 0.0

    def _enqueue_result(self, annotated_frame, detections) -> None:
        """
        Put an inference result onto the output queue.

        Uses a non-blocking put and silently drops the result if the display
        thread is too slow to keep up.  Dropping results (rather than blocking)
        ensures the GPU never stalls waiting on the display.

        Args:
            annotated_frame: BGR numpy array with bounding boxes drawn.
            detections:      Raw detection objects from the detector.
        """
        try:
            self._output_queue.put_nowait((annotated_frame, detections))
        except queue.Full:
            self._frames_skipped += 1
            logger.debug(
                "DetectionEngine: result dropped (output queue full). "
                "total_skipped=%d",
                self._frames_skipped,
            )

    def _forward_sentinel(self) -> None:
        """
        Push ``None`` onto the output queue to propagate end-of-stream to the
        display loop.  Retries until successful so the sentinel is never lost.
        """
        while not self._stop_event.is_set():
            try:
                self._output_queue.put(None, block=True, timeout=0.5)
                logger.debug("DetectionEngine: sentinel forwarded to output queue")
                return
            except queue.Full:
                logger.debug("DetectionEngine: waiting to forward sentinel...")

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        status = "running" if self.is_alive else "stopped"
        return (
            f"DetectionEngine(status={status}, "
            f"frames_processed={self._frames_processed}, "
            f"frames_skipped={self._frames_skipped}, "
            f"avg_inference_ms={self.avg_inference_ms:.1f})"
        )