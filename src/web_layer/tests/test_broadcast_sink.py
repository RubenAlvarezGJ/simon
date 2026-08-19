"""Tests for BroadcastSink."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from web_layer.broadcast_sink import BroadcastSink
from web_layer.runtime_state import RuntimeState


@dataclass
class _StubAlert:
    rule_name: str = "test_rule"
    severity: str = "high"

    def to_dict(self) -> dict:
        return {"rule_name": self.rule_name, "severity": self.severity}


class TestBroadcastSink:
    def test_appends_to_recent_alerts(self) -> None:
        state = RuntimeState()
        sink = BroadcastSink(state)
        sink.deliver(_StubAlert("r1"))
        sink.deliver(_StubAlert("r2"))
        names = [a["rule_name"] for a in state.recent_alerts]
        assert names == ["r1", "r2"]

    def test_tallies_every_alert_by_severity(self) -> None:
        state = RuntimeState()
        sink = BroadcastSink(state)
        sink.deliver(_StubAlert("r1", "critical"))
        sink.deliver(_StubAlert("r2", "low"))
        sink.deliver(_StubAlert("r3", "critical"))
        assert state.alert_tally["counts"] == {"low": 1, "high": 0, "critical": 2}

    def test_tallies_with_no_loop_bound(self) -> None:
        # Alerts raised while the server is still booting must still count.
        state = RuntimeState()
        sink = BroadcastSink(state)
        sink.deliver(_StubAlert("early", "high"))
        assert state.alert_tally["counts"]["high"] == 1

    def test_no_loop_bound_still_appends(self) -> None:
        # event_loop=None must not raise.
        state = RuntimeState()
        sink = BroadcastSink(state)
        sink.deliver(_StubAlert("ok"))
        assert state.recent_alerts[-1] == {"rule_name": "ok", "severity": "high"}

    @pytest.mark.asyncio
    async def test_fanout_to_subscribers(self) -> None:
        state = RuntimeState()
        state.event_loop = asyncio.get_running_loop()
        sink = BroadcastSink(state)

        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state.add_subscriber(q1)
        state.add_subscriber(q2)

        sink.deliver(_StubAlert("hit"))
        # call_soon_threadsafe schedules onto the loop; yield to let it run.
        await asyncio.sleep(0)

        msg1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        msg2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        expected = {"type": "alert", "data": {"rule_name": "hit", "severity": "high"}}
        assert msg1 == expected
        assert msg2 == expected

    @pytest.mark.asyncio
    async def test_full_queue_drops_silently(self) -> None:
        state = RuntimeState()
        state.event_loop = asyncio.get_running_loop()
        sink = BroadcastSink(state)

        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        q.put_nowait({"sentinel": True})  # pre-fill so put_nowait fails
        state.add_subscriber(q)

        sink.deliver(_StubAlert("dropped"))
        await asyncio.sleep(0)

        # Queue still holds only the sentinel; alert was dropped silently.
        assert q.qsize() == 1
        assert q.get_nowait() == {"sentinel": True}
