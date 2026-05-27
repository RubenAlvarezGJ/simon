"""Alert sink that mirrors every TriggeredAlert into RuntimeState and onto
every connected WebSocket subscriber.

Runs on the AlertDispatcher worker thread (NOT the asyncio loop). Posts to
each subscriber's ``asyncio.Queue`` via ``loop.call_soon_threadsafe`` to keep
WebSocket delivery in lockstep with the JSONL sink. Slow clients are dropped
silently by swallowing ``asyncio.QueueFull``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logic_layer.rule_evaluator import TriggeredAlert

    from .runtime_state import RuntimeState

logger = logging.getLogger(__name__)


class BroadcastSink:
    """A ``Sink``-compatible adapter that pushes alerts into RuntimeState."""

    def __init__(self, state: "RuntimeState") -> None:
        self._state = state

    def deliver(self, alert: "TriggeredAlert") -> None:
        payload = alert.to_dict()
        # Append to recent_alerts deque - atomic on a single-element append.
        self._state.recent_alerts.append(payload)

        loop = self._state.event_loop
        if loop is None:
            # No event loop bound yet (server still booting). The alert is
            # already in recent_alerts; new WS clients will get it on connect.
            return

        message = {"type": "alert", "data": payload}
        for queue in self._state.snapshot_subscribers():
            try:
                loop.call_soon_threadsafe(self._safe_put, queue, message)
            except RuntimeError:
                # Loop closed mid-shutdown; nothing we can do.
                logger.debug("BroadcastSink: event loop closed; skipping subscriber.")

    @staticmethod
    def _safe_put(queue: asyncio.Queue, message: dict) -> None:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.debug("BroadcastSink: subscriber queue full; dropping alert.")
