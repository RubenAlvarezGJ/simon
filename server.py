"""Entry point for the threat-detector web command center.

Usage::

    python server.py                            # camera 0, bind 127.0.0.1:8000
    python server.py --source videos/clip.mp4   # play a file instead
    python server.py --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Threat Detector web command center")
    p.add_argument(
        "--source",
        default="0",
        help=(
            "Video source: an integer camera index (e.g. '0') or a file path. "
            "Default: 0 (first available camera)."
        ),
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    p.add_argument("--port", type=int, default=8000, help="Bind port. Default: 8000")
    p.add_argument(
        "--zones",
        default="src/config/zones.json",
        help="Path to zones config JSON. Default: src/config/zones.json",
    )
    p.add_argument(
        "--rules",
        default="src/config/rules.json",
        help="Path to rules config JSON. Default: src/config/rules.json",
    )
    p.add_argument(
        "--alerts-log",
        default="logs/alerts.jsonl",
        help="JSONL alert log path. Default: logs/alerts.jsonl",
    )
    p.add_argument(
        "--static-dir",
        default="web/dist",
        help="Directory to serve as the SPA. Default: web/dist",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level. Default: INFO",
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
    import uvicorn

    app = create_app(
        source=_resolve_source(args.source),
        zones_path=args.zones,
        rules_path=args.rules,
        jsonl_path=args.alerts_log,
        static_dir=args.static_dir,
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
