"""
Zone Configuration (``zones.json``) format::

    {
        "driveway":   [[120, 400], [520, 400], [640, 720], [0, 720]],
        "porch":      [[200, 280], [440, 280], [440, 400], [200, 400]],
        "street_bg":  [[0, 0],    [640, 0],   [640, 240], [0, 240]]
    }

"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import supervision as sv

# Avoid a circular import: ThreatState lives in state_manager.
# We use TYPE_CHECKING so the hint is available to type-checkers
# without importing the module at runtime if it isn't already loaded.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from state_manager import ThreatState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sentinel written to ThreatState.active_zones when no zone file is loaded.
# ---------------------------------------------------------------------------
GLOBAL_ZONE = "global"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ZoneDefinition:
    """
    Fully resolved zone object, built once during engine initialisation.

    Attributes:
        name:   Human-readable zone label, sourced directly from the JSON key.
                Propagated into ``ThreatState.active_zones``.
        zone:   Compiled ``sv.PolygonZone`` instance pre-configured with the
                ``BOTTOM_CENTER`` triggering anchor.  Re-used every frame to
                avoid repeated allocations inside the evaluation loop.
        vertex_count: Stored for diagnostic / logging purposes only.
    """
    name:         str
    zone:         sv.PolygonZone
    vertex_count: int

class SpatialEngine:
    """
    Stateless, frame-driven spatial classifier for the Logic Layer.

    The engine is initialised once per process with a path to a ``zones.json``
    file.  On every frame the Main Thread calls ``evaluate(threats)``, which
    mutates each ``ThreatState.active_zones`` list in-place.

    Usage:

        engine = SpatialEngine(zones_path="config/zones.json")

        # Inside the Main Thread loop:
        confirmed = registry.get_confirmed_threats()
        engine.evaluate(confirmed)
        # Each ThreatState.active_zones is now populated.
        rule_evaluator.evaluate(confirmed)

    Lifecycle of ``active_zones`` per frame:

    1. **Cleared** at the start of every ``evaluate()`` call so stale zone
       memberships from the previous frame never persist.
    2. **Populated** by iterating through every loaded zone and running a
       batched ``sv.PolygonZone.trigger()`` call across all bboxes.
    3. **Fallback**: if a threat has no zone matches it receives ``["global"]``
       so downstream consumers always see a non-empty list.

    Attributes:
        zones_path:   Resolved ``pathlib.Path`` to the JSON config file.
        bypass:       ``True`` when the engine is operating in Bypass Mode.
        zone_count:   Number of valid zones loaded (0 in Bypass Mode).
    """

    def __init__(self, zones_path: str | Path = "config/zones.json") -> None:
        """
        Initialise the engine and compile all polygon zones.

        Args:
            zones_path: Path to the JSON zone-definition file.  Relative
                        paths are resolved from the current working directory.
                        If the file is missing or invalid the engine silently
                        enters Bypass Mode rather than raising an exception,
                        so the surveillance pipeline keeps running.
        """
        self.zones_path = Path(zones_path)
        self._zones:     list[ZoneDefinition] = []
        self.bypass:     bool  = False
        self.zone_count: int   = 0

        self._load_zones()

    # -----------------------------------------------------------------------
    # API
    # -----------------------------------------------------------------------

    def evaluate(self, threats: list["ThreatState"]) -> None:
        """
        Classify each confirmed threat by zone membership.

        This is the only method called by the Main Thread every frame.
        It mutates ``threat.active_zones`` in-place for every ``ThreatState``
        in the supplied list, then returns ``None``.  The caller's list
        reference is unaffected; only the *contents* of each object change.

        Bypass Mode behaviour:
            All threats are tagged ``["global"]`` and the method returns
            immediately with no further processing.

        Empty-list fast-path:
            If ``threats`` is empty the method returns immediately without
            allocating any intermediate arrays.

        Args:
            threats: List of ``ThreatState`` objects from
                     ``registry.get_confirmed_threats()``.  Each object must
                     expose a ``bbox`` attribute (numpy array, xyxy format)
                     and an ``active_zones`` attribute (``list[str]``).
        """
        # Clear stale zone data from previous frame
        for threat in threats:
            threat.active_zones.clear()

        if self.bypass:
            for threat in threats:
                threat.active_zones.append(GLOBAL_ZONE)
            return

        if not threats:
            return
        
        bboxes = np.array([t.bbox for t in threats], dtype=float)
        detections = sv.Detections(xyxy=bboxes)

        for zone_def in self._zones:
            mask: np.ndarray = zone_def.zone.trigger(detections)
            for idx, inside in enumerate(mask):
                if inside:
                    threats[idx].active_zones.append(zone_def.name)

        # Fallback: any threat with zero zone matches gets "global".
        # This guarantees rule_evaluator always receives a non-empty list.
        for threat in threats:
            if not threat.active_zones:
                threat.active_zones.append(GLOBAL_ZONE)
                logger.debug(
                    "SPATIAL   | ID %-4d | %-15s | no zone match -> global",
                    threat.tracker_id, threat.class_name,
                )

    def reload(self) -> bool:
        """
        Hot-reload the zone configuration from disk without restarting the
        process.

        Returns:
            ``True`` if reload succeeded and at least one zone was loaded.
            ``False`` if the file was missing/invalid (engine enters Bypass).
        """
        logger.info("SPATIAL   | Hot-reload triggered for: %s", self.zones_path)
        self._zones.clear()
        self._load_zones()
        return not self.bypass

    def diagnostics(self) -> dict:
        """
        Lightweight status snapshot for structured logging and debug UIs.

        Returns:
            A plain dict suitable for ``json.dumps()`` output, containing::

                {
                    "bypass":        bool,
                    "zone_count":    int,
                    "zones_path":    str,
                    "zones": [
                        {"name": "driveway", "vertices": 4},
                        ...
                    ]
                }
        """
        return {
            "bypass":     self.bypass,
            "zone_count": self.zone_count,
            "zones_path": str(self.zones_path),
            "zones": [
                {"name": z.name, "vertices": z.vertex_count}
                for z in self._zones
            ],
        }

    # -----------------------------------------------------------------------
    # Private - initialisation helpers
    # -----------------------------------------------------------------------

    def _load_zones(self) -> None:
        """
        Parse ``zones.json`` and compile ``ZoneDefinition`` objects.

        Failure modes handled gracefully (all trigger Bypass Mode):
          - File not found.
          - File exists but is not valid JSON.
          - JSON root is not a dict.
          - All polygon entries fail individual validation.

        Individual zone validation failures are logged as warnings and
        skipped; other zones in the same file continue to load normally.
        """
        raw = self._read_json()
        if raw is None:
            self._enter_bypass("zones.json absent or unreadable")
            return

        if not isinstance(raw, dict) or not raw:
            self._enter_bypass("zones.json is empty or not a JSON object")
            return

        for zone_name, vertices in raw.items():
            zone_def = self._build_zone(zone_name, vertices)
            if zone_def is not None:
                self._zones.append(zone_def)

        if not self._zones:
            self._enter_bypass("zones.json contained no valid polygon definitions")
            return

        self.bypass     = False
        self.zone_count = len(self._zones)
        logger.info(
            "SPATIAL   | Loaded %d zone(s) from %s: [%s]",
            self.zone_count,
            self.zones_path,
            ", ".join(z.name for z in self._zones),
        )

    def _read_json(self) -> Optional[dict]:
        """
        Read and parse the zones JSON file.

        Returns:
            Parsed Python object, or ``None`` on any I/O or parse failure.
        """
        if not self.zones_path.exists():
            logger.warning(
                "SPATIAL   | zones.json not found at '%s' — entering Bypass Mode.",
                self.zones_path,
            )
            return None
        try:
            with self.zones_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error(
                "SPATIAL   | zones.json parse error: %s — entering Bypass Mode.", exc
            )
            return None
        except OSError as exc:
            logger.error(
                "SPATIAL   | zones.json read error: %s — entering Bypass Mode.", exc
            )
            return None

    def _build_zone(
        self, name: str, vertices: object
    ) -> Optional[ZoneDefinition]:
        """
        Validate a single zone entry and compile it into a ``ZoneDefinition``.

        Validation rules:
          - ``vertices`` must be a list.
          - The list must contain at least 3 entries.
          - Each entry must be a list or tuple of exactly two numeric values.

        Args:
            name:     The zone's string key from the JSON file.
            vertices: The raw value associated with that key.

        Returns:
            A compiled ``ZoneDefinition``, or ``None`` if validation fails.
        """
        # Structural validation
        if not isinstance(vertices, list):
            logger.warning(
                "SPATIAL   | Zone '%s' skipped — vertices must be a list, got %s.",
                name, type(vertices).__name__,
            )
            return None

        if len(vertices) < 3:
            logger.warning(
                "SPATIAL   | Zone '%s' skipped — polygon needs ≥3 vertices, got %d.",
                name, len(vertices),
            )
            return None

        for i, point in enumerate(vertices):
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or not all(isinstance(c, (int, float)) for c in point)
            ):
                logger.warning(
                    "SPATIAL   | Zone '%s' skipped — vertex[%d] is not a valid "
                    "[x, y] pair: %r",
                    name, i, point,
                )
                return None

        # Compile supervision PolygonZone
        polygon = np.array(vertices, dtype=np.int64)
        zone = sv.PolygonZone(
            polygon=polygon,
            triggering_anchors=[sv.Position.BOTTOM_CENTER],
        )

        logger.debug(
            "SPATIAL   | Zone '%s' compiled — %d vertices.", name, len(vertices)
        )
        return ZoneDefinition(name=name, zone=zone, vertex_count=len(vertices))

    def _enter_bypass(self, reason: str) -> None:
        """Set Bypass Mode and emit a single INFO-level log entry."""
        self.bypass     = True
        self.zone_count = 0
        logger.info(
            "SPATIAL   | Bypass Mode active — %s. "
            "All threats will be tagged ['global'].",
            reason,
        )