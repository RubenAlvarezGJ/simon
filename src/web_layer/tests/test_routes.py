"""Smoke tests for the FastAPI app via TestClient.

Uses an externally-provided ``PipelineRunner`` so the app does not autostart
the production pipeline (no camera, no torch model).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
import supervision as sv
from fastapi.testclient import TestClient

from web_layer.app import create_app
from web_layer.pipeline_runner import PipelineRunner
from web_layer.runtime_state import RuntimeState


class _StubDetector:
    pass


def _empty_detections() -> sv.Detections:
    return sv.Detections(
        xyxy=np.zeros((0, 4), dtype=np.float32),
        class_id=np.zeros((0,), dtype=int),
        confidence=np.zeros((0,), dtype=np.float32),
        tracker_id=np.zeros((0,), dtype=int),
    )


class _StubPipeline:
    def __init__(self, frames: int = 200, sleep: float = 0.01) -> None:
        self._frames = frames
        self._sleep = sleep
        self.stats = {"reader_frames_read": 0}

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def results(self):
        for i in range(self._frames):
            frame = np.full((48, 64, 3), (i * 13) % 255, dtype=np.uint8)
            self.stats["reader_frames_read"] = i + 1
            yield frame, _empty_detections()
            time.sleep(self._sleep)


def _build_client(tmp_path: Path):
    state_dir = tmp_path / "cfg"
    state_dir.mkdir()
    zones_path = state_dir / "zones.json"
    rules_path = state_dir / "rules.json"

    # Wire a runner with stub factories so the lifespan never loads YOLO.
    placeholder_state = RuntimeState()
    runner = PipelineRunner(
        placeholder_state,  # gets reassigned below
        source="stub",
        zones_path=str(zones_path),
        rules_path=str(rules_path),
        jsonl_path=str(tmp_path / "alerts.jsonl"),
        detector_factory=lambda: _StubDetector(),
        pipeline_factory=lambda _det: _StubPipeline(),
    )

    app = create_app(
        source="stub",
        zones_path=zones_path,
        rules_path=rules_path,
        jsonl_path=str(tmp_path / "alerts.jsonl"),
        static_dir=None,
        autostart_pipeline=False,
        runner=runner,
    )
    # Re-bind runner to point at the runtime that the app actually published.
    runner._state = app.state.runtime
    return app, zones_path, rules_path


@pytest.fixture
def app_client(tmp_path: Path):
    app, zones_path, rules_path = _build_client(tmp_path)
    with TestClient(app) as client:
        # Wait for first frame so /api/snapshot.jpg has something to return.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and app.state.runtime.frame_id == 0:
            time.sleep(0.02)
        yield client, app, zones_path, rules_path


def test_health(app_client):
    client, *_ = app_client
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_s" in body
    assert body["pipeline_running"] is True


def test_severities(app_client):
    client, *_ = app_client
    r = client.get("/api/severities")
    assert r.status_code == 200
    body = r.json()
    assert body == ["low", "high", "critical"]


def test_snapshot_after_first_frame(app_client):
    client, app, *_ = app_client
    assert app.state.runtime.frame_id > 0
    r = client.get("/api/snapshot.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:3] == b"\xff\xd8\xff"

    r = client.get("/api/snapshot/meta")
    assert r.status_code == 200
    meta = r.json()
    assert meta["width"] == 64 and meta["height"] == 48
    assert meta["frame_id"] >= 1


def test_state_endpoint(app_client):
    client, *_ = app_client
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    for key in ("threats", "pipeline_stats", "dispatcher_stats", "recent_alerts", "frame_id"):
        assert key in body


def test_zones_get_empty_then_put_then_get(app_client):
    client, app, zones_path, _ = app_client

    r = client.get("/api/zones")
    assert r.status_code == 200
    assert r.json() == {}

    polygon = {"porch": [[0, 0], [10, 0], [10, 10], [0, 10]]}
    r = client.put("/api/zones", json=polygon)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"ok": True, "zones": 1}

    # Disk persisted with proper structure
    assert zones_path.exists()
    on_disk = json.loads(zones_path.read_text(encoding="utf-8"))
    assert on_disk == polygon

    # Subsequent GET returns the saved data
    r = client.get("/api/zones")
    assert r.json() == polygon


def test_zones_put_rejects_bad_polygon(app_client):
    client, *_ = app_client
    r = client.put("/api/zones", json={"bad": [[0, 0], [1, 1]]})  # <3 vertices
    assert r.status_code == 422


def test_rules_round_trip(app_client):
    client, app, _, rules_path = app_client

    payload = {
        "rules": [
            {
                "name": "Critical anywhere",
                "description": "test",
                "severity": "critical",
                "cooldown_seconds": 5,
                "conditions": [{"class_name": "knife"}],
            }
        ]
    }
    r = client.put("/api/rules", json=payload)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "rules": 1}

    on_disk = json.loads(rules_path.read_text(encoding="utf-8"))
    assert on_disk["rules"][0]["name"] == "Critical anywhere"

    r = client.get("/api/rules")
    assert r.status_code == 200
    assert r.json()["rules"][0]["name"] == "Critical anywhere"


def test_rules_put_rejects_empty_conditions(app_client):
    client, *_ = app_client
    bad = {"rules": [{"name": "x", "conditions": []}]}
    r = client.put("/api/rules", json=bad)
    assert r.status_code == 422


def test_websocket_hello_and_snapshot(app_client):
    client, *_ = app_client
    with client.websocket_connect("/api/events") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert "severities" in hello["data"]
        assert hello["data"]["severities"] == ["low", "high", "critical"]

        # 5 Hz pump -> should receive a snapshot inside ~1 s
        deadline = time.monotonic() + 2.0
        saw_snapshot = False
        while time.monotonic() < deadline:
            msg = ws.receive_json()
            if msg["type"] == "snapshot":
                saw_snapshot = True
                assert "threats" in msg["data"]
                break
        assert saw_snapshot


def test_create_app_forwards_model_and_device_to_runner(monkeypatch, tmp_path):
    """Deployment config must reach the runner, not stop at create_app."""
    captured: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, state, **kwargs):
            captured.update(kwargs)

        def start(self, *_a, **_k):
            return None

        def stop(self, *_a, **_k):
            return None

    monkeypatch.setattr("web_layer.app.PipelineRunner", _FakeRunner)

    app = create_app(
        source=0,
        model_path="models/custom.pt",
        device="cpu",
        autostart_recorder=False,
        autostart_manager=False,
        zones_path=str(tmp_path / "zones.json"),
        rules_path=str(tmp_path / "rules.json"),
        jsonl_path=str(tmp_path / "alerts.jsonl"),
        static_dir=None,
    )

    with TestClient(app):
        pass

    assert captured["model_path"] == "models/custom.pt"
    assert captured["device"] == "cpu"
