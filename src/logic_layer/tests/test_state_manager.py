import time
import unittest

import numpy as np

from logic_layer.state_manager import (
    ActiveThreats,
    StateManagerConfig,
    ThreatStatus,
)

# ---------------------------------------------------------------------------
# Minimal sv.Detections stub. ActiveThreats reads only a handful of attributes,
# so a stand-in keeps these tests focused on state transitions rather than on
# building full detection objects.
# ---------------------------------------------------------------------------

class MockDetections:
    """Minimal sv.Detections stand-in for unit testing."""

    def __init__(
        self,
        tracker_ids: list[int],
        class_names: list[str],
        confidences: list[float] | None = None,
        bboxes:      list[list[float]] | None = None,
    ):
        self.tracker_id = np.array(tracker_ids, dtype=int) if tracker_ids else np.array([], dtype=int)
        self.class_id   = None
        self.confidence = np.array(confidences) if confidences else np.ones(len(tracker_ids))
        self.xyxy       = np.array(bboxes) if bboxes else np.zeros((len(tracker_ids), 4))
        self.data       = {"class_name": class_names} if class_names else {}


def empty_detections() -> MockDetections:
    return MockDetections([], [], [], [])


def make_detections(
    tracker_ids: list[int],
    class_names: list[str],
    confidences: list[float] | None = None,
) -> MockDetections:
    n = len(tracker_ids)
    return MockDetections(
        tracker_ids=tracker_ids,
        class_names=class_names,
        confidences=confidences or [0.9] * n,
        bboxes=[[10.0, 20.0, 50.0, 80.0]] * n,
    )




# ===========================================================================
# Test Cases
# ===========================================================================

class TestPendingDebounce(unittest.TestCase):
    """Objects must accumulate the required frame count before confirming."""

    def setUp(self):
        self.cfg = StateManagerConfig(
            confirm_frames=3,
            cooldown_seconds=5.0,
        )
        self.registry = ActiveThreats(config=self.cfg)

    def _pump(self, n_frames: int, tracker_id: int, class_name: str):
        """Feed the same detection for n_frames consecutive frames."""
        det = make_detections([tracker_id], [class_name])
        for _ in range(n_frames):
            self.registry.update(det)

    def test_object_starts_pending(self):
        det = make_detections([1], ["handgun"])
        self.registry.update(det)
        state = self.registry.get_by_tracker_id(1)
        self.assertIsNotNone(state)
        self.assertEqual(state.status, ThreatStatus.PENDING)

    def test_confirms_at_threshold(self):
        self._pump(self.cfg.confirm_frames, 1, "handgun")
        state = self.registry.get_by_tracker_id(1)
        self.assertEqual(state.status, ThreatStatus.CONFIRMED)

    def test_not_confirmed_before_threshold(self):
        self._pump(self.cfg.confirm_frames - 1, 1, "handgun")
        state = self.registry.get_by_tracker_id(1)
        self.assertEqual(state.status, ThreatStatus.PENDING)

    def test_any_class_uses_same_threshold(self):
        """The same confirmation threshold applies to every class."""
        self._pump(self.cfg.confirm_frames, 2, "crowbar")
        state = self.registry.get_by_tracker_id(2)
        self.assertEqual(state.status, ThreatStatus.CONFIRMED)


class TestNewlyConfirmed(unittest.TestCase):
    """get_newly_confirmed() returns only threats confirmed in the current frame."""

    def setUp(self):
        cfg = StateManagerConfig(confirm_frames=2)
        self.registry = ActiveThreats(config=cfg)

    def test_newly_confirmed_populated_on_threshold_frame(self):
        det = make_detections([10], ["handgun"])
        self.registry.update(det)
        self.assertEqual(len(self.registry.get_newly_confirmed()), 0)

        self.registry.update(det)  # frame 2 — hits threshold
        newly = self.registry.get_newly_confirmed()
        self.assertEqual(len(newly), 1)
        self.assertEqual(newly[0].tracker_id, 10)

    def test_newly_confirmed_cleared_next_frame(self):
        det = make_detections([10], ["handgun"])
        self.registry.update(det)
        self.registry.update(det)
        # Frame after confirmation — buffer must be cleared
        self.registry.update(det)
        self.assertEqual(len(self.registry.get_newly_confirmed()), 0)

    def test_multiple_objects_confirmed_same_frame(self):
        cfg = StateManagerConfig(confirm_frames=1)
        registry = ActiveThreats(config=cfg)
        det = make_detections([1, 2], ["handgun", "crowbar"])
        registry.update(det)
        newly = registry.get_newly_confirmed()
        self.assertEqual(len(newly), 2)


class TestPendingDiscard(unittest.TestCase):
    """PENDING objects that disappear before confirming should be silently dropped."""

    def setUp(self):
        cfg = StateManagerConfig(confirm_frames=5, cooldown_seconds=5.0)
        self.registry = ActiveThreats(config=cfg)

    def test_pending_discarded_when_absent(self):
        self.registry.update(make_detections([99], ["knife"]))
        self.assertEqual(self.registry.get_by_tracker_id(99).status, ThreatStatus.PENDING)

        # Object disappears — next frame has nothing
        self.registry.update(empty_detections())
        self.assertIsNone(self.registry.get_by_tracker_id(99))

    def test_pending_discard_does_not_enter_cooldown(self):
        self.registry.update(make_detections([99], ["knife"]))
        self.registry.update(empty_detections())
        # Registry should be empty — not in COOLDOWN
        self.assertEqual(len(self.registry.get_all()), 0)


class TestCooldown(unittest.TestCase):
    """CONFIRMED objects that vanish should enter COOLDOWN and eventually be purged."""

    def setUp(self):
        cfg = StateManagerConfig(
            confirm_frames=2,
            cooldown_seconds=0.1,   # Short duration for fast test
        )
        self.registry = ActiveThreats(config=cfg)
        det = make_detections([5], ["handgun"])
        self.registry.update(det)
        self.registry.update(det)   # Now CONFIRMED

    def test_confirmed_transitions_to_cooldown_when_absent(self):
        self.registry.update(empty_detections())
        state = self.registry.get_by_tracker_id(5)
        self.assertIsNotNone(state)
        self.assertEqual(state.status, ThreatStatus.COOLDOWN)

    def test_cooldown_entry_not_in_confirmed_list(self):
        self.registry.update(empty_detections())
        confirmed = self.registry.get_confirmed_threats()
        self.assertEqual(len(confirmed), 0)

    def test_expired_cooldown_purges_entry(self):
        self.registry.update(empty_detections())  # → COOLDOWN
        time.sleep(0.15)                            # Exceed cooldown_seconds=0.1
        self.registry.update(empty_detections())  # Purge check fires
        self.assertIsNone(self.registry.get_by_tracker_id(5))

    def test_active_cooldown_retains_entry(self):
        self.registry.update(empty_detections())  # → COOLDOWN
        # Don't sleep — cooldown still active
        self.registry.update(empty_detections())
        state = self.registry.get_by_tracker_id(5)
        self.assertIsNotNone(state)
        self.assertEqual(state.status, ThreatStatus.COOLDOWN)


class TestRevival(unittest.TestCase):
    """Objects re-entering frame during COOLDOWN should revive correctly."""

    def setUp(self):
        self.cfg = StateManagerConfig(
            confirm_frames=2,
            cooldown_seconds=5.0,
            revive_on_reentry=True,
        )
        self.registry = ActiveThreats(config=self.cfg)
        det = make_detections([7], ["handgun"])
        self.registry.update(det)
        self.registry.update(det)   # → CONFIRMED
        self.registry.update(empty_detections())  # → COOLDOWN

    def test_reentry_revives_to_confirmed(self):
        self.registry.update(make_detections([7], ["handgun"]))
        state = self.registry.get_by_tracker_id(7)
        self.assertEqual(state.status, ThreatStatus.CONFIRMED)

    def test_reentry_clears_cooldown_start(self):
        self.registry.update(make_detections([7], ["handgun"]))
        state = self.registry.get_by_tracker_id(7)
        self.assertIsNone(state.cooldown_start)

    def test_reentry_does_not_re_emit_newly_confirmed(self):
        """Revived objects should NOT appear in newly_confirmed (already alerted)."""
        self.registry.update(make_detections([7], ["handgun"]))
        self.assertEqual(len(self.registry.get_newly_confirmed()), 0)

    def test_no_revive_requires_full_debounce(self):
        cfg = StateManagerConfig(
            confirm_frames=3,
            cooldown_seconds=5.0,
            revive_on_reentry=False,
        )
        registry = ActiveThreats(config=cfg)
        det = make_detections([8], ["handgun"])
        registry.update(det)
        registry.update(det)
        registry.update(det)        # → CONFIRMED
        registry.update(empty_detections())  # → COOLDOWN

        registry.update(det)        # Re-entry → PENDING (not revived)
        self.assertEqual(registry.get_by_tracker_id(8).status, ThreatStatus.PENDING)


class TestAlertFired(unittest.TestCase):
    """mark_alert_fired() should prevent duplicate alert flags."""

    def setUp(self):
        cfg = StateManagerConfig(confirm_frames=1)
        self.registry = ActiveThreats(config=cfg)
        self.registry.update(make_detections([3], ["knife"]))

    def test_alert_not_fired_by_default(self):
        state = self.registry.get_by_tracker_id(3)
        self.assertFalse(state.alert_fired)

    def test_mark_alert_fired(self):
        self.registry.mark_alert_fired(3)
        self.assertTrue(self.registry.get_by_tracker_id(3).alert_fired)

    def test_mark_alert_fired_on_missing_id_is_safe(self):
        # Should not raise
        self.registry.mark_alert_fired(9999)


class TestSummary(unittest.TestCase):
    """summary() should accurately reflect registry state counts."""

    def test_summary_mixed_states(self):
        cfg = StateManagerConfig(confirm_frames=2)
        registry = ActiveThreats(config=cfg)

        # ID 1 will reach CONFIRMED after 2 frames; introduce ID 2 only on
        # frame 2 so it remains PENDING.
        registry.update(make_detections([1], ["handgun"]))
        registry.update(make_detections([1, 2], ["handgun", "crowbar"]))

        s = registry.summary()
        self.assertEqual(s["CONFIRMED"], 1)
        self.assertEqual(s["PENDING"], 1)
        self.assertEqual(s["COOLDOWN"], 0)
        self.assertEqual(s["total"], 2)


class TestReset(unittest.TestCase):
    """reset() should clear registry and newly_confirmed buffer."""

    def test_reset_clears_all(self):
        cfg = StateManagerConfig(confirm_frames=1)
        registry = ActiveThreats(config=cfg)
        registry.update(make_detections([1, 2, 3], ["handgun", "knife", "crowbar"]))
        self.assertEqual(len(registry.get_all()), 3)
        registry.reset()
        self.assertEqual(len(registry.get_all()), 0)
        self.assertEqual(len(registry.get_newly_confirmed()), 0)


class TestThreatStateProperties(unittest.TestCase):
    """ThreatState convenience properties behave correctly."""

    def test_age_seconds_increases(self):
        cfg = StateManagerConfig(confirm_frames=1)
        registry = ActiveThreats(config=cfg)
        registry.update(make_detections([1], ["handgun"]))
        state = registry.get_by_tracker_id(1)
        t0 = state.age_seconds
        time.sleep(0.05)
        self.assertGreater(state.age_seconds, t0)

    def test_to_dict_contains_required_keys(self):
        cfg = StateManagerConfig(confirm_frames=1)
        registry = ActiveThreats(config=cfg)
        registry.update(make_detections([1], ["handgun"]))
        d = registry.get_by_tracker_id(1).to_dict()
        for key in ("tracker_id", "class_name", "status",
                    "frame_count", "confidence", "bbox", "age_seconds", "alert_fired"):
            self.assertIn(key, d, f"Missing key: {key}")
        self.assertNotIn("is_critical", d)

    def test_cooldown_elapsed_zero_when_not_in_cooldown(self):
        cfg = StateManagerConfig(confirm_frames=1)
        registry = ActiveThreats(config=cfg)
        registry.update(make_detections([1], ["handgun"]))
        state = registry.get_by_tracker_id(1)
        self.assertEqual(state.cooldown_elapsed, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
