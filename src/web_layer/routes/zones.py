"""Zones CRUD: read and write src/config/zones.json atomically."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..config_io import atomic_write_json
from ..runtime_state import RuntimeState
from ..schemas import ZonesPayload

logger = logging.getLogger(__name__)
router = APIRouter()


def _state(request: Request) -> RuntimeState:
    return request.app.state.runtime


def _path(request: Request) -> Path:
    return request.app.state.zones_path


@router.get("/api/zones")
async def get_zones(request: Request) -> dict[str, list[list[int]]]:
    path = _path(request)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("GET /api/zones: failed to read %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


@router.put("/api/zones")
async def put_zones(payload: ZonesPayload, request: Request) -> dict:
    path = _path(request)
    try:
        atomic_write_json(path, payload.model_dump())
    except OSError as exc:
        logger.exception("PUT /api/zones: failed to write %s", path)
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}") from exc

    _state(request).request_zones_reload()
    return {"ok": True, "zones": len(payload.root)}
