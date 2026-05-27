"""Stream-related routes: live MJPEG, latest snapshot, snapshot meta."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..mjpeg import MULTIPART_CONTENT_TYPE, mjpeg_generator
from ..runtime_state import RuntimeState

router = APIRouter()


def _state(request: Request) -> RuntimeState:
    return request.app.state.runtime


@router.get("/api/stream.mjpg")
async def stream(request: Request) -> StreamingResponse:
    state = _state(request)
    return StreamingResponse(
        mjpeg_generator(state),
        media_type=MULTIPART_CONTENT_TYPE,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/snapshot.jpg")
async def snapshot(request: Request) -> Response:
    state = _state(request)
    jpeg = state.jpeg_bytes
    if jpeg is None:
        raise HTTPException(status_code=503, detail="No frame published yet.")
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/api/snapshot/meta")
async def snapshot_meta(request: Request) -> dict:
    state = _state(request)
    shape = state.frame_shape
    if shape is None:
        raise HTTPException(status_code=503, detail="No frame published yet.")
    h, w = shape
    return {"width": w, "height": h, "frame_id": state.frame_id}
