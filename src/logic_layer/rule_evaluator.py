"""
Rule Schema Example:

    {
      "rules": [
        {
          "name":             "Porch Intruder",
          "description":      "Person on porch carrying an intrusion tool.",
          "cooldown_seconds": 30.0,
          "conditions": [
            { "class_name": "person", "zone": "porch", "min_confidence": 0.60 },
            { "is_critical": true }
          ]
        }
      ]
    }

Fail-Safe:
    If ``rules.json`` is missing, empty, or structurally invalid the engine
    enters **Bypass Mode**. ``evaluate()`` returns ``[]`` every frame and
    the main loop continues uninterrupted.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from state_manager import ThreatState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output payload - consumed by Alert Dispatcher and Agentic VLM
# ---------------------------------------------------------------------------

@dataclass
class TriggeredAlert:
    """
    Structured payload emitted when a rule fires.

    This is the sole output type of ``RuleEvaluator.evaluate()`` and the
    primary message type placed on the Agent Queue for Thread 3.

    Attributes:
        rule_name:    The ``name`` field of the rule that fired.  Used by the
                      dispatcher for notification routing and deduplication.
        triggered_at: Wall-clock timestamp (``time.time()``) at the moment
                      the rule fired.  Use for log correlation and display.
        tracker_ids:  Deduplicated list of ByteTrack IDs for every
                      ``ThreatState`` that satisfied at least one condition.
                      The Agentic VLM uses these IDs to crop the correct
                      bounding boxes from the burst frame buffer.
        threat_snapshots: Serialisable dict representation of each
                      contributing threat (via ``ThreatState.to_dict()``).
                      Provides the VLM with class labels, zones, and
                      confidence scores without passing live object references
                      across thread boundaries.
        rule_description: The optional ``description`` field from the JSON
                      rule definition.  Passed through verbatim.
    """
    rule_name:         str
    triggered_at:      float
    tracker_ids:       list[int]
    threat_snapshots:  list[dict]
    rule_description:  str = ""

    def to_dict(self) -> dict:
        """Fully serialisable snapshot for structured logging or queue transport."""
        return {
            "rule_name":        self.rule_name,
            "triggered_at":     self.triggered_at,
            "tracker_ids":      self.tracker_ids,
            "threat_snapshots": self.threat_snapshots,
            "rule_description": self.rule_description,
        }


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConditionSpec:
    """
    Compiled, validated representation of a single rule condition.

    All filter fields are optional.  A condition with no fields set is a
    "match-all" wildcard - it is always satisfied if any threat exists.
    The validator in ``_parse_condition`` rejects structurally empty
    conditions to prevent accidental wildcard rules.

    Attributes:
        class_name:     Exact YOLO class label to match, or ``None``.
        is_critical:    True/False, or ``None``.
        zone:           Zone name that must appear in ``active_zones``,
                        or ``None`` (any zone including "global" is accepted).
        min_confidence: Minimum confidence threshold, or ``None``.
    """
    class_name:     Optional[str]   = None
    is_critical:    Optional[bool]   = None
    zone:           Optional[str]   = None
    min_confidence: Optional[float] = None


@dataclass
class RuleDefinition:
    """
    Compiled, validated representation of a single rule.

    Attributes:
        name:             Unique rule identifier string.
        conditions:       Ordered list of ``ConditionSpec`` objects.  ALL
                          must be satisfied for the rule to fire (AND logic).
        cooldown_seconds: Minimum interval between successive alerts for
                          this rule.
        description:      Optional operator annotation.
    """
    name:             str
    conditions:       list[ConditionSpec]
    cooldown_seconds: float
    description:      str = ""


@dataclass
class FrameIndex:
    """
    Per-frame pre-computed index over the confirmed threat list.

    Built once at the start of each ``evaluate()`` call and discarded
    afterwards.  Reduces condition evaluation from O(N_threats) per
    condition to O(1) lookup + O(|candidates|) filter.

    Attributes:
        by_class:    Maps class label → list of matching ThreatStates.
        by_critical: Maps critical flag (True/False) → list of matching
                     ThreatStates.
        by_zone:     Maps zone name → list of matching ThreatStates.
                     A ThreatState appears under EVERY zone in its
                     ``active_zones`` list.
        all:         Unfiltered reference to the full confirmed threat list.
    """
    by_class:    dict[str,  list["ThreatState"]] = field(default_factory=dict)
    by_critical: dict[bool, list["ThreatState"]] = field(default_factory=dict)
    by_zone:     dict[str,  list["ThreatState"]] = field(default_factory=dict)
    all:         list["ThreatState"]             = field(default_factory=list)

class RuleEvaluator:
    """
    Compound rule engine for the Logic Layer.

    The evaluator is initialised once per process from a ``rules.json`` file.
    On every frame the Main Thread calls ``evaluate(threats)`` which returns a
    (possibly empty) list of ``TriggeredAlert`` objects.

    Evaluation model:
        A rule fires when **every** one of its conditions is independently
        satisfied by **at least one** ThreatState in the current frame.
        Multiple conditions may be satisfied by the **same** ThreatState
        (e.g. a critical weapon on the porch satisfies both an is_critical
        condition and a zone condition).  The ``tracker_ids`` in the resulting alert is the
        **union** of all contributing object IDs.

    Cooldown model:
        Each rule has its own independent cooldown clock keyed by rule name.
        The clock is updated only when the rule fires and an alert is emitted.
        Cooldown state is held in memory and resets on process restart.

    Usage::

        evaluator = RuleEvaluator(rules_path="config/rules.json")

        # Inside the Main Thread loop (after spatial_engine.evaluate):
        alerts = evaluator.evaluate(confirmed_threats)
        for alert in alerts:
            alert_dispatcher.send(alert)
            agent_queue.put(alert)

    Attributes:
        rules_path:  Resolved ``pathlib.Path`` to the JSON config file.
        bypass:      ``True`` when operating in Bypass Mode (no valid rules).
        rule_count:  Number of valid rules loaded (0 in Bypass Mode).
    """

    def __init__(self, rules_path: str | Path = "src/config/rules.json") -> None:
        """
        Initialise the evaluator and compile all rule definitions.

        Args:
            rules_path: Path to the JSON rule-definition file.  If the file
                        is absent or invalid the engine enters Bypass Mode
                        silently so the surveillance pipeline keeps running.
        """
        self.rules_path = Path(rules_path)
        self._rules:         list[RuleDefinition] = []
        self._cooldown_ledger: dict[str, float]   = {}
        self.bypass:     bool = False
        self.rule_count: int  = 0

        self._load_rules()

    # -----------------------------------------------------------------------
    # API
    # -----------------------------------------------------------------------

    def evaluate(self, threats: list["ThreatState"]) -> list[TriggeredAlert]:
        """
        Evaluate all loaded rules against the current frame's threat list.

        This is the sole method called by the Main Thread every frame.
        It is a pure read of ``threats``.

        Performance contract:
            - ``FrameIndex`` is built once: O(N_threats).
            - Each condition resolves via index lookup + small linear filter.
            - Short-circuits immediately if any condition yields zero matches.
            - Cooldown check is a single dict lookup: O(1).

        Args:
            threats: List of confirmed, spatially-tagged ``ThreatState``
                     objects from ``registry.get_confirmed_threats()``.
                     Each object must expose: ``tracker_id``, ``class_name``,
                     ``is_critical``, ``confidence``, ``active_zones``, ``to_dict()``.

        Returns:
            List of ``TriggeredAlert`` objects for every rule that fired this
            frame.  Returns ``[]`` in Bypass Mode or when no rules match.
        """
        if self.bypass or not threats:
            return []

        index  = self._build_index(threats)
        alerts = []
        now    = time.time()

        for rule in self._rules:
            alert = self._evaluate_rule(rule, index, now)
            if alert is not None:
                alerts.append(alert)
                self._cooldown_ledger[rule.name] = now
                logger.info(
                    "RULE_EVAL | %-25s | FIRED | ids=%s",
                    rule.name, alert.tracker_ids,
                )

        return alerts

    def reload(self) -> bool:
        """
        Hot-reload the rule configuration from disk.

        Preserves the existing cooldown ledger so an in-progress cooldown
        is not reset mid-deployment.  If the reload fails, the engine enters
        Bypass Mode and the ledger is retained for when a valid file is
        restored.

        Returns:
            ``True`` if at least one valid rule was loaded, ``False`` if the
            engine entered Bypass Mode.
        """
        logger.info("RULE_EVAL | Hot-reload triggered for: %s", self.rules_path)
        self._rules.clear()
        self._load_rules()
        return not self.bypass

    def active_cooldowns(self) -> dict[str, float]:
        """
        Return the remaining cooldown (seconds) for every rule currently
        in its cooldown window.

        Rules whose cooldown has expired are omitted.

        Returns:
            ``{ rule_name: seconds_remaining, ... }`` for active cooldowns.
        """
        now = time.time()
        result = {}
        for rule in self._rules:
            last_fired = self._cooldown_ledger.get(rule.name)
            if last_fired is not None:
                remaining = rule.cooldown_seconds - (now - last_fired)
                if remaining > 0:
                    result[rule.name] = round(remaining, 2)
        return result

    def diagnostics(self) -> dict:
        """
        Lightweight status snapshot for structured logging and debug UIs.

        Returns:
            A plain dict suitable for ``json.dumps()`` output.
        """
        return {
            "bypass":     self.bypass,
            "rule_count": self.rule_count,
            "rules_path": str(self.rules_path),
            "rules": [
                {
                    "name":             r.name,
                    "conditions":       len(r.conditions),
                    "cooldown_seconds": r.cooldown_seconds,
                }
                for r in self._rules
            ],
            "active_cooldowns": self.active_cooldowns(),
        }

    # ---------------------------------------------------------------------------
    # Private - rule evaluation
    # ---------------------------------------------------------------------------

    def _evaluate_rule(
        self,
        rule:  RuleDefinition,
        index: FrameIndex,
        now:   float,
    ) -> Optional[TriggeredAlert]:
        """
        Evaluate a single rule.  Returns a ``TriggeredAlert`` if it fires,
        ``None`` otherwise.

        Short-circuit ordering:
            1. Cooldown gate - cheapest check, single dict lookup.
            2. Condition evaluation - iterate conditions, resolve each via
               index, bail immediately on first empty result set.
            3. Alert construction - only reached when all conditions matched.
        """
        # Cooldown gate
        last_fired = self._cooldown_ledger.get(rule.name)
        if last_fired is not None:
            if (now - last_fired) < rule.cooldown_seconds:
                return None

        # Condition evaluation
        contributing: dict[int, "ThreatState"] = {}

        for condition in rule.conditions:
            matches = self._resolve_condition(condition, index)
            if not matches:
                return None
            for t in matches:
                contributing[t.tracker_id] = t

        # Build alert
        tracker_ids     = sorted(contributing.keys())
        threat_snapshots = [contributing[tid].to_dict() for tid in tracker_ids]

        return TriggeredAlert(
            rule_name        = rule.name,
            triggered_at     = now,
            tracker_ids      = tracker_ids,
            threat_snapshots = threat_snapshots,
            rule_description = rule.description,
        )

    def _resolve_condition(
        self,
        condition: ConditionSpec,
        index:     FrameIndex,
    ) -> list["ThreatState"]:
        """
        Find all ThreatStates in the frame that satisfy a single condition.

        Index selection strategy:
            Start from the most selective index available in priority order:
            ``class_name`` > ``zone`` > ``is_critical`` > ``all``.  Then apply
            any remaining field filters as a linear pass over that candidate
            set.  This minimises the number of objects touched per condition.

        Args:
            condition: The compiled condition spec to resolve.
            index:     The pre-built frame index for this evaluation cycle.

        Returns:
            List of matching ``ThreatState`` objects (may be empty).
        """
        # Select the best starting candidate set
        if condition.class_name is not None:
            candidates = index.by_class.get(condition.class_name, [])
        elif condition.zone is not None:
            candidates = index.by_zone.get(condition.zone, [])
        elif condition.is_critical is not None:
            candidates = index.by_critical.get(condition.is_critical, [])
        else:
            candidates = index.all

        if not candidates:
            return []

        # Apply remaining filters that weren't used for index selection
        result = []
        for threat in candidates:
            if condition.class_name is not None and threat.class_name != condition.class_name:
                continue
            if condition.is_critical is not None and threat.is_critical != condition.is_critical:
                continue
            if condition.zone is not None and condition.zone not in threat.active_zones:
                continue
            if condition.min_confidence is not None and threat.confidence < condition.min_confidence:
                continue
            result.append(threat)

        return result

    # ---------------------------------------------------------------------------
    # Private - FrameIndex construction
    # ---------------------------------------------------------------------------

    @staticmethod
    def _build_index(threats: list["ThreatState"]) -> FrameIndex:
        """
        Build a per-frame multi-key index over the confirmed threat list.

        Called once per ``evaluate()`` invocation.  All three index dicts are
        populated in a single O(N_threats x |active_zones|) pass.

        A ThreatState is inserted under EVERY zone in its ``active_zones``
        list so that zone-based conditions work correctly for objects in
        multiple overlapping zones (e.g. ``["porch", "front_yard"]``).
        """
        idx = FrameIndex(all=threats)

        for threat in threats:
            # Index by class
            idx.by_class.setdefault(threat.class_name, []).append(threat)

            # Index by critical flag
            idx.by_critical.setdefault(threat.is_critical, []).append(threat)

            # Index by every zone the threat currently occupies
            for zone_name in threat.active_zones:
                idx.by_zone.setdefault(zone_name, []).append(threat)

        return idx

    # ---------------------------------------------------------------------------
    # Private - configuration loading
    # ---------------------------------------------------------------------------

    def _load_rules(self) -> None:
        """
        Parse ``rules.json`` and compile ``RuleDefinition`` objects.

        Failure modes handled gracefully (all trigger Bypass Mode):
          - File not found.
          - File is not valid JSON.
          - JSON root is not a dict with a ``"rules"`` key.
          - The ``"rules"`` array is empty or missing.
          - All rule entries fail individual validation.

        Individual rule/condition validation failures are logged as warnings
        and skipped; the remaining rules in the file continue to load.
        """
        raw = self._read_json()
        if raw is None:
            self._enter_bypass("rules.json absent or unreadable")
            return

        if not isinstance(raw, dict) or "rules" not in raw:
            self._enter_bypass("rules.json must be a JSON object with a 'rules' key")
            return

        rules_raw = raw["rules"]
        if not isinstance(rules_raw, list) or not rules_raw:
            self._enter_bypass("'rules' array is missing or empty")
            return

        for entry in rules_raw:
            rule = self._parse_rule(entry)
            if rule is not None:
                self._rules.append(rule)

        if not self._rules:
            self._enter_bypass("rules.json contained no valid rule definitions")
            return

        self.bypass     = False
        self.rule_count = len(self._rules)
        logger.info(
            "RULE_EVAL | Loaded %d rule(s) from %s: [%s]",
            self.rule_count,
            self.rules_path,
            ", ".join(f'"{r.name}"' for r in self._rules),
        )

    def _read_json(self) -> Optional[dict]:
        """Read and parse the rules JSON file."""
        if not self.rules_path.exists():
            logger.warning(
                "RULE_EVAL | rules.json not found at '%s' - entering Bypass Mode.",
                self.rules_path,
            )
            return None
        try:
            with self.rules_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.error(
                "RULE_EVAL | rules.json parse error: %s - entering Bypass Mode.", exc
            )
            return None
        except OSError as exc:
            logger.error(
                "RULE_EVAL | rules.json read error: %s - entering Bypass Mode.", exc
            )
            return None

    def _parse_rule(self, entry: object) -> Optional[RuleDefinition]:
        """
        Validate and compile a single rule dict into a ``RuleDefinition``.

        Required fields:  ``name``, ``conditions``.
        Optional fields:  ``cooldown_seconds`` (default 30.0), ``description``.

        Args:
            entry: Raw JSON value for one rule entry.

        Returns:
            Compiled ``RuleDefinition`` or ``None`` if validation fails.
        """
        if not isinstance(entry, dict):
            logger.warning("RULE_EVAL | Skipping rule - entry is not a JSON object: %r", entry)
            return None

        # Required: name
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            logger.warning("RULE_EVAL | Skipping rule - missing or blank 'name': %r", entry)
            return None

        # Required: conditions
        conditions_raw = entry.get("conditions")
        if not isinstance(conditions_raw, list) or not conditions_raw:
            logger.warning(
                "RULE_EVAL | Rule '%s' skipped - 'conditions' must be a non-empty list.",
                name,
            )
            return None

        conditions = []
        for i, cond_raw in enumerate(conditions_raw):
            cond = self._parse_condition(name, i, cond_raw)
            if cond is None:
                return None   # Any invalid condition invalidates the entire rule.
            conditions.append(cond)

        # Optional: cooldown_seconds
        cooldown = entry.get("cooldown_seconds", 30.0)
        if not isinstance(cooldown, (int, float)) or cooldown < 0:
            logger.warning(
                "RULE_EVAL | Rule '%s' - invalid 'cooldown_seconds' %r; using 30.0.",
                name, cooldown,
            )
            cooldown = 30.0

        description = entry.get("description", "")

        return RuleDefinition(
            name             = name.strip(),
            conditions       = conditions,
            cooldown_seconds = float(cooldown),
            description      = str(description),
        )

    def _parse_condition(
        self, rule_name: str, idx: int, entry: object
    ) -> Optional[ConditionSpec]:
        """
        Validate and compile a single condition dict into a ``ConditionSpec``.

        Valid filter fields: ``class_name`` (str), ``is_critical`` (bool),
        ``zone`` (str), ``min_confidence`` (float 0.0-1.0).
        At least one field must be present.

        Args:
            rule_name: Parent rule name, for error messages only.
            idx:       Zero-based index of this condition, for error messages.
            entry:     Raw JSON value for one condition entry.

        Returns:
            Compiled ``ConditionSpec`` or ``None`` if validation fails.
        """
        prefix = f"RULE_EVAL | Rule '{rule_name}', condition[{idx}]"

        if not isinstance(entry, dict):
            logger.warning("%s - must be a JSON object, got %r", prefix, entry)
            return None

        class_name     = entry.get("class_name")
        is_critical    = entry.get("is_critical")
        zone           = entry.get("zone")
        min_confidence = entry.get("min_confidence")

        # Field-level validation
        if class_name is not None and not isinstance(class_name, str):
            logger.warning("%s - 'class_name' must be a string.", prefix)
            return None

        if is_critical is not None and not isinstance(is_critical, bool):
            logger.warning("%s - 'is_critical' must be a boolean.", prefix)
            return None

        if zone is not None and not isinstance(zone, str):
            logger.warning("%s - 'zone' must be a string.", prefix)
            return None

        if min_confidence is not None:
            if not isinstance(min_confidence, (int, float)) or not (0.0 <= min_confidence <= 1.0):
                logger.warning("%s - 'min_confidence' must be a float in [0.0, 1.0].", prefix)
                return None

        # Require at least one filter field
        if all(v is None for v in (class_name, is_critical, zone, min_confidence)):
            logger.warning(
                "%s - empty condition (no filter fields). "
                "Use at least one of: class_name, is_critical, zone, min_confidence.",
                prefix,
            )
            return None

        return ConditionSpec(
            class_name     = class_name,
            is_critical    = is_critical,
            zone           = zone,
            min_confidence = float(min_confidence) if min_confidence is not None else None,
        )

    def _enter_bypass(self, reason: str) -> None:
        """Activate Bypass Mode and emit a single INFO-level log entry."""
        self.bypass     = True
        self.rule_count = 0
        logger.info(
            "RULE_EVAL | Bypass Mode active - %s. "
            "evaluate() will return [] every frame.",
            reason,
        )