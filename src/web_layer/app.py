"""FastAPI application factory + lifespan for the threat-detector command center."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from recorder.video_recorder import VideoRecorder
from .pipeline_runner import PipelineRunner
from .routes import events as events_routes
from .routes import rules as rules_routes
from .routes import state as state_routes
from .routes import stream as stream_routes
from .routes import zones as zones_routes
from .runtime_state import RuntimeState

logger = logging.getLogger(__name__)


def create_app(
    source: str | int = 0,
    *,
    footage_path: str | Path = "footage",
    zones_path: str | Path = "src/config/zones.json",
    rules_path: str | Path = "src/config/rules.json",
    jsonl_path: str | Path = "logs/alerts.jsonl",
    static_dir: str | Path | None = "web/dist",
    autostart_recorder: bool = True,
    autostart_pipeline: bool = True,
    recorder: Optional[VideoRecorder] = None,
    runner: Optional[PipelineRunner] = None,
) -> FastAPI:
    """Build the FastAPI app + wire up shared state and lifespan."""

    runtime = RuntimeState()
    zones_path = Path(zones_path)
    rules_path = Path(rules_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Capture the running asyncio loop so BroadcastSink can post from
        # the dispatcher worker thread via call_soon_threadsafe.
        runtime.event_loop = asyncio.get_running_loop()

        # PipelineRunner setup
        nonlocal runner
        if autostart_pipeline and runner is None:
            runner = PipelineRunner(
                runtime,
                source=source,
                zones_path=str(zones_path),
                rules_path=str(rules_path),
                jsonl_path=str(jsonl_path),
            )
        if runner is not None:
            app.state.runner = runner
            try:
                runner.start()
                logger.info("FastAPI lifespan: PipelineRunner started")
            except Exception:
                logger.exception("FastAPI lifespan: failed to start PipelineRunner")

        # VideoRecorder setup. RTSP source required.
        nonlocal recorder
        if autostart_recorder and recorder is None:
            if isinstance(source, str) and source.startswith(("rtsp://", "rtsps://")):
                recorder = VideoRecorder(source=source, destination=footage_path)
            else:
                logger.info(
                    "FastAPI lifespan: recorder autostart skipped; source %r is "
                    "not an RTSP URL",
                    source,
                )
        if recorder is not None:
            app.state.recorder = recorder
            try:
                recorder.start()
                logger.info("FastAPI lifespan: VideoRecorder started")
            except Exception:
                logger.exception("FastAPI lifespan: failed to start VideoRecorder")

        try:
            yield
        finally:
            logger.info("Lifespan shutting down")
            runtime.notify_shutdown()
            rn = getattr(app.state, "runner", None)
            rc = getattr(app.state, "recorder", None)

            if rn is not None:
                try:
                    rn.stop(timeout=5.0)
                except Exception:
                    logger.exception("FastAPI lifespan: error stopping runner")

            if rc is not None:
                try:
                    rc.stop()
                except Exception:
                    logger.exception("FastAPI lifespan: error stopping recorder")

            runtime.event_loop = None

    app = FastAPI(title="Threat Detector Command Center", lifespan=lifespan)

    # Shared mutable state lives on app.state so route handlers can pick it up.
    app.state.runtime = runtime
    app.state.zones_path = zones_path
    app.state.rules_path = rules_path

    # Routes
    app.include_router(stream_routes.router)
    app.include_router(zones_routes.router)
    app.include_router(rules_routes.router)
    app.include_router(state_routes.router)
    app.include_router(events_routes.router)

    # Static SPA at /
    if static_dir is not None:
        static_path = Path(static_dir)
        if static_path.exists():
            app.mount(
                "/",
                StaticFiles(directory=str(static_path), html=True),
                name="spa",
            )
        else:
            logger.warning(
                "create_app: static dir %s not found; SPA will not be served. "
                "Run `npm run build` inside web/ to populate it.",
                static_path,
            )

    return app
