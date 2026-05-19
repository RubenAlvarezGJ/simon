from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from logic_layer.rule_evaluator import TriggeredAlert

    from .overlay import OverlayBuffer


@runtime_checkable
class Sink(Protocol):
    """Structural type for any alert output sink."""

    def deliver(self, alert: "TriggeredAlert") -> None: ...


# ---------------------------------------------------------------------------
# ConsoleSink
# ---------------------------------------------------------------------------

class ConsoleSink:
    """
    Emits one INFO log record per alert via the stdlib ``logging`` module.

    Uses its own named logger so callers can route or filter alert lines
    independently of the rest of the application's logging.
    """

    def __init__(self, logger_name: str = "alert_layer.console") -> None:
        self._logger = logging.getLogger(logger_name)

    def deliver(self, alert: "TriggeredAlert") -> None:
        self._logger.info(
            "[ALERT] %s | ids=%s | t=%.3f",
            alert.rule_name,
            alert.tracker_ids,
            alert.triggered_at,
        )


# ---------------------------------------------------------------------------
# JsonlSink
# ---------------------------------------------------------------------------

class JsonlSink:
    """
    Appends one JSON object per alert to a newline-delimited file.

    Opens the file once in ``__init__`` and holds the handle open for the
    sink's lifetime - this avoids the open/close overhead per alert and lets
    ``flush()`` push bytes to disk immediately so a crash doesn't lose the
    most recent alerts. Writes are guarded by a lock so multiple worker
    threads (or a test running in parallel) cannot interleave bytes.

    Args:
        path: Destination JSONL file. Parent directory is created if absent.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = self._path.open("a", encoding="utf-8")

    def deliver(self, alert: "TriggeredAlert") -> None:
        line = json.dumps(alert.to_dict(), ensure_ascii=False) + "\n"
        with self._lock:
            if self._fh is None or self._fh.closed:
                return
            self._fh.write(line)
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            if self._fh is not None and not self._fh.closed:
                self._fh.close()
            self._fh = None

    @property
    def path(self) -> Path:
        return self._path


# ---------------------------------------------------------------------------
# OverlaySink
# ---------------------------------------------------------------------------

class OverlaySink:
    """
    Forwards alerts into an ``OverlayBuffer`` so the main thread can render
    them onto the displayed video frame.
    """

    def __init__(self, buffer: "OverlayBuffer") -> None:
        self._buffer = buffer

    def deliver(self, alert: "TriggeredAlert") -> None:
        self._buffer.push(alert)
