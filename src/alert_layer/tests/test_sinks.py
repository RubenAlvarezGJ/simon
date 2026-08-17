import json
import logging
from unittest.mock import MagicMock

import pytest
import requests

from alert_layer import sinks as sinks_module
from alert_layer.sinks import ConsoleSink, JsonlSink, Sink, TelegramSink
from logic_layer.rule_evaluator import Severity, TriggeredAlert


# ===========================================================================
# Helpers
# ===========================================================================

def make_alert(
    rule_name: str = "TestRule",
    ids: list[int] | None = None,
    snapshots: list[dict] | None = None,
    rule_description: str = "unit test",
    severity: str = "critical",
) -> TriggeredAlert:
    return TriggeredAlert(
        rule_name=rule_name,
        triggered_at=1234567.890,
        tracker_ids=list(ids) if ids is not None else [7, 9],
        threat_snapshots=(
            snapshots
            if snapshots is not None
            else [{"tracker_id": 7, "class_name": "handgun"}]
        ),
        rule_description=rule_description,
        severity=Severity(severity),
    )


def snapshot(**overrides) -> dict:
    snap = {
        "tracker_id": 7,
        "class_name": "handgun",
        "active_zones": ["porch"],
    }
    snap.update(overrides)
    return snap


def build_telegram_sink(
    monkeypatch,
    token: str | None = "TEST_TOKEN",
    chat_id: str | None = "999",
    timeout: float = 5.0,
) -> TelegramSink:
    """
    Construct a TelegramSink with a controlled environment.

    Stubs ``load_dotenv`` so a real project ``.env`` can't repopulate the
    environment, then sets or clears the two credentials. The returned sink's
    ``_session`` is left untouched - tests that exercise the send path replace
    it with a mock.
    """
    monkeypatch.setattr(sinks_module, "load_dotenv", lambda *a, **k: False)
    for name, value in (("TELEGRAM_BOT_TOKEN", token), ("CHAT_ID", chat_id)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return TelegramSink(timeout=timeout)


# ===========================================================================
# Sink protocol
# ===========================================================================

class TestSinkProtocol:

    def test_all_sinks_satisfy_protocol(self, tmp_path):
        assert isinstance(ConsoleSink(), Sink)
        assert isinstance(JsonlSink(tmp_path / "x.jsonl"), Sink)


# ===========================================================================
# ConsoleSink
# ===========================================================================

class TestConsoleSink:

    def test_emits_one_info_record_per_alert(self, caplog):
        sink = ConsoleSink(logger_name="alert_layer.console.test_emits")
        with caplog.at_level(logging.INFO, logger="alert_layer.console.test_emits"):
            sink.deliver(make_alert("Critical: Weapon"))
        records = [r for r in caplog.records if r.name == "alert_layer.console.test_emits"]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO

    def test_record_contains_rule_name(self, caplog):
        sink = ConsoleSink(logger_name="alert_layer.console.test_contains")
        with caplog.at_level(logging.INFO, logger="alert_layer.console.test_contains"):
            sink.deliver(make_alert("My Rule"))
        assert "My Rule" in caplog.text


# ===========================================================================
# JsonlSink
# ===========================================================================

class TestJsonlSink:

    def test_writes_one_json_object_per_line(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        sink = JsonlSink(path)
        sink.deliver(make_alert("A"))
        sink.deliver(make_alert("B"))
        sink.close()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["rule_name"] == "A"
        assert parsed[1]["rule_name"] == "B"

    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "alerts.jsonl"
        sink = JsonlSink(path)
        sink.deliver(make_alert())
        sink.close()
        assert path.exists()

    def test_appends_across_reopens(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        first = JsonlSink(path)
        first.deliver(make_alert("first"))
        first.close()

        second = JsonlSink(path)
        second.deliver(make_alert("second"))
        second.close()

        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["rule_name"] == "first"
        assert json.loads(lines[1])["rule_name"] == "second"

    def test_close_is_idempotent(self, tmp_path):
        sink = JsonlSink(tmp_path / "alerts.jsonl")
        sink.close()
        sink.close()  # Must not raise.

    def test_deliver_after_close_is_silent_noop(self, tmp_path):
        path = tmp_path / "alerts.jsonl"
        sink = JsonlSink(path)
        sink.close()
        sink.deliver(make_alert())  # Must not raise.
        assert path.read_text(encoding="utf-8") == ""


# ===========================================================================
# TelegramSink
# ===========================================================================

class TestTelegramSinkBypass:
    """Missing credentials -> bypass mode, never touches the network."""

    def test_bypass_when_both_credentials_missing(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, token=None, chat_id=None)
        assert sink.bypass is True

    def test_bypass_when_only_token_missing(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, token=None, chat_id="999")
        assert sink.bypass is True

    def test_bypass_when_only_chat_id_missing(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, token="TOKEN", chat_id=None)
        assert sink.bypass is True

    def test_not_bypass_when_both_present(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        assert sink.bypass is False

    def test_bypass_deliver_is_silent_noop(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, token=None, chat_id=None)
        sink._session = MagicMock()
        sink.deliver(make_alert(snapshots=[snapshot()]))
        sink._session.post.assert_not_called()

    def test_bypass_logs_info_line(self, monkeypatch, caplog):
        with caplog.at_level(logging.INFO, logger="alert_layer.sinks"):
            build_telegram_sink(monkeypatch, token=None, chat_id=None)
        assert any("bypass mode" in r.message for r in caplog.records)


class TestTelegramSinkDelivery:
    """Send path: routed by severity, and the request is well-formed."""

    @staticmethod
    def _mock_session(sink) -> MagicMock:
        session = MagicMock()
        session.post.return_value = MagicMock()  # response with no-op raise_for_status
        sink._session = session
        return session

    def test_satisfies_sink_protocol(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        assert isinstance(sink, Sink)

    def test_delivers_critical_alert(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()], severity="critical"))
        session.post.assert_called_once()

    def test_delivers_high_alert(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()], severity="high"))
        session.post.assert_called_once()

    def test_skips_low_alert(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()], severity="low"))
        session.post.assert_not_called()

    def test_critical_enables_notification(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()], severity="critical"))
        payload = session.post.call_args.kwargs["json"]
        assert payload["disable_notification"] is False

    def test_high_silences_notification(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()], severity="high"))
        payload = session.post.call_args.kwargs["json"]
        assert payload["disable_notification"] is True

    def test_request_url_targets_sendmessage_with_token(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, token="ABC123")
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()]))
        url = session.post.call_args.args[0]
        assert url == "https://api.telegram.org/botABC123/sendMessage"

    def test_request_payload_has_chat_id_and_text(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, chat_id="555")
        session = self._mock_session(sink)
        sink.deliver(make_alert("weapon_rule", snapshots=[snapshot()]))
        payload = session.post.call_args.kwargs["json"]
        assert payload["chat_id"] == "555"
        assert "weapon_rule" in payload["text"]

    def test_passes_configured_timeout(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch, timeout=2.5)
        session = self._mock_session(sink)
        sink.deliver(make_alert(snapshots=[snapshot()]))
        assert session.post.call_args.kwargs["timeout"] == 2.5

    def test_http_error_propagates(self, monkeypatch):
        """Network/HTTP errors are NOT swallowed - dispatcher must see them."""
        sink = build_telegram_sink(monkeypatch)
        session = MagicMock()
        response = MagicMock()
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
        session.post.return_value = response
        sink._session = session
        with pytest.raises(requests.exceptions.HTTPError):
            sink.deliver(make_alert(snapshots=[snapshot()]))

    def test_connection_error_propagates(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = MagicMock()
        session.post.side_effect = requests.exceptions.ConnectionError("no route")
        sink._session = session
        with pytest.raises(requests.exceptions.ConnectionError):
            sink.deliver(make_alert(snapshots=[snapshot()]))


class TestTelegramSinkFormatting:
    """_format_message builds a useful plain-text body from the alert."""

    def test_includes_core_fields(self):
        alert = make_alert(
            "porch_weapon",
            ids=[7, 9],
            snapshots=[snapshot(class_name="knife", active_zones=["porch"])],
            rule_description="Knife on the porch",
        )
        body = TelegramSink._format_message(alert)
        assert "porch_weapon" in body
        assert "knife" in body
        assert "porch" in body
        assert "[7, 9]" in body
        assert "Knife on the porch" in body

    def test_header_reflects_severity(self):
        alert = make_alert(snapshots=[snapshot()], severity="high")
        body = TelegramSink._format_message(alert)
        assert body.startswith("HIGH DETECTION")

    def test_all_snapshots_drive_class_and_zone(self):
        alert = make_alert(
            snapshots=[
                snapshot(class_name="handgun", active_zones=["yard"]),
                snapshot(class_name="person", active_zones=["street"]),
            ],
        )
        body = TelegramSink._format_message(alert)
        assert "handgun" in body and "yard" in body
        assert "person" in body and "street" in body

    def test_omits_zone_line_when_no_zones(self):
        alert = make_alert(
            snapshots=[snapshot(active_zones=[])],
            rule_description="",
        )
        body = TelegramSink._format_message(alert)
        assert "Zone:" not in body


class TestTelegramSinkClose:

    def test_close_closes_session(self, monkeypatch):
        sink = build_telegram_sink(monkeypatch)
        session = MagicMock()
        sink._session = session
        sink.close()
        session.close.assert_called_once()
