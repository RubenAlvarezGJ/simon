from __future__ import annotations

import json
import logging
import threading
import requests
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from logic_layer.rule_evaluator import TriggeredAlert

    from .overlay import OverlayBuffer


logger = logging.getLogger(__name__)


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
            "[ALERT] %s | sev=%s | ids=%s | t=%.3f",
            alert.rule_name,
            alert.severity.value,
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


# ---------------------------------------------------------------------------
# TelegramSink
# ---------------------------------------------------------------------------

class TelegramSink:
    """
    Pushes a notification to a Telegram chat, routed by the alert's severity.

    Routing:
        - ``low``      not sent (logged by other sinks only).
        - ``high``     sent with ``disable_notification=True`` (silent).
        - ``critical`` sent with ``disable_notification=False`` (audible).

    Follows the project's Bypass Mode convention: if the bot token or chat ID
    is missing from the environment, the sink logs an INFO line and becomes a
    no-op rather than raising, so a misconfigured notifier never takes down the
    surveillance pipeline.

    Args:
        timeout: Per-request HTTP timeout in seconds. Bounds how long a single
                 ``deliver()`` call can block the shared dispatcher worker.
    """

    _API_BASE = "https://api.telegram.org"

    def __init__(self, timeout: float = 5.0) -> None:
        load_dotenv()

        self._timeout = timeout
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id = os.environ.get("CHAT_ID")
        self._session = requests.Session()

        self.bypass = not (self._token and self._chat_id)
        if self.bypass:
            logger.info(
                "TelegramSink: TELEGRAM_BOT_TOKEN / CHAT_ID not set - "
                "running in bypass mode (push notifications disabled)."
            )

    def deliver(self, alert: "TriggeredAlert") -> None:
        if self.bypass:
            return
        
        if alert.severity == "low":
            return

        url = f"{self._API_BASE}/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": self._format_message(alert),
            "disable_notification": alert.severity == "high",
        }

        response = self._session.post(url, json=payload, timeout=self._timeout)
        response.raise_for_status()
        logger.info(
            "TelegramSink: delivered alert %r (sev=%s, ids=%s)",
            alert.rule_name,
            alert.severity.value,
            alert.tracker_ids,
        )

    @staticmethod
    def _format_message(alert: "TriggeredAlert") -> str:
        """Build a plain-text notification body from the alert payload."""
        snapshots = alert.threat_snapshots
        classes = sorted({s.get("class_name", "unknown") for s in snapshots})
        zones = sorted(
            {z for s in snapshots for z in s.get("active_zones", [])}
        )

        lines = [
            f"{alert.severity.value.upper()} DETECTION",
            f"Rule: {alert.rule_name}",
            f"Class: {', '.join(classes) or 'unknown'}",
        ]
        if zones:
            lines.append(f"Zone: {', '.join(zones)}")
        lines.append(f"Tracker IDs: {alert.tracker_ids}")
        if alert.rule_description:
            lines.append(alert.rule_description)
        return "\n".join(lines)

    def close(self) -> None:
        self._session.close()

