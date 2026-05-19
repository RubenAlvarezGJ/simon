from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from logic_layer.rule_evaluator import TriggeredAlert

    from .sinks import Sink

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """
    Queue-backed alert dispatcher with a single background worker thread.

    Usage (context manager - matches VideoPipeline)::

        with AlertDispatcher(sinks) as dispatcher:
            dispatcher.dispatch(alerts)   # called once per frame

    Args:
        sinks:        Ordered iterable of Sink objects. Each alert is
                      delivered to every sink in order.
        queue_size:   Max alerts buffered between main thread and worker.
        drop_on_full: If True, alerts are silently counted-and-dropped when
                      the queue is full. If
                      False, ``dispatch`` blocks until space is available.

    Attributes:
        stats: Live counters - ``enqueued``, ``delivered``, ``dropped``,
               ``sink_errors``. Snapshot for logging or diagnostics.
    """

    def __init__(
        self,
        sinks: Iterable["Sink"],
        queue_size: int = 64,
        drop_on_full: bool = True,
    ) -> None:
        self._sinks: list["Sink"] = list(sinks)
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop_event: threading.Event = threading.Event()
        self._drop_on_full = drop_on_full
        self._thread: threading.Thread | None = None
        self._running: bool = False

        self.stats: dict[str, int] = {
            "enqueued": 0,
            "delivered": 0,
            "dropped": 0,
            "sink_errors": 0,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> "AlertDispatcher":
        """Launch the worker thread. Returns self for chaining."""
        if self._running:
            raise RuntimeError("AlertDispatcher is already running.")

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="AlertDispatcher",
            daemon=True,
        )
        self._thread.start()
        self._running = True
        logger.info(
            "AlertDispatcher: started with %d sink(s): %s",
            len(self._sinks),
            [type(s).__name__ for s in self._sinks],
        )
        return self

    def stop(self, timeout: float = 2.0) -> None:
        """
        Signal shutdown, push the sentinel, join the worker, close sinks.

        Safe to call multiple times. The sentinel is delivered with a
        blocking put loop so a temporarily-full queue doesn't drop it.
        """
        if not self._running:
            return

        self._stop_event.set()
        self._enqueue_sentinel()

        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "AlertDispatcher: worker did not exit within %.1fs", timeout,
                )
            self._thread = None

        self._running = False

        for sink in self._sinks:
            close = getattr(sink, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.exception(
                        "AlertDispatcher: error closing sink %r",
                        type(sink).__name__,
                    )

        logger.info(
            "AlertDispatcher: stopped.  enqueued=%d delivered=%d dropped=%d sink_errors=%d",
            self.stats["enqueued"],
            self.stats["delivered"],
            self.stats["dropped"],
            self.stats["sink_errors"],
        )

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def dispatch(self, alerts: list["TriggeredAlert"]) -> None:
        """
        Enqueue alerts for delivery. Non-blocking when ``drop_on_full=True``.

        No-op on an empty list or after ``stop()``.
        """
        if not alerts:
            return
        if not self._running or self._stop_event.is_set():
            logger.warning(
                "AlertDispatcher: dispatch() called while not running; "
                "dropping %d alert(s).",
                len(alerts),
            )
            return

        for alert in alerts:
            if self._drop_on_full:
                try:
                    self._queue.put_nowait(alert)
                    self.stats["enqueued"] += 1
                except queue.Full:
                    self.stats["dropped"] += 1
            else:
                self._queue.put(alert, block=True)
                self.stats["enqueued"] += 1

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pending(self) -> int:
        """Approximate number of alerts waiting in the queue."""
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        logger.debug("AlertDispatcher: worker thread started")
        while True:
            try:
                item = self._queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue

            if item is None:
                break

            for sink in self._sinks:
                try:
                    sink.deliver(item)
                except Exception:
                    self.stats["sink_errors"] += 1
                    logger.exception(
                        "AlertDispatcher: sink %r raised on alert %r",
                        type(sink).__name__,
                        getattr(item, "rule_name", "<?>"),
                    )

            self.stats["delivered"] += 1
        logger.debug("AlertDispatcher: worker thread exiting")

    def _enqueue_sentinel(self) -> None:
        """Push the None sentinel, retrying if the queue is momentarily full."""
        while True:
            try:
                self._queue.put(None, block=True, timeout=0.5)
                return
            except queue.Full:
                logger.debug("AlertDispatcher: waiting to enqueue sentinel...")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "AlertDispatcher":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.stop()
        return False

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return (
            f"AlertDispatcher(status={status}, sinks={len(self._sinks)}, "
            f"enqueued={self.stats['enqueued']}, "
            f"delivered={self.stats['delivered']}, "
            f"dropped={self.stats['dropped']})"
        )
