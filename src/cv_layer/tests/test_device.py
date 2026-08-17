"""Tests for deployment-target resolution.

These are pure-function tests: torch.cuda.is_available is monkeypatched so the
same assertions hold on a CUDA laptop and a CPU-only mini PC.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import torch

from cv_layer.device import resolve_device, resolve_model_path


# ---------------------------------------------------------------------------
# resolve_device
# ---------------------------------------------------------------------------


def test_auto_prefers_cuda_when_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert resolve_device("auto") == "cuda"


def test_auto_falls_back_to_cpu_when_unavailable(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert resolve_device("auto") == "cpu"


def test_none_and_empty_string_mean_auto(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert resolve_device(None) == "cpu"
    assert resolve_device("") == "cpu"


def test_explicit_cpu_passes_through_even_with_cuda_present(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert resolve_device("cpu") == "cpu"


def test_explicit_cuda_passes_through_when_available(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    assert resolve_device("cuda") == "cuda"
    assert resolve_device("cuda:1") == "cuda:1"


def test_explicit_cuda_warns_and_degrades_when_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with caplog.at_level(logging.WARNING):
        assert resolve_device("cuda") == "cpu"
    assert "cuda" in caplog.text.lower()


# ---------------------------------------------------------------------------
# resolve_model_path
# ---------------------------------------------------------------------------


def test_returns_path_when_weights_exist(tmp_path):
    weights = tmp_path / "yolo11s.pt"
    weights.write_bytes(b"not-a-real-model")
    assert resolve_model_path(weights) == weights


def test_accepts_a_string_path(tmp_path):
    weights = tmp_path / "yolo11s.pt"
    weights.write_bytes(b"not-a-real-model")
    assert resolve_model_path(str(weights)) == weights


def test_raises_with_the_offending_path_when_missing(tmp_path):
    missing = tmp_path / "nope.pt"
    with pytest.raises(FileNotFoundError) as excinfo:
        resolve_model_path(missing)
    assert str(missing) in str(excinfo.value)


def test_error_message_mentions_the_container_mount(tmp_path):
    """A missing mount is the likely cause in production; say so."""
    with pytest.raises(FileNotFoundError) as excinfo:
        resolve_model_path(tmp_path / "nope.pt")
    assert "mount" in str(excinfo.value).lower()
