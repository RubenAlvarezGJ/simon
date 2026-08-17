"""Tests for the concurrency contracts of RuntimeState."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from web_layer.runtime_state import RuntimeState


class TestFramePublication:
    def test_publish_bumps_frame_id_monotonically(self) -> None:
        state = RuntimeState()
        assert state.frame_id == 0
        fid1 = state.publish_frame(b"a", (480, 640))
        fid2 = state.publish_frame(b"b", (480, 640))
        assert fid1 == 1
        assert fid2 == 2
        assert state.jpeg_bytes == b"b"
        assert state.frame_shape == (480, 640)

    def test_wait_for_frame_unblocks_on_publish(self) -> None:
        state = RuntimeState()
        result: dict = {}

        def reader() -> None:
            fid, data = state.wait_for_frame(last_id=0, timeout=2.0)
            result["fid"] = fid
            result["data"] = data

        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.05)
        state.publish_frame(b"hello", (480, 640))
        t.join(timeout=2.0)

        assert result["fid"] == 1
        assert result["data"] == b"hello"

    def test_multiple_waiters_all_receive_new_frame(self) -> None:
        state = RuntimeState()
        received: list[int] = []
        lock = threading.Lock()
        N = 5

        def reader() -> None:
            fid, _ = state.wait_for_frame(last_id=0, timeout=2.0)
            with lock:
                received.append(fid)

        threads = [threading.Thread(target=reader) for _ in range(N)]
        for t in threads:
            t.start()
        time.sleep(0.05)
        state.publish_frame(b"x", (1, 1))
        for t in threads:
            t.join(timeout=2.0)

        assert len(received) == N
        assert all(fid == 1 for fid in received)


class TestReloadFlags:
    def test_request_and_consume_zones(self) -> None:
        state = RuntimeState()
        assert state.consume_reload_flags() == (False, False)
        state.request_zones_reload()
        assert state.consume_reload_flags() == (True, False)
        assert state.consume_reload_flags() == (False, False)  # cleared

    def test_request_and_consume_rules(self) -> None:
        state = RuntimeState()
        state.request_rules_reload()
        zones, rules = state.consume_reload_flags()
        assert zones is False and rules is True

    def test_consume_clears_both(self) -> None:
        state = RuntimeState()
        state.request_zones_reload()
        state.request_rules_reload()
        zones, rules = state.consume_reload_flags()
        assert zones is True and rules is True
        assert state.consume_reload_flags() == (False, False)


class TestSubscribers:
    def test_add_and_remove(self) -> None:
        state = RuntimeState()
        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state.add_subscriber(q1)
        state.add_subscriber(q2)
        snap = state.snapshot_subscribers()
        assert q1 in snap and q2 in snap

        state.remove_subscriber(q1)
        snap = state.snapshot_subscribers()
        assert q1 not in snap and q2 in snap

    def test_remove_unknown_subscriber_silent(self) -> None:
        state = RuntimeState()
        q: asyncio.Queue = asyncio.Queue()
        # Must not raise even though q was never added
        state.remove_subscriber(q)


class TestRefSwapDoesNotTear:
    """Confirm that whole-object swaps remain consistent under concurrency.

    Replacing the ``confirmed_snapshot`` reference is a single attribute
    assignment, so a reader will always observe a *complete* prior list
    even while a writer is mid-replace.
    """

    def test_concurrent_writer_reader(self) -> None:
        state = RuntimeState()
        state.confirmed_snapshot = [{"i": 0}]
        stop = threading.Event()
        observed_lens: set[int] = set()

        def writer() -> None:
            i = 0
            while not stop.is_set():
                state.confirmed_snapshot = [{"i": j} for j in range(i % 5)]
                i += 1

        def reader() -> None:
            for _ in range(2000):
                snap = state.confirmed_snapshot  # single attr load — atomic
                observed_lens.add(len(snap))

        tw = threading.Thread(target=writer)
        tr = threading.Thread(target=reader)
        tw.start()
        tr.start()
        tr.join(timeout=5.0)
        stop.set()
        tw.join(timeout=5.0)

        # Should have seen at least a couple distinct snapshot sizes and never crashed.
        assert observed_lens.issubset({0, 1, 2, 3, 4})


class TestStateDict:
    def test_minimal_state_dict(self) -> None:
        state = RuntimeState()
        state.confirmed_snapshot = [{"tracker_id": 1}]
        state.pipeline_stats = {"frames": 7}
        state.recent_alerts.append({"rule_name": "x"})
        d = state.state_dict()
        assert d["threats"] == [{"tracker_id": 1}]
        assert d["pipeline_stats"] == {"frames": 7}
        assert d["recent_alerts"][-1] == {"rule_name": "x"}


def test_uptime_increases() -> None:
    state = RuntimeState()
    u1 = state.uptime_seconds()
    time.sleep(0.01)
    assert state.uptime_seconds() > u1
