"""Rules CRUD: read and write src/config/rules.json atomically."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ..config_io import atomic_write_json
from ..runtime_state import RuntimeState
from ..schemas import RulesPayload

logger = logging.getLogger(__name__)
router = APIRouter()


def _state(request: Request) -> RuntimeState:
    return request.app.state.runtime


def _path(request: Request) -> Path:
    return request.app.state.rules_path


@router.get("/api/rules")
async def get_rules(request: Request) -> dict:
    path = _path(request)
    if not path.exists():
        return {"rules": []}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("GET /api/rules: failed to read %s: %s", path, exc)
        return {"rules": []}
    if not isinstance(data, dict) or "rules" not in data:
        return {"rules": []}
    return data


@router.put("/api/rules")
async def put_rules(payload: RulesPayload, request: Request) -> dict:
    path = _path(request)
    try:
        atomic_write_json(path, payload.model_dump())
    except OSError as exc:
        logger.exception("PUT /api/rules: failed to write %s", path)
        raise HTTPException(status_code=500, detail=f"Write failed: {exc}") from exc

    _state(request).request_rules_reload()
    return {"ok": True, "rules": len(payload.rules)}
