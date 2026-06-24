"""State / diagnostics routes: /api/state, /api/severities, /api/health."""

from __future__ import annotations

from fastapi import APIRouter, Request

from logic_layer.rule_evaluator import Severity

from ..runtime_state import RuntimeState

router = APIRouter()


def _state(request: Request) -> RuntimeState:
    return request.app.state.runtime


@router.get("/api/state")
async def get_state(request: Request) -> dict:
    return _state(request).state_dict()


@router.get("/api/severities")
async def get_severities() -> list[str]:
    return [s.value for s in Severity]


@router.get("/api/health")
async def get_health(request: Request) -> dict:
    state = _state(request)
    runner = getattr(request.app.state, "runner", None)
    return {
        "status": "ok",
        "uptime_s": round(state.uptime_seconds(), 3),
        "pipeline_running": bool(runner.is_running) if runner is not None else False,
        "frame_id": state.frame_id,
    }
