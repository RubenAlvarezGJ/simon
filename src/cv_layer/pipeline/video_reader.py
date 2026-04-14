import cv2 as cv
import queue
import threading
import logging
from pathlib import Path
from typing import Self

logger = logging.getLogger(__name__)

class VideoReader:
    """
    Reads frames from a video file or camera on a dedicated background thread.

    Decouples I/O (disk/camera) from GPU inference to prevent blocking the
    inference thread.

    Args:
        source (str | int): Path to video file or camera index (e.g., 0).
        output_queue (queue.Queue): Thread-safe queue for raw frames (BGR, uint8).
        stop_event (threading.Event): Event used to signal a graceful shutdown.
        max_queue_size (int): Max frames to buffer. Keep small to save RAM.
        drop_if_full (bool): If True, drops frames to maintain low latency (live).
            If False, blocks until space is available (offline processing).

    Attributes:
        frames_read (int): Total frames pulled from source.
        frames_dropped (int): Total frames discarded due to full queue.

    Usage:
        >>> reader = VideoReader(source=0, output_queue=q, stop_event=e)
        >>> reader.start()

    Note:
        Pushes `None` to the queue as a sentinel value upon EOF or error
        so consumers can detect without polling a shared flag.
    """

    def __init__(
        self,
        source: str | int,
        output_queue: queue.Queue,
        stop_event: threading.Event,
        max_queue_size: int = 4,
        drop_if_full: bool = True,
    ) -> None:
        
        self._source = source
        self._output_queue = output_queue
        self._stop_event = stop_event
        self._drop_if_full = drop_if_full

        self._cap: cv.VideoCapture | None = None
        self._thread: threading.Thread | None = None

        # Introspection / diagnostics
        self._frames_read: int = 0
        self._frames_dropped: int = 0

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def start(self) -> Self:
        """
        Open the video source and launch the background reader thread.

        Returns self so callers can chain:  ``reader.start()``

        Raises:
            RuntimeError: If the video source cannot be opened.
        """
        self._cap = cv.VideoCapture(self._source)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"VideoReader: could not open source '{self._source}'. "
                "Check the path/index and ensure the file exists."
            )

        logger.info(
            "VideoReader: opened '%s'  (%dx%d @ %.1f fps)",
            self._source,
            int(self._cap.get(cv.CAP_PROP_FRAME_WIDTH)),
            int(self._cap.get(cv.CAP_PROP_FRAME_HEIGHT)),
            self._cap.get(cv.CAP_PROP_FPS),
        )

        self._thread = threading.Thread(
            target=self._read_loop,
            name="VideoReader",
            daemon=True,  # Won't block process exit if main thread dies
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """
        Signal the reader to stop and block until the thread has exited.

        Safe to call multiple times or before ``start()``.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info(
            "VideoReader: stopped.  frames_read=%d  frames_dropped=%d",
            self._frames_read,
            self._frames_dropped,
        )

    @property
    def is_alive(self) -> bool:
        """True while the background thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def frames_read(self) -> int:
        """Total number of frames successfully decoded from the source."""
        return self._frames_read

    @property
    def frames_dropped(self) -> int:
        """
        Number of frames discarded because the output queue was full.
        A non-zero value means the GPU consumer is slower than the source.
        """
        return self._frames_dropped

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_loop(self) -> None:
        """
        Main loop executed on the background thread.

        Continuously reads frames from the capture device and puts them on
        ``_output_queue``.  Exits when:
          - ``_stop_event`` is set (pipeline shutdown requested), or
          - ``cap.read()`` fails (end of file, camera disconnect, corrupt frame).

        A ``None`` sentinel is always enqueued before the thread exits so that
        downstream consumers can detect end-of-stream.
        """
        logger.debug("VideoReader: reader thread started")

        while not self._stop_event.is_set():
            ret, frame = self._cap.read()

            if not ret:
                logger.info("VideoReader: end of stream reached")
                break

            self._frames_read += 1
            self._enqueue(frame)

        self._enqueue_sentinel()
        logger.debug("VideoReader: reader thread exiting")

    def _enqueue(self, frame) -> None:
        """
        Put a frame on the output queue, respecting the drop_if_full policy.

        Args:
            frame: A BGR numpy array decoded from the video source.
        """
        if self._drop_if_full:
            try:
                self._output_queue.put_nowait(frame)
            except queue.Full:
                self._frames_dropped += 1
                logger.debug(
                    "VideoReader: frame dropped (queue full). "
                    "total_dropped=%d",
                    self._frames_dropped,
                )
        else:
            # Blocking put with a short timeout so we can still respond to
            # stop_event without waiting indefinitely.
            while not self._stop_event.is_set():
                try:
                    self._output_queue.put(frame, block=True, timeout=0.1)
                    break
                except queue.Full:
                    continue  # retry until stop_event or queue drains

    def _enqueue_sentinel(self) -> None:
        """
        Push ``None`` onto the queue to signal end-of-stream.

        Retries with a timeout loop so the sentinel is always delivered even
        when the queue is temporarily full.
        """
        while True:
            try:
                self._output_queue.put(None, block=True, timeout=0.5)
                break
            except queue.Full:
                logger.debug("VideoReader: waiting to enqueue sentinel...")

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        status = "running" if self.is_alive else "stopped"
        return (
            f"VideoReader(source={self._source!r}, status={status}, "
            f"frames_read={self._frames_read}, "
            f"frames_dropped={self._frames_dropped})"
        )