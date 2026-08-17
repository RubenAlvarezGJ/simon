import threading
import time

import pytest

from alert_layer.dispatcher import AlertDispatcher
from logic_layer.rule_evaluator import TriggeredAlert


# ===========================================================================
# Helpers
# ===========================================================================

def make_alert(rule_name: str = "TestRule", ids: list[int] | None = None) -> TriggeredAlert:
    return TriggeredAlert(
        rule_name=rule_name,
        triggered_at=time.time(),
        tracker_ids=list(ids) if ids is not None else [1],
        threat_snapshots=[],
        rule_description="",
    )


class RecordingSink:
    """Captures every delivered alert. Signals an event after N alerts."""

    def __init__(self, expected: int = 0):
        self.received: list[TriggeredAlert] = []
        self._lock = threading.Lock()
        self._expected = expected
        self.done = threading.Event()

    def deliver(self, alert: TriggeredAlert) -> None:
        with self._lock:
            self.received.append(alert)
            if self._expected and len(self.received) >= self._expected:
                self.done.set()


class BoomSink:
    """Always raises - used to verify per-sink error isolation."""

    def __init__(self):
        self.calls = 0

    def deliver(self, alert: TriggeredAlert) -> None:
        self.calls += 1
        raise RuntimeError("boom")


class BlockingSink:
    """Blocks in deliver() until release() is called. For queue-full tests."""

    def __init__(self):
        self.entered = threading.Event()
        self._gate = threading.Event()
        self.received: list[TriggeredAlert] = []

    def deliver(self, alert: TriggeredAlert) -> None:
        self.entered.set()
        self._gate.wait(timeout=5.0)
        self.received.append(alert)

    def release(self) -> None:
        self._gate.set()


class CloseableSink:
    def __init__(self):
        self.closed = False

    def deliver(self, alert: TriggeredAlert) -> None:
        pass

    def close(self) -> None:
        self.closed = True


# ===========================================================================
# Lifecycle
# ===========================================================================

class TestLifecycle:

    def test_context_manager_starts_and_stops(self):
        with AlertDispatcher([]) as dispatcher:
            assert dispatcher.is_running is True
        assert dispatcher.is_running is False

    def test_start_twice_raises(self):
        dispatcher = AlertDispatcher([])
        dispatcher.start()
        try:
            with pytest.raises(RuntimeError):
                dispatcher.start()
        finally:
            dispatcher.stop()

    def test_stop_without_start_is_noop(self):
        dispatcher = AlertDispatcher([])
        dispatcher.stop()  # Must not raise.

    def test_stop_is_idempotent(self):
        dispatcher = AlertDispatcher([])
        dispatcher.start()
        dispatcher.stop()
        dispatcher.stop()  # Must not raise.

    def test_stop_invokes_close_on_closeable_sinks(self):
        sink = CloseableSink()
        with AlertDispatcher([sink]) as _:
            pass
        assert sink.closed is True


# ===========================================================================
# Dispatch behaviour
# ===========================================================================

class TestDispatch:

    def test_empty_list_is_noop(self):
        sink = RecordingSink()
        with AlertDispatcher([sink]) as dispatcher:
            dispatcher.dispatch([])
        assert sink.received == []
        assert dispatcher.stats["enqueued"] == 0

    def test_single_alert_reaches_sink(self):
        sink = RecordingSink(expected=1)
        with AlertDispatcher([sink]) as dispatcher:
            dispatcher.dispatch([make_alert("R1")])
            assert sink.done.wait(timeout=2.0)
        assert len(sink.received) == 1
        assert sink.received[0].rule_name == "R1"

    def test_alerts_delivered_in_order(self):
        sink = RecordingSink(expected=3)
        with AlertDispatcher([sink]) as dispatcher:
            dispatcher.dispatch([make_alert("A"), make_alert("B"), make_alert("C")])
            assert sink.done.wait(timeout=2.0)
        assert [a.rule_name for a in sink.received] == ["A", "B", "C"]

    def test_all_sinks_receive_each_alert(self):
        s1 = RecordingSink(expected=2)
        s2 = RecordingSink(expected=2)
        with AlertDispatcher([s1, s2]) as dispatcher:
            dispatcher.dispatch([make_alert("A"), make_alert("B")])
            assert s1.done.wait(timeout=2.0)
            assert s2.done.wait(timeout=2.0)
        assert [a.rule_name for a in s1.received] == ["A", "B"]
        assert [a.rule_name for a in s2.received] == ["A", "B"]

    def test_dispatch_before_start_warns_and_drops(self, caplog):
        sink = RecordingSink()
        dispatcher = AlertDispatcher([sink])
        dispatcher.dispatch([make_alert("X")])
        assert sink.received == []
        assert dispatcher.stats["enqueued"] == 0

    def test_dispatch_after_stop_warns_and_drops(self):
        sink = RecordingSink()
        dispatcher = AlertDispatcher([sink])
        dispatcher.start()
        dispatcher.stop()
        dispatcher.dispatch([make_alert("X")])
        # No delivery, no enqueue beyond what happened before stop.
        assert sink.received == []

    def test_stats_counters_increment(self):
        sink = RecordingSink(expected=2)
        with AlertDispatcher([sink]) as dispatcher:
            dispatcher.dispatch([make_alert("A"), make_alert("B")])
            assert sink.done.wait(timeout=2.0)
        assert dispatcher.stats["enqueued"] == 2
        assert dispatcher.stats["delivered"] == 2
        assert dispatcher.stats["dropped"] == 0
        assert dispatcher.stats["sink_errors"] == 0


# ===========================================================================
# Error isolation
# ===========================================================================

class TestSinkErrorIsolation:

    def test_failing_sink_does_not_kill_others(self):
        boom = BoomSink()
        ok = RecordingSink(expected=2)
        with AlertDispatcher([boom, ok]) as dispatcher:
            dispatcher.dispatch([make_alert("A"), make_alert("B")])
            assert ok.done.wait(timeout=2.0)

        assert boom.calls == 2
        assert [a.rule_name for a in ok.received] == ["A", "B"]
        assert dispatcher.stats["sink_errors"] == 2
        assert dispatcher.stats["delivered"] == 2

    def test_worker_survives_repeated_failures(self):
        boom = BoomSink()
        with AlertDispatcher([boom]) as dispatcher:
            for i in range(5):
                dispatcher.dispatch([make_alert(f"R{i}")])
            # Give the worker a moment to drain.
            deadline = time.monotonic() + 2.0
            while dispatcher.stats["delivered"] < 5 and time.monotonic() < deadline:
                time.sleep(0.02)

        assert boom.calls == 5
        assert dispatcher.stats["sink_errors"] == 5


# ===========================================================================
# Queue full handling
# ===========================================================================

class TestQueueFull:

    def test_drop_on_full_increments_dropped_counter(self):
        blocker = BlockingSink()
        dispatcher = AlertDispatcher([blocker], queue_size=2, drop_on_full=True)
        dispatcher.start()
        try:
            # First alert is pulled by the worker and parks inside deliver().
            dispatcher.dispatch([make_alert("first")])
            assert blocker.entered.wait(timeout=2.0)

            # Now the worker is blocked. Fill the queue plus three extras.
            dispatcher.dispatch([make_alert(f"n{i}") for i in range(5)])

            # Queue accepted 2, dropped 3.
            assert dispatcher.stats["dropped"] == 3
            # 1 in-flight + 2 queued = 3 successfully enqueued.
            assert dispatcher.stats["enqueued"] == 3
        finally:
            blocker.release()
            dispatcher.stop()
