from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np
import supervision as sv

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

@dataclass(frozen=True)
class StateManagerConfig:
    """
    Configuration for the ActiveThreats registry.

    Per-tier confirm thresholds allow fast-tracking critical Tier 1 detections
    (weapons) while requiring more evidence for ambiguous Tier 3 objects.

    Args:
        tier1_confirm_frames:  Consecutive frames required to confirm a Tier 1
                               (lethal weapon) detection. Low value = fast alert.
        tier2_confirm_frames:  Consecutive frames for Tier 2 (intrusion tools).
        tier3_confirm_frames:  Consecutive frames for Tier 3
        
        cooldown_seconds:      Duration (seconds) a lost ID is retained in
                               COOLDOWN before being purged. Prevents re-alerting
                               on the same physical object re-entering frame.
        revive_on_reentry:     If True, a COOLDOWN ID that reappears is promoted
                               directly to CONFIRMED, skipping debounce. Safe
                               to enable when tracker ID stability is high.
    """
    tier1_confirm_frames: int   = 3
    tier2_confirm_frames: int   = 5
    tier3_confirm_frames: int   = 8

    cooldown_seconds:     float = 8.0
    revive_on_reentry:    bool  = True


# ------------------------------------------------------------------
# Map: maps class names to tiers
# ------------------------------------------------------------------

CLASS_TIER_MAP: dict[str, int] = {
    # Tier 1 — Lethal Weapons (Critical Priority)
    "handgun":       1,
    "long_gun":      1,
    "knife":         1,
    # Tier 2 — Intrusion Tools (High Priority)
    "crowbar":       2,
    "bolt_cutters":  2,
    "baseball_bat":  2,
    # Tier 3 — Concealment / Access (Contextual Priority)
    "ski_mask":      3,
    "face_covering": 3,
    "flashlight":    3,
    "ladder":        3,
}


# ------------------------------------------------------------------
# Data Structures
# ------------------------------------------------------------------

class ThreatStatus(Enum):
    """Lifecycle states for a tracked object within the registry."""
    PENDING   = auto()   # Visible, accumulating debounce frames
    CONFIRMED = auto()   # Debounce threshold met — active threat
    COOLDOWN  = auto()   # No longer visible, awaiting expiry before deletion


@dataclass
class ThreatState:
    """
    Complete state record for a single tracked object.

    Keyed by tracker_id in the ActiveThreats registry. All mutable fields
    are updated in-place each frame to avoid unnecessary object creation.

    Args:
        tracker_id:     Persistent ID assigned by ByteTrack.
        class_name:     YOLO class label ( "handgun", "crowbar", etc...).
        tier:           Priority tier resolved from CLASS_TIER_MAP.
        status:         Current lifecycle status (PENDING/CONFIRMED).
        frame_count:    Running count of frames this object has been visible.
                        Increments through PENDING → CONFIRMED.
        confidence:     Most recent detection confidence score [0.0, 1.0].
        bbox:           Most recent bounding box in xyxy format, shape (4,).
        first_seen_at:  Monotonic timestamp when the ID first appeared.
        last_seen_at:   Monotonic timestamp of the most recent detection.
        cooldown_start: Monotonic timestamp when COOLDOWN began. None otherwise.
        alert_fired:    Flipped to True by the alert dispatcher once the initial
                        notification is emitted. Prevents duplicate alerts on the
                        same object ID within its active lifetime.
    """
    tracker_id:    int
    class_name:    str
    tier:          int
    status:        ThreatStatus
    frame_count:   int
    confidence:    float
    bbox:          np.ndarray
    first_seen_at: float       = field(default_factory=time.monotonic)
    last_seen_at:  float       = field(default_factory=time.monotonic)
    cooldown_start: Optional[float] = None
    alert_fired:   bool        = False
    active_zones:  list[str]   = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def age_seconds(self) -> float:
        """Wall-clock seconds since this object was first detected."""
        return time.monotonic() - self.first_seen_at
    
    @property
    def cooldown_elapsed(self) -> float:
        """Seconds elapsed since cooldown began. 0.0 if not in cooldown."""
        if self.cooldown_start is None:
            return 0.0
        return time.monotonic() - self.cooldown_start
 
    @property
    def is_cooldown_expired(self, cooldown_duration: float = 8.0) -> bool:
        """
        True if the cooldown window has closed.
        NOTE: ActiveThreats passes its configured duration directly via
        _process_absent_ids rather than relying on this default.
        """
        return self.cooldown_elapsed >= cooldown_duration

    def to_dict(self) -> dict:
        """Serialisable snapshot for logging, the Agentic Layer, or debug UIs."""
        return {
            "tracker_id":   self.tracker_id,
            "class_name":   self.class_name,
            "tier":         self.tier,
            "status":       self.status.name,
            "frame_count":  self.frame_count,
            "confidence":   round(self.confidence, 4),
            "bbox":         self.bbox.tolist(),
            "age_seconds":  round(self.age_seconds, 2),
            "alert_fired":  self.alert_fired,
        }


# ------------------------------------------------------------------
# ActiveThreats Registry
# ------------------------------------------------------------------

class ActiveThreats:
    """
    Central threat registry for the Logic Layer.

    Usage (Main Thread, once per frame):

        registry = ActiveThreats(config=StateManagerConfig())

        # In your main loop, after reading from the output queue:
        registry.update(detections)

        # Feed confirmed threats downstream:
        for threat in registry.get_newly_confirmed():
            alert_dispatcher.queue(threat)

        # Feed full confirmed state to spatial + rule engines:
        confirmed = registry.get_confirmed_threats()

        NOTE: need to update this docstring to be consistent with other files
    """

    def __init__(
        self,
        config: StateManagerConfig = StateManagerConfig(),
        class_names: Optional[dict[int, str]] = None,
    ):
        """
        Args:
            config:       Tuning parameters (thresholds, cooldown duration).
            class_names:  Optional mapping from YOLO class index → string label,
                          e.g. {0: "handgun", 1: "crowbar"}.
                          If sv.Detections already carries class names in
                          detections.data["class_name"], this can be omitted.
        """
        self._config:            StateManagerConfig       = config
        self._class_names:       dict[int, str]           = class_names or {}
        self._registry:          dict[int, ThreatState]   = {}
        self._newly_confirmed:   list[ThreatState]        = []

        # Map tier -> confirm threshold for O(1) lookup during updates
        self._tier_thresholds: dict[int, int] = {
            1: config.tier1_confirm_frames,
            2: config.tier2_confirm_frames,
            3: config.tier3_confirm_frames,
        }

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def update(self, detections: sv.Detections) -> None:
        """
        Primary update method. Called once per frame from the Main Thread.

        Processing order:
          1. Clear the newly-confirmed buffer from the previous frame.
          2. Extract tracker IDs present in this frame.
          3. For each visible ID: create a new entry or advance its state.
          4. For each absent ID: transition to COOLDOWN or purge if expired.
          NOTE: Update for consistency
        """
        self._newly_confirmed.clear()
        active_ids: list[int] = self._extract_active_ids(detections)

        # Handle all currently visible detections
        for idx, tracker_id in enumerate(active_ids):
            class_name = self._resolve_class_name(detections, idx)
            confidence = (
                float(detections.confidence[idx])
                if detections.confidence is not None
                else 0.0
            )
            bbox = detections.xyxy[idx]

            if tracker_id not in self._registry:
                self._create_entry(tracker_id, class_name, confidence, bbox)
            else:
                self._advance_entry(tracker_id, class_name, confidence, bbox)

        
        # Process IDs absent this frame
        self._process_absent_ids(set(active_ids))

    def get_confirmed_threats(self) -> list[ThreatState]:
        """
        All currently CONFIRMED threats.
        Primary input for spatial_engine.py and rule_evaluator.py.
        """
        return [
            s for s in self._registry.values()
            if s.status == ThreatStatus.CONFIRMED
        ]

    def get_newly_confirmed(self) -> list[ThreatState]:
        """
        Threats that crossed the confirmation threshold THIS frame only.
        Consumed by the alert dispatcher to trigger notifications.
        This list is cleared at the start of every update() call.
        """
        return list(self._newly_confirmed)

    def get_by_tier(self, tier: int) -> list[ThreatState]:
        """All CONFIRMED threats belonging to a specific tier."""
        return [
            s for s in self._registry.values()
            if s.status == ThreatStatus.CONFIRMED and s.tier == tier
        ]

    def get_by_tracker_id(self, tracker_id: int) -> Optional[ThreatState]:
        """Direct registry lookup. Returns None if ID is not tracked."""
        return self._registry.get(tracker_id)

    def get_all(self) -> dict[int, ThreatState]:
        """Full registry snapshot. Useful for debug overlays and logging."""
        return dict(self._registry)

    def mark_alert_fired(self, tracker_id: int) -> None:
        """
        Called by the alert dispatcher after a notification is emitted.
        Prevents duplicate alerts for the same physical object within
        its active tracking lifetime.
        """
        if tracker_id in self._registry:
            self._registry[tracker_id].alert_fired = True

    def summary(self) -> dict:
        """
        Lightweight diagnostic snapshot for structured logging.

        Example output:
            {"PENDING": 2, "CONFIRMED": 1, "total": 3}
        """
        counts: dict[str, int] = {s.name: 0 for s in ThreatStatus}
        for entry in self._registry.values():
            counts[entry.status.name] += 1
        counts["total"] = len(self._registry)
        return counts

    def reset(self) -> None:
        """
        Clears the entire registry. Use when switching camera feeds or
        resuming after a long pause where stale IDs would be meaningless.
        """
        self._registry.clear()
        self._newly_confirmed.clear()
        logger.info("STATE_MANAGER | Registry cleared.")

    # ------------------------------------------------------------------
    # Private - State Transition Logic
    # ------------------------------------------------------------------

    def _create_entry(
        self,
        tracker_id: int,
        class_name:  str,
        confidence:  float,
        bbox:        np.ndarray,
    ) -> None:
        """
        Register a new tracker ID.

        Starts as PENDING in all cases, then immediately checks whether the
        configured threshold for this tier is already met at frame_count=1
        (i.e. threshold == 1).
        """
        tier = self._resolve_tier(class_name)
        entry = ThreatState(
            tracker_id  = tracker_id,
            class_name  = class_name,
            tier        = tier,
            status      = ThreatStatus.PENDING,
            frame_count = 1,
            confidence  = confidence,
            bbox        = bbox.copy(),
        )
        self._registry[tracker_id] = entry

        threshold = self._tier_thresholds.get(tier, self._config.tier3_confirm_frames)
        if entry.frame_count >= threshold:
            self._confirm_entry(entry)
        else:
            logger.debug(
                "PENDING   | ID %-4d | %-15s | Tier %d | conf=%.2f",
                tracker_id, class_name, tier, confidence,
            )

    def _advance_entry(
        self,
        tracker_id: int,
        class_name:  str,
        confidence:  float,
        bbox:        np.ndarray,
    ) -> None:
        """Update an existing registry entry based on its current status."""
        entry              = self._registry[tracker_id]
        entry.last_seen_at = time.monotonic()
        entry.confidence   = confidence
        entry.bbox         = bbox.copy()
        # Guard against rare ByteTrack re-ID class swaps on crowded scenes
        entry.class_name   = class_name
 
        if entry.status == ThreatStatus.COOLDOWN:
            self._revive_entry(entry)
 
        elif entry.status == ThreatStatus.PENDING:
            entry.frame_count += 1
            threshold = self._tier_thresholds.get(entry.tier, self._config.tier3_confirm_frames)
            if entry.frame_count >= threshold:
                self._confirm_entry(entry)
 
        elif entry.status == ThreatStatus.CONFIRMED:
            # Continue incrementing for dwell-time tracking
            entry.frame_count += 1

    def _confirm_entry(self, entry: ThreatState) -> None:
        """Promote a PENDING entry to CONFIRMED and buffer it as a new alert."""
        entry.status = ThreatStatus.CONFIRMED
        self._newly_confirmed.append(entry)
        logger.info(
            "CONFIRMED | ID %-4d | %-15s | Tier %d | conf=%.2f | frames=%d",
            entry.tracker_id, entry.class_name, entry.tier,
            entry.confidence, entry.frame_count,
        )

    def _revive_entry(self, entry: ThreatState) -> None:
        """
        Restore a COOLDOWN entry to CONFIRMED when it reappears in frame.
 
        Skips the debounce threshold because we already verified this object.
        The original alert_fired flag is preserved, the alert dispatcher
        should decide whether a re-entry warrants a second notification.
        """
        if self._config.revive_on_reentry:
            entry.status         = ThreatStatus.CONFIRMED
            entry.cooldown_start = None
            entry.frame_count   += 1
            logger.info(
                "REVIVED   | ID %-4d | %-15s | Tier %d | reappeared after cooldown",
                entry.tracker_id, entry.class_name, entry.tier,
            )
        else:
            # Treat re-entry as a fresh sighting requiring full debounce
            entry.status         = ThreatStatus.PENDING
            entry.cooldown_start = None
            entry.frame_count    = 1
            entry.alert_fired    = False
            logger.debug(
                "RE-PENDING| ID %-4d | %-15s | revive_on_reentry=False",
                entry.tracker_id, entry.class_name,
            )

    def _process_absent_ids(self, active_set: set[int]) -> None:
        """
        Transition or purge all registry entries not present this frame.
 
        Transition rules:
          PENDING   -> DELETE  (never confirmed; discard silently)
          CONFIRMED -> COOLDOWN (start expiry clock)
          COOLDOWN  -> DELETE  (if cooldown window has elapsed)
        """
        to_delete: list[int] = []
        now = time.monotonic()
 
        for tracker_id, entry in self._registry.items():
            if tracker_id in active_set:
                continue
 
            if entry.status == ThreatStatus.PENDING:
                to_delete.append(tracker_id)
                logger.debug(
                    "DISCARDED | ID %-4d | %-15s | never reached confirm threshold",
                    tracker_id, entry.class_name,
                )
 
            elif entry.status == ThreatStatus.CONFIRMED:
                entry.status         = ThreatStatus.COOLDOWN
                entry.cooldown_start = now
                logger.info(
                    "COOLDOWN  | ID %-4d | %-15s | Tier %d | last_seen=%.1fs ago",
                    tracker_id, entry.class_name, entry.tier,
                    now - entry.last_seen_at,
                )
 
            elif entry.status == ThreatStatus.COOLDOWN:
                if entry.cooldown_elapsed >= self._config.cooldown_seconds:
                    to_delete.append(tracker_id)
                    logger.info(
                        "PURGED    | ID %-4d | %-15s | cooldown expired after %.1fs",
                        tracker_id, entry.class_name,
                        self._config.cooldown_seconds,
                    )
 
        for tracker_id in to_delete:
            del self._registry[tracker_id]

    # ------------------------------------------------------------------
    # Private - Resolution Helpers
    # ------------------------------------------------------------------

    def _extract_active_ids(self, detections: sv.Detections) -> list[int]:
        """
        Extract tracker IDs from an sv.Detections object.
        Returns an empty list if ByteTrack has not yet assigned IDs.
        """
        if detections.tracker_id is None or len(detections.tracker_id) == 0:
            return []
        return detections.tracker_id.tolist()

    def _resolve_class_name(self, detections: sv.Detections, idx: int) -> str:
        """
        Resolve a string class label from an sv.Detections entry.

        Resolution priority:
          1. detections.data["class_name"] — populated by YOLO11 natively.
          2. self._class_names dict + detections.class_id — manual mapping.
          3. "unknown" — fallback to avoid hard crashes on unmapped classes.
        """
        if detections.data and "class_name" in detections.data:
            return str(detections.data["class_name"][idx])
        if detections.class_id is not None and self._class_names:
            class_idx = int(detections.class_id[idx])
            return self._class_names.get(class_idx, "unknown")
        return "unknown"

    def _resolve_tier(self, class_name: str) -> int:
        """
        Map a class label to its priority tier.
        Defaults to Tier 3 for any class not yet in CLASS_TIER_MAP,
        ensuring new/experimental classes are treated as contextual rather
        than silently dropped or elevated to critical priority.
        """
        return CLASS_TIER_MAP.get(class_name, 3)