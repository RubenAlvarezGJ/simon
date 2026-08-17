"""The detectors must not assume CUDA is present.

Constructing a real YOLODetector would load weights from disk and hit the GPU,
so ultralytics.YOLO is replaced with a fake that records what device it was
moved to.
"""

from __future__ import annotations

import pytest
import torch

from cv_layer.detector.adaptive_detector import AdaptiveDetector
from cv_layer.detector.yolo_detector import YOLODetector


class _FakeYOLOModel:
    """Stand-in for an ultralytics YOLO model."""

    names = {0: "person"}

    def __init__(self) -> None:
        self.moved_to: str | None = None

    def to(self, device):
        self.moved_to = device
        return self


@pytest.fixture
def fake_yolo(monkeypatch):
    """Patch YOLO in the module that calls it, and hand back the fake model."""
    model = _FakeYOLOModel()
    monkeypatch.setattr(
        "cv_layer.detector.yolo_detector.YOLO",
        lambda _path: model,
    )
    return model


def test_yolo_detector_defaults_to_cpu_without_cuda(monkeypatch, fake_yolo):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    detector = YOLODetector("models/whatever.pt")
    assert detector.device == "cpu"
    assert fake_yolo.moved_to == "cpu"


def test_yolo_detector_defaults_to_cuda_with_cuda(monkeypatch, fake_yolo):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    detector = YOLODetector("models/whatever.pt")
    assert detector.device == "cuda"
    assert fake_yolo.moved_to == "cuda"


def test_yolo_detector_honours_an_explicit_device(monkeypatch, fake_yolo):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    detector = YOLODetector("models/whatever.pt", device="cpu")
    assert detector.device == "cpu"
    assert fake_yolo.moved_to == "cpu"


def test_adaptive_detector_defaults_to_cpu_without_cuda(monkeypatch, fake_yolo):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    detector = AdaptiveDetector("models/whatever.pt")
    assert detector.detector.device == "cpu"


def test_adaptive_detector_forwards_an_explicit_device(monkeypatch, fake_yolo):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    detector = AdaptiveDetector("models/whatever.pt", device="cpu")
    assert detector.detector.device == "cpu"
