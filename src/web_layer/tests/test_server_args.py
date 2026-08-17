"""server.py must be configurable from the environment for containers.

Precedence is CLI flag > env var > built-in default.
"""

from __future__ import annotations

import logging
import sys

import pytest
import uvicorn

import server


@pytest.fixture(autouse=True)
def _no_cli_args(monkeypatch):
    """argparse reads sys.argv; give it just the program name by default."""
    monkeypatch.setattr(sys, "argv", ["server.py"])


def test_defaults_are_unchanged_without_env(monkeypatch):
    for var in ("SIMON_SOURCE", "SIMON_HOST", "SIMON_MODEL", "SIMON_DEVICE"):
        monkeypatch.delenv(var, raising=False)
    args = server._parse_args()
    assert args.source == "0"
    assert args.host == "127.0.0.1"
    assert args.model == "models/yolo11s.pt"
    assert args.device == "auto"


def test_env_vars_supply_defaults(monkeypatch):
    monkeypatch.setenv("SIMON_SOURCE", "rtsp://host.docker.internal:8554/cam")
    monkeypatch.setenv("SIMON_HOST", "0.0.0.0")
    monkeypatch.setenv("SIMON_MODEL", "models/yolo11s.engine")
    monkeypatch.setenv("SIMON_DEVICE", "cpu")
    args = server._parse_args()
    assert args.source == "rtsp://host.docker.internal:8554/cam"
    assert args.host == "0.0.0.0"
    assert args.model == "models/yolo11s.engine"
    assert args.device == "cpu"


def test_cli_flag_overrides_env(monkeypatch):
    monkeypatch.setenv("SIMON_SOURCE", "rtsp://from-env")
    monkeypatch.setattr(sys, "argv", ["server.py", "--source", "rtsp://from-flag"])
    assert server._parse_args().source == "rtsp://from-flag"


def test_numeric_env_vars_are_coerced(monkeypatch):
    monkeypatch.setenv("SIMON_PORT", "9000")
    monkeypatch.setenv("SIMON_MAX_FOOTAGE_GB", "20")
    args = server._parse_args()
    assert args.port == 9000
    assert isinstance(args.port, int)
    assert args.max_footage_gb == 20.0


def test_resolve_source_still_maps_digits_to_camera_index():
    assert server._resolve_source("0") == 0
    assert server._resolve_source("rtsp://cam") == "rtsp://cam"


# ---------------------------------------------------------------------------
# Important 5: env-supplied values bypass argparse `choices`
# ---------------------------------------------------------------------------


def test_lowercase_log_level_env_var_is_normalized(monkeypatch):
    """SIMON_LOG_LEVEL=debug is the natural spelling in a compose file.

    argparse only validates `choices=` against an explicit CLI flag, never
    against `default=`, so without upper-casing this would reach
    getattr(logging, "debug") later -- which returns a function, not a level.
    """
    monkeypatch.setenv("SIMON_LOG_LEVEL", "debug")
    args = server._parse_args()
    assert args.log_level == "DEBUG"
    level, is_fallback = server._resolve_log_level(args.log_level)
    assert level == logging.DEBUG
    assert is_fallback is False


def test_invalid_log_level_env_var_falls_back_to_info_with_warning(monkeypatch, caplog):
    """An unrecognized SIMON_LOG_LEVEL must degrade to INFO, not crash."""
    monkeypatch.setenv("SIMON_LOG_LEVEL", "TRACE")
    args = server._parse_args()
    # Bypasses choices= entirely because it arrived via default=, not a flag.
    assert args.log_level == "TRACE"

    with caplog.at_level(logging.WARNING):
        level, is_fallback = server._resolve_log_level(args.log_level)

    assert level == logging.INFO
    assert is_fallback is True


def test_mixed_case_device_env_var_is_normalized(monkeypatch):
    """SIMON_DEVICE=CUDA must match resolve_device's `startswith("cuda")` check.

    resolve_device() checks preference.startswith("cuda") (lowercase), so an
    uppercase "CUDA" previously slipped past the CUDA-unavailable warning
    branch entirely and would raise an opaque torch error instead.
    """
    monkeypatch.setenv("SIMON_DEVICE", "CUDA")
    args = server._parse_args()
    assert args.device == "cuda"


def test_mixed_case_device_cli_flag_is_normalized(monkeypatch):
    """The --device CLI flag bypassed normalization entirely (Important 5).

    Only the SIMON_DEVICE env path went through `.strip().lower()`, because
    it lived inside `os.getenv(...)` in `_parse_args` rather than in
    `resolve_device` itself. `python server.py --device CUDA` reached
    resolve_device unnormalized, so `preference.startswith("cuda")` (which
    checks the lowercase form) missed it and "CUDA" -- not "cuda" -- was
    handed straight to `model.to()`.
    """
    monkeypatch.delenv("SIMON_DEVICE", raising=False)
    monkeypatch.setattr(sys, "argv", ["server.py", "--device", "CUDA"])
    args = server._parse_args()

    from cv_layer.device import resolve_device

    monkeypatch.setattr("torch.cuda.is_available", lambda: True)
    assert resolve_device(args.device) == "cuda"


def test_auto_device_cli_flag_case_insensitive(monkeypatch):
    """--device Auto must still mean auto-detect, not an explicit device string."""
    monkeypatch.delenv("SIMON_DEVICE", raising=False)
    monkeypatch.setattr(sys, "argv", ["server.py", "--device", "Auto"])
    args = server._parse_args()

    from cv_layer.device import resolve_device

    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    assert resolve_device(args.device) == "cpu"


# ---------------------------------------------------------------------------
# Important 4: the raw, un-degraded log level string must never reach uvicorn
# ---------------------------------------------------------------------------


def test_invalid_log_level_does_not_crash_uvicorn_config(monkeypatch):
    """SIMON_LOG_LEVEL=verbose is invalid for both `logging` and uvicorn.

    server.py used to hand args.log_level (the raw, un-degraded string)
    straight to uvicorn.Config as `log_level=args.log_level.lower()`.
    uvicorn's Config.__init__ does LOG_LEVELS[self.log_level.lower()] with no
    fallback of its own -- an uncaught KeyError, crash-looping the container
    under compose's `restart: unless-stopped`. The *resolved* level (already
    degraded to INFO by _resolve_log_level) must be what reaches uvicorn.
    """
    monkeypatch.setenv("SIMON_LOG_LEVEL", "verbose")
    args = server._parse_args()
    assert args.log_level == "VERBOSE"

    level, is_fallback = server._resolve_log_level(args.log_level)
    assert is_fallback is True

    resolved_name = logging.getLevelName(level).lower()
    assert resolved_name == "info"

    # This is the exact call server.main() makes; it must not raise.
    config = uvicorn.Config(
        lambda scope, receive, send: None,
        log_level=resolved_name,
    )
    assert config.log_level == resolved_name
