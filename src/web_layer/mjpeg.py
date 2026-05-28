"""Helpers for streaming the latest annotated JPEG to multiple clients with
a single encode per frame.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from .runtime_state import RuntimeState

BOUNDARY = "frame"
MULTIPART_CONTENT_TYPE = f"multipart/x-mixed-replace; boundary={BOUNDARY}"


def _wait_for_new_frame(state: RuntimeState, last_id: int, timeout: float):
    """Block (in a worker thread) until ``frame_id > last_id`` or timeout."""
    return state.wait_for_frame(last_id, timeout=timeout)


async def mjpeg_generator(
    state: RuntimeState,
    keepalive_timeout: float = 1.0,
) -> AsyncGenerator[bytes, None]:
    """Yield MIME-multipart parts, one per published frame.

    Implemented with ``asyncio.to_thread`` so the event loop is never blocked
    waiting on the condition variable. ``keepalive_timeout`` lets the loop
    re-check ``state`` periodically (e.g. for client disconnect).
    """
    last_id = 0
    while not state.is_shutdown:
        try:
            frame_id, jpeg = await asyncio.to_thread(
                _wait_for_new_frame, state, last_id, keepalive_timeout
            )
        except asyncio.CancelledError:
            break

        if frame_id == last_id or jpeg is None:
            # Timeout fired without a new frame; loop again so the client
            # disconnect can be detected by Starlette.
            continue
        last_id = frame_id

        yield (
            b"--" + BOUNDARY.encode() + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
            + jpeg
            + b"\r\n"
        )
