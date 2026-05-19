from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    from logic_layer.rule_evaluator import TriggeredAlert


class OverlayBuffer:
    """
    Thread-safe, TTL-bounded list of recent alerts for on-screen rendering.

    Entries older than ``ttl_seconds`` are pruned lazily on every ``snapshot``
    call; ``push`` keeps the list capped at ``max_items`` so a burst of alerts
    cannot grow it unbounded between snapshots.

    Args:
        ttl_seconds:  How long an alert stays on screen after it arrives.
        max_items:    Hard cap on simultaneously-displayed alerts.
    """

    def __init__(self, ttl_seconds: float = 3.0, max_items: int = 5) -> None:
        self._ttl = float(ttl_seconds)
        self._max_items = int(max_items)
        self._lock = threading.Lock()
        self._items: list[tuple[float, "TriggeredAlert"]] = []

    def push(self, alert: "TriggeredAlert") -> None:
        """Record an alert with the current monotonic timestamp."""
        now = time.monotonic()
        with self._lock:
            self._items.append((now, alert))
            if len(self._items) > self._max_items:
                self._items = self._items[-self._max_items:]

    def snapshot(self) -> list[tuple[float, "TriggeredAlert"]]:
        """Return a copy of unexpired entries, pruning expired ones in place."""
        cutoff = time.monotonic() - self._ttl
        with self._lock:
            self._items = [pair for pair in self._items if pair[0] >= cutoff]
            return list(self._items)

    def clear(self) -> None:
        """Drop all entries. Used by tests and on shutdown."""
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        return len(self.snapshot())


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.7
_FONT_THICKNESS = 2
_LINE_PAD = 6
_MARGIN = 10
_TEXT_COLOR = (255, 255, 255)   # white BGR
_BG_COLOR = (0, 0, 200)         # dark red BGR


def draw_overlay(frame: np.ndarray, buffer: OverlayBuffer) -> np.ndarray:
    """
    Draw one banner line per unexpired alert at the top-left of ``frame``.

    Mutates the frame in place and returns it for chainable calls. A no-op 
    when the buffer is empty.
    """
    items = buffer.snapshot()
    if not items:
        return frame

    y = _MARGIN
    for _, alert in items:
        text = f"[ALERT] {alert.rule_name}"
        (text_w, text_h), baseline = cv2.getTextSize(
            text, _FONT, _FONT_SCALE, _FONT_THICKNESS
        )
        top_left = (_MARGIN, y)
        bottom_right = (
            _MARGIN + text_w + 2 * _LINE_PAD,
            y + text_h + baseline + 2 * _LINE_PAD,
        )
        cv2.rectangle(frame, top_left, bottom_right, _BG_COLOR, thickness=-1)
        cv2.putText(
            frame,
            text,
            (_MARGIN + _LINE_PAD, y + text_h + _LINE_PAD),
            _FONT,
            _FONT_SCALE,
            _TEXT_COLOR,
            _FONT_THICKNESS,
            cv2.LINE_AA,
        )
        y = bottom_right[1] + _LINE_PAD

    return frame
