"""Entry point for the threat-detector web command center.

Usage::

    python server.py                            # camera 0, bind 127.0.0.1:8000
    python server.py --source videos/clip.mp4   # play a file instead
    python server.py --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Simon's web interface")
    p.add_argument(
        "--source",
        default=os.getenv("SIMON_SOURCE", "0"),
        help=(
            "Video source: an integer camera index (e.g. '0'), a file path, or an "
            "RTSP URL. Env: SIMON_SOURCE. Default: 0"
        ),
    )
    p.add_argument(
        "--model",
        default=os.getenv("SIMON_MODEL", "models/yolo11s.pt"),
        help=(
            "Path to the detector weights. Env: SIMON_MODEL. "
            "Default: models/yolo11s.pt"
        ),
    )
    p.add_argument(
        "--device",
        default=os.getenv("SIMON_DEVICE", "auto"),
        help=(
            "Inference device: 'auto', 'cpu', or 'cuda'. Env: SIMON_DEVICE. "
            "Default: auto"
        ),
    )
    p.add_argument(
        "--host",
        default=os.getenv("SIMON_HOST", "127.0.0.1"),
        help="Bind host. Env: SIMON_HOST. Default: 127.0.0.1",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SIMON_PORT", "8000")),
        help="Bind port. Env: SIMON_PORT. Default: 8000",
    )
    p.add_argument(
        "--zones",
        default=os.getenv("SIMON_ZONES", "src/config/zones.json"),
        help=(
            "Path to zones config JSON. Env: SIMON_ZONES. "
            "Default: src/config/zones.json"
        ),
    )
    p.add_argument(
        "--rules",
        default=os.getenv("SIMON_RULES", "src/config/rules.json"),
        help=(
            "Path to rules config JSON. Env: SIMON_RULES. "
            "Default: src/config/rules.json"
        ),
    )
    p.add_argument(
        "--alerts-log",
        default=os.getenv("SIMON_ALERTS_LOG", "logs/alerts.jsonl"),
        help="JSONL alert log path. Env: SIMON_ALERTS_LOG. Default: logs/alerts.jsonl",
    )
    p.add_argument(
        "--static-dir",
        default=os.getenv("SIMON_STATIC_DIR", "web/dist"),
        help="Directory to serve as the SPA. Env: SIMON_STATIC_DIR. Default: web/dist",
    )
    p.add_argument(
        "--footage",
        default=os.getenv("SIMON_FOOTAGE", "footage"),
        help="Directory holding recorded footage. Env: SIMON_FOOTAGE. Default: footage",
    )
    p.add_argument(
        "--max-footage-gb",
        type=float,
        default=float(os.getenv("SIMON_MAX_FOOTAGE_GB", "10")),
        help=(
            "Footage-directory size budget in GB (0 = unlimited). "
            "Env: SIMON_MAX_FOOTAGE_GB. Default: 10"
        ),
    )
    p.add_argument(
        "--footage-ttl-hours",
        type=float,
        default=float(os.getenv("SIMON_FOOTAGE_TTL_HOURS", "24")),
        help=(
            "Delete footage older than this many hours (0 = no TTL). "
            "Env: SIMON_FOOTAGE_TTL_HOURS. Default: 24"
        ),
    )
    p.add_argument(
        "--footage-sweep-mins",
        type=float,
        default=float(os.getenv("SIMON_FOOTAGE_SWEEP_MINS", "1")),
        help=(
            "Minutes between footage-cleanup sweeps. The size budget is only "
            "enforced at sweep time, so footage can transiently exceed it by "
            "about one segment per sweep interval; keep this at or below the "
            "recorder's 60s segment duration. Env: SIMON_FOOTAGE_SWEEP_MINS. "
            "Default: 1"
        ),
    )
    p.add_argument(
        "--no-footage-cleanup",
        action="store_true",
        help="Disable the periodic footage-retention manager.",
    )
    p.add_argument(
        "--log-level",
        default=os.getenv("SIMON_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level. Env: SIMON_LOG_LEVEL. Default: INFO",
    )
    return p.parse_args()


def _resolve_source(raw: str) -> str | int:
    """Camera indices are int; everything else is a file path string."""
    if raw.isdigit():
        return int(raw)
    return raw


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    # Make `from src.web_layer.app import create_app` work alongside the
    # `pythonpath = src` test setup.
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

    from web_layer.app import create_app
    from recorder.video_manager import RetentionConfig
    import uvicorn

    retention_config = RetentionConfig(
        footage_path=args.footage,
        max_bytes=int(args.max_footage_gb * 1024 ** 3) if args.max_footage_gb > 0 else None,
        ttl_seconds=args.footage_ttl_hours * 3600 if args.footage_ttl_hours > 0 else None,
        sweep_interval_seconds=args.footage_sweep_mins * 60,
    )

    app = create_app(
        source=_resolve_source(args.source),
        footage_path=args.footage,
        zones_path=args.zones,
        rules_path=args.rules,
        jsonl_path=args.alerts_log,
        model_path=args.model,
        device=args.device,
        static_dir=args.static_dir,
        autostart_manager=not args.no_footage_cleanup,
        retention_config=retention_config,
    )
    runtime = app.state.runtime

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        timeout_graceful_shutdown=5,
    )
    server = uvicorn.Server(config)

    _orig_handle_exit = server.handle_exit

    def handle_exit(sig, frame):
        runtime.notify_shutdown()
        _orig_handle_exit(sig, frame)

    server.handle_exit = handle_exit

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
