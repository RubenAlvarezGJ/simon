"""WebSocket /api/events: alerts (pushed by BroadcastSink) + 5 Hz snapshots."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from logic_layer.state_manager import CRITICAL_CLASSES

from ..runtime_state import RuntimeState

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)
router = APIRouter()

SNAPSHOT_HZ = 5.0
SNAPSHOT_INTERVAL = 1.0 / SNAPSHOT_HZ
SUBSCRIBER_QUEUE_MAX = 64


def _state(ws: WebSocket) -> RuntimeState:
    return ws.app.state.runtime


def _hello_frame(state: RuntimeState, zones: dict) -> dict:
    return {
        "type": "hello",
        "data": {
            "critical_classes": sorted(CRITICAL_CLASSES),
            "zones": zones,
            "frame_shape": state.frame_shape,
            "frame_id": state.frame_id,
        },
    }


def _read_zones(app) -> dict:
    """Best-effort read of the current zones file. Failure returns {}."""
    path = getattr(app.state, "zones_path", None)
    if path is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@router.websocket("/api/events")
async def events(ws: WebSocket) -> None:
    await ws.accept()
    state = _state(ws)
    queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
    state.add_subscriber(queue)

    # Initial hello
    try:
        await ws.send_json(_hello_frame(state, _read_zones(ws.app)))
    except Exception:
        state.remove_subscriber(queue)
        return

    snapshot_task = asyncio.create_task(_snapshot_pump(state, queue))
    try:
        while True:
            msg = await queue.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket /api/events: unexpected error")
    finally:
        snapshot_task.cancel()
        state.remove_subscriber(queue)


async def _snapshot_pump(state: RuntimeState, queue: asyncio.Queue) -> None:
    """Push a periodic state snapshot to the subscriber queue."""
    try:
        while True:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            message = {
                "type": "snapshot",
                "data": {
                    "threats": list(state.confirmed_snapshot),
                    "pipeline_stats": dict(state.pipeline_stats),
                    "dispatcher_stats": dict(state.dispatcher_stats),
                    "frame_id": state.frame_id,
                },
            }
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Slow client - drop snapshot to keep alerts flowing.
                continue
    except asyncio.CancelledError:
        pass
