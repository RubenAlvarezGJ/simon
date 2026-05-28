"""Shared, thread-safe state container linking the pipeline thread and the
asyncio event loop.

Locking discipline:

* ``frame_lock`` / ``frame_cond`` guard the latest encoded frame. Hold them
  only across the four-field swap of ``frame_id``, ``jpeg_bytes``,
  ``frame_shape``, ``frame_published_at``. JPEG encoding itself must happen
  *outside* the lock.

* ``confirmed_snapshot``, ``pipeline_stats``, ``dispatcher_stats`` are
  replaced by whole-object reference assignment. The GIL guarantees that
  a single attribute assignment is atomic, so readers can grab the ref then
  read at leisure without locking.

* ``recent_alerts`` is a ``collections.deque(maxlen=200)``. Its ``append``
  is GIL-atomic.

* ``reload_lock`` guards the two pending-reload booleans. The pipeline
  thread drains them on each iteration.

* ``subscribers`` is mutated only while holding ``subscribers_lock``.

* ``event_loop`` is captured in the FastAPI lifespan startup, not at
  construction (uvicorn's loop does not yet exist when this dataclass is
  built).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RuntimeState:
    # --- Frame publication -------------------------------------------------
    frame_lock: threading.Lock = field(default_factory=threading.Lock)
    frame_cond: threading.Condition = field(init=False)
    frame_id: int = 0
    jpeg_bytes: Optional[bytes] = None
    frame_shape: Optional[tuple[int, int]] = None  # (height, width)
    frame_published_at: float = 0.0
    shutdown_flag: bool = False

    # --- Atomic-ref-swap fields -------------------------------------------
    confirmed_snapshot: list[dict] = field(default_factory=list)
    recent_alerts: deque = field(default_factory=lambda: deque(maxlen=200))
    pipeline_stats: dict = field(default_factory=dict)
    dispatcher_stats: dict = field(default_factory=dict)

    # --- Hot-reload signalling --------------------------------------------
    reload_lock: threading.Lock = field(default_factory=threading.Lock)
    pending_zones_reload: bool = False
    pending_rules_reload: bool = False

    # --- WebSocket fanout --------------------------------------------------
    event_loop: Optional[asyncio.AbstractEventLoop] = None
    subscribers_lock: threading.Lock = field(default_factory=threading.Lock)
    subscribers: list[asyncio.Queue] = field(default_factory=list)

    # --- Process bookkeeping ----------------------------------------------
    started_at: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        # frame_cond must be bound to frame_lock so that waiters and notifiers
        # share the same primitive.
        object.__setattr__(self, "frame_cond", threading.Condition(self.frame_lock))

    # ------------------------------------------------------------------
    # Pipeline-thread API
    # ------------------------------------------------------------------

    def publish_frame(
        self,
        jpeg_bytes: bytes,
        frame_shape: tuple[int, int],
    ) -> int:
        """Atomically swap in a freshly-encoded JPEG. Returns new frame_id."""
        with self.frame_cond:
            self.frame_id += 1
            self.jpeg_bytes = jpeg_bytes
            self.frame_shape = frame_shape
            self.frame_published_at = time.monotonic()
            self.frame_cond.notify_all()
            return self.frame_id

    def consume_reload_flags(self) -> tuple[bool, bool]:
        """Return + clear the pending reload flags. Called by pipeline thread."""
        with self.reload_lock:
            zones = self.pending_zones_reload
            rules = self.pending_rules_reload
            self.pending_zones_reload = False
            self.pending_rules_reload = False
            return zones, rules

    # ------------------------------------------------------------------
    # Request-handler API (runs on asyncio loop)
    # ------------------------------------------------------------------

    def request_zones_reload(self) -> None:
        with self.reload_lock:
            self.pending_zones_reload = True

    def request_rules_reload(self) -> None:
        with self.reload_lock:
            self.pending_rules_reload = True

    # ------------------------------------------------------------------
    # WebSocket subscriber helpers
    # ------------------------------------------------------------------

    def add_subscriber(self, queue: asyncio.Queue) -> None:
        with self.subscribers_lock:
            self.subscribers.append(queue)

    def remove_subscriber(self, queue: asyncio.Queue) -> None:
        with self.subscribers_lock:
            try:
                self.subscribers.remove(queue)
            except ValueError:
                pass

    def snapshot_subscribers(self) -> list[asyncio.Queue]:
        """Return a shallow copy of the subscriber list for iteration."""
        with self.subscribers_lock:
            return list(self.subscribers)

    # ------------------------------------------------------------------
    # Read-side helpers
    # ------------------------------------------------------------------

    def wait_for_frame(self, last_id: int, timeout: Optional[float] = None) -> tuple[int, Optional[bytes]]:
        """Block (in a thread) until a frame newer than ``last_id`` is published.

        Returns ``(frame_id, jpeg_bytes)``. If ``timeout`` elapses without a
        new frame, returns the current state regardless (caller must check).
        """
        with self.frame_cond:
            self.frame_cond.wait_for(lambda: self.frame_id > last_id or self.shutdown_flag, timeout=timeout)
            return self.frame_id, self.jpeg_bytes

    def state_dict(self) -> dict[str, Any]:
        """Lightweight snapshot for ``GET /api/state``."""
        return {
            "threats": list(self.confirmed_snapshot),
            "pipeline_stats": dict(self.pipeline_stats),
            "dispatcher_stats": dict(self.dispatcher_stats),
            "recent_alerts": list(self.recent_alerts),
            "frame_id": self.frame_id,
            "frame_shape": self.frame_shape,
        }
    
    def notify_shutdown(self):
        with self.frame_cond:
            self.shutdown_flag = True
            self.frame_cond.notify_all()

    @property
    def is_shutdown(self) -> bool:
        return self.shutdown_flag

    def uptime_seconds(self) -> float:
        return time.monotonic() - self.started_at
