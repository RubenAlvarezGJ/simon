import json
import os
import time

import pytest

from logic_layer.rule_evaluator import (
    RuleEvaluator,
    TriggeredAlert,
    ConditionSpec,
    RuleDefinition,
    Severity,
)


# ===========================================================================
# MockThreatState stub
# ===========================================================================

class MockThreatState:
    """Minimal ThreatState stand-in satisfying the RuleEvaluator's read contract."""

    def __init__(
        self,
        tracker_id:   int,
        class_name:   str,
        confidence:   float = 0.90,
        active_zones: list[str] | None = None,
    ):
        self.tracker_id   = tracker_id
        self.class_name   = class_name
        self.confidence   = confidence
        self.active_zones = active_zones if active_zones is not None else ["global"]

    def to_dict(self) -> dict:
        return {
            "tracker_id":   self.tracker_id,
            "class_name":   self.class_name,
            "confidence":   self.confidence,
            "active_zones": self.active_zones,
        }

    def __repr__(self):
        return (
            f"MockThreat(id={self.tracker_id}, cls={self.class_name!r}, "
            f"zones={self.active_zones})"
        )


# ===========================================================================
# Helpers
# ===========================================================================

def write_rules(tmp_path, data: dict) -> str:
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def single_rule(
    conditions: list[dict],
    cooldown: float = 30.0,
    name: str = "TestRule",
    severity: str | None = None,
) -> dict:
    rule = {"name": name, "conditions": conditions, "cooldown_seconds": cooldown}
    if severity is not None:
        rule["severity"] = severity
    return {"rules": [rule]}


# ===========================================================================
# Bypass Mode
# ===========================================================================

class TestBypassMode:

    def test_missing_file_activates_bypass(self, tmp_path):
        ev = RuleEvaluator(rules_path=str(tmp_path / "nope.json"))
        assert ev.bypass is True
        assert ev.rule_count == 0

    def test_invalid_json_activates_bypass(self, tmp_path):
        p = tmp_path / "rules.json"
        p.write_text("not json {{", encoding="utf-8")
        ev = RuleEvaluator(rules_path=str(p))
        assert ev.bypass is True

    def test_empty_rules_array_activates_bypass(self, tmp_path):
        path = write_rules(tmp_path, {"rules": []})
        ev = RuleEvaluator(rules_path=path)
        assert ev.bypass is True

    def test_missing_rules_key_activates_bypass(self, tmp_path):
        path = write_rules(tmp_path, {"not_rules": []})
        ev = RuleEvaluator(rules_path=path)
        assert ev.bypass is True

    def test_bypass_evaluate_returns_empty_list(self, tmp_path):
        ev = RuleEvaluator(rules_path=str(tmp_path / "nope.json"))
        threats = [MockThreatState(1, "handgun")]
        assert ev.evaluate(threats) == []

    def test_empty_threat_list_returns_empty(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        assert ev.evaluate([]) == []


# ===========================================================================
# Rule Loading & Validation
# ===========================================================================

class TestRuleLoading:

    def test_valid_rule_loads(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        assert ev.bypass is False
        assert ev.rule_count == 1

    def test_multiple_rules_loaded(self, tmp_path):
        data = {"rules": [
            {"name": "R1", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 10},
            {"name": "R2", "conditions": [{"class_name": "crowbar"}], "cooldown_seconds": 20},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.rule_count == 2

    def test_rule_missing_name_skipped(self, tmp_path):
        data = {"rules": [
            {"conditions": [{"class_name": "handgun"}]},          # no name — invalid
            {"name": "Good", "conditions": [{"class_name": "crowbar"}]},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.rule_count == 1
        assert ev._rules[0].name == "Good"

    def test_rule_missing_conditions_skipped(self, tmp_path):
        data = {"rules": [
            {"name": "Bad"},
            {"name": "Good", "conditions": [{"class_name": "handgun"}]},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.rule_count == 1

    def test_rule_empty_conditions_skipped(self, tmp_path):
        data = {"rules": [{"name": "Bad", "conditions": []}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.bypass is True

    def test_default_cooldown_applied(self, tmp_path):
        data = {"rules": [{"name": "R", "conditions": [{"class_name": "handgun"}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev._rules[0].cooldown_seconds == 30.0

    def test_invalid_cooldown_uses_default(self, tmp_path):
        data = {"rules": [{"name": "R", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": -5}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev._rules[0].cooldown_seconds == 30.0

    def test_description_preserved(self, tmp_path):
        data = {"rules": [{"name": "R", "description": "My rule", "conditions": [{"class_name": "handgun"}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev._rules[0].description == "My rule"


# ===========================================================================
# Severity parsing
# ===========================================================================

class TestSeverityParsing:

    @pytest.mark.parametrize("level", ["low", "high", "critical"])
    def test_explicit_severity_parsed(self, tmp_path, level):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}], severity=level))
        ev = RuleEvaluator(rules_path=path)
        assert ev._rules[0].severity == Severity(level)

    def test_missing_severity_defaults_to_high(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        assert ev._rules[0].severity == Severity.HIGH

    def test_invalid_severity_defaults_to_high_without_bypass(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}], severity="urgent"))
        ev = RuleEvaluator(rules_path=path)
        assert ev.bypass is False
        assert ev.rule_count == 1
        assert ev._rules[0].severity == Severity.HIGH

    def test_severity_is_case_insensitive(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}], severity="CRITICAL"))
        ev = RuleEvaluator(rules_path=path)
        assert ev._rules[0].severity == Severity.CRITICAL

    def test_severity_propagates_to_alert(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}], severity="critical"))
        ev = RuleEvaluator(rules_path=path)
        alerts = ev.evaluate([MockThreatState(1, "handgun")])
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.CRITICAL

    def test_default_severity_propagates_to_alert(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        alerts = ev.evaluate([MockThreatState(1, "handgun")])
        assert alerts[0].severity == Severity.HIGH


# ===========================================================================
# Condition Validation
# ===========================================================================

class TestConditionValidation:

    def test_empty_condition_invalidates_rule(self, tmp_path):
        data = {"rules": [{"name": "Bad", "conditions": [{}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.bypass is True

    def test_only_unknown_field_invalidates_rule(self, tmp_path):
        # is_critical is no longer a recognised filter; a condition carrying
        # only unknown fields is structurally empty and invalidates the rule.
        data = {"rules": [{"name": "Bad", "conditions": [{"is_critical": True}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.bypass is True

    def test_invalid_confidence_invalidates_rule(self, tmp_path):
        data = {"rules": [{"name": "Bad", "conditions": [{"min_confidence": 1.5}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.bypass is True

    def test_class_name_non_string_invalidates_rule(self, tmp_path):
        data = {"rules": [{"name": "Bad", "conditions": [{"class_name": 42}]}]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        assert ev.bypass is True

    def test_all_valid_fields_accepted(self, tmp_path):
        cond = {"class_name": "person", "zone": "porch", "min_confidence": 0.6}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([cond])))
        assert ev.bypass is False


# ===========================================================================
# Evaluation — Single Condition Rules
# ===========================================================================

class TestSingleConditionEvaluation:

    def test_class_name_match_fires(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun"}])))
        threats = [MockThreatState(1, "handgun")]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "TestRule"

    def test_class_name_no_match(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun"}])))
        threats = [MockThreatState(1, "crowbar")]
        assert ev.evaluate(threats) == []

    def test_zone_match_fires(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"zone": "porch"}])))
        threats = [MockThreatState(1, "crowbar", active_zones=["porch"])]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1

    def test_zone_no_match(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"zone": "porch"}])))
        threats = [MockThreatState(1, "crowbar", active_zones=["driveway"])]
        assert ev.evaluate(threats) == []

    def test_min_confidence_above_threshold_fires(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun", "min_confidence": 0.7}])))
        threats = [MockThreatState(1, "handgun", confidence=0.85)]
        assert len(ev.evaluate(threats)) == 1

    def test_min_confidence_below_threshold_no_fire(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun", "min_confidence": 0.7}])))
        threats = [MockThreatState(1, "handgun", confidence=0.50)]
        assert ev.evaluate(threats) == []

    def test_exactly_at_confidence_threshold_fires(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun", "min_confidence": 0.7}])))
        threats = [MockThreatState(1, "handgun", confidence=0.70)]
        assert len(ev.evaluate(threats)) == 1


# ===========================================================================
# Evaluation — Compound Rules (AND logic)
# ===========================================================================

class TestCompoundRuleEvaluation:

    def test_both_conditions_satisfied_fires(self, tmp_path):
        """Person on porch AND a tool present: both present → fires."""
        rule = single_rule([
            {"class_name": "person", "zone": "porch"},
            {"class_name": "crowbar"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [
            MockThreatState(1, "person",  active_zones=["porch"]),
            MockThreatState(2, "crowbar", active_zones=["global"]),
        ]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1

    def test_first_condition_missing_does_not_fire(self, tmp_path):
        rule = single_rule([
            {"class_name": "person", "zone": "porch"},
            {"class_name": "crowbar"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        # No person on porch
        threats = [MockThreatState(2, "crowbar", active_zones=["global"])]
        assert ev.evaluate(threats) == []

    def test_second_condition_missing_does_not_fire(self, tmp_path):
        rule = single_rule([
            {"class_name": "person", "zone": "porch"},
            {"class_name": "handgun"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        # Person on porch but no weapon
        threats = [MockThreatState(1, "person", active_zones=["porch"])]
        assert ev.evaluate(threats) == []

    def test_single_threat_satisfies_multiple_conditions(self, tmp_path):
        """One object can satisfy both conditions in a compound rule."""
        rule = single_rule([
            {"class_name": "crowbar"},
            {"zone": "porch"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [MockThreatState(1, "crowbar", active_zones=["porch"])]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1
        assert alerts[0].tracker_ids == [1]

    def test_three_condition_rule_all_satisfied(self, tmp_path):
        rule = single_rule([
            {"class_name": "person"},
            {"class_name": "handgun"},
            {"zone": "driveway"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [
            MockThreatState(1, "person",  active_zones=["driveway"]),
            MockThreatState(2, "handgun", active_zones=["driveway"]),
        ]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1

    def test_three_condition_rule_one_unsatisfied(self, tmp_path):
        rule = single_rule([
            {"class_name": "person"},
            {"class_name": "handgun"},
            {"zone": "driveway"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        # No weapon present
        threats = [
            MockThreatState(1, "person",  active_zones=["driveway"]),
            MockThreatState(2, "crowbar", active_zones=["driveway"]),
        ]
        assert ev.evaluate(threats) == []


# ===========================================================================
# TriggeredAlert Payload
# ===========================================================================

class TestTriggeredAlertPayload:

    def _fire(self, tmp_path, threats) -> TriggeredAlert:
        rule = single_rule([{"class_name": "handgun"}])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1
        return alerts[0]

    def test_alert_contains_correct_rule_name(self, tmp_path):
        alert = self._fire(tmp_path, [MockThreatState(1, "handgun")])
        assert alert.rule_name == "TestRule"

    def test_alert_triggered_at_is_recent(self, tmp_path):
        before = time.time()
        alert  = self._fire(tmp_path, [MockThreatState(1, "handgun")])
        after  = time.time()
        assert before <= alert.triggered_at <= after

    def test_alert_contains_correct_tracker_ids(self, tmp_path):
        alert = self._fire(tmp_path, [MockThreatState(7, "handgun")])
        assert alert.tracker_ids == [7]

    def test_alert_tracker_ids_are_sorted(self, tmp_path):
        rule = single_rule([{"class_name": "handgun"}])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [
            MockThreatState(5, "handgun"),
            MockThreatState(2, "handgun"),
            MockThreatState(9, "handgun"),
        ]
        alerts = ev.evaluate(threats)
        assert alerts[0].tracker_ids == [2, 5, 9]

    def test_alert_threat_snapshots_populated(self, tmp_path):
        alert = self._fire(tmp_path, [MockThreatState(1, "handgun")])
        assert len(alert.threat_snapshots) == 1
        assert alert.threat_snapshots[0]["tracker_id"] == 1
        assert alert.threat_snapshots[0]["class_name"] == "handgun"

    def test_alert_to_dict_includes_severity(self, tmp_path):
        alert = self._fire(tmp_path, [MockThreatState(1, "handgun")])
        d = alert.to_dict()
        assert d["severity"] == "high"

    def test_alert_to_dict_is_json_serialisable(self, tmp_path):
        import json
        alert = self._fire(tmp_path, [MockThreatState(1, "handgun")])
        json.dumps(alert.to_dict())  # Must not raise

    def test_compound_rule_union_of_tracker_ids(self, tmp_path):
        """All contributing threat IDs from all conditions must be in the alert."""
        rule = single_rule([
            {"class_name": "person", "zone": "porch"},
            {"class_name": "crowbar"},
        ])
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [
            MockThreatState(10, "person",  active_zones=["porch"]),
            MockThreatState(20, "crowbar"),
        ]
        alerts = ev.evaluate(threats)
        assert set(alerts[0].tracker_ids) == {10, 20}


# ===========================================================================
# Cooldown
# ===========================================================================

class TestCooldown:

    def test_rule_does_not_fire_within_cooldown(self, tmp_path):
        rule = single_rule([{"class_name": "handgun"}], cooldown=60.0)
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [MockThreatState(1, "handgun")]

        first  = ev.evaluate(threats)
        second = ev.evaluate(threats)

        assert len(first)  == 1
        assert len(second) == 0

    def test_rule_fires_again_after_cooldown_expires(self, tmp_path):
        rule = single_rule([{"class_name": "handgun"}], cooldown=0.05)
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        threats = [MockThreatState(1, "handgun")]

        ev.evaluate(threats)
        time.sleep(0.07)          # Exceed 0.05 s cooldown
        second = ev.evaluate(threats)

        assert len(second) == 1

    def test_cooldown_is_per_rule_independent(self, tmp_path):
        """Two rules with independent cooldowns should behave independently."""
        data = {"rules": [
            {"name": "R1", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 60.0},
            {"name": "R2", "conditions": [{"class_name": "crowbar"}], "cooldown_seconds": 60.0},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))

        threats = [
            MockThreatState(1, "handgun"),
            MockThreatState(2, "crowbar"),
        ]

        first = ev.evaluate(threats)   # Both fire
        assert len(first) == 2

        second = ev.evaluate(threats)  # Both in cooldown
        assert len(second) == 0

    def test_active_cooldowns_returns_remaining(self, tmp_path):
        rule = single_rule([{"class_name": "handgun"}], cooldown=60.0)
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        ev.evaluate([MockThreatState(1, "handgun")])

        cd = ev.active_cooldowns()
        assert "TestRule" in cd
        assert 0 < cd["TestRule"] <= 60.0

    def test_active_cooldowns_empty_before_any_fire(self, tmp_path):
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, single_rule([{"class_name": "handgun"}])))
        assert ev.active_cooldowns() == {}

    def test_active_cooldowns_clears_after_expiry(self, tmp_path):
        rule = single_rule([{"class_name": "handgun"}], cooldown=0.05)
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, rule))
        ev.evaluate([MockThreatState(1, "handgun")])
        time.sleep(0.07)
        assert ev.active_cooldowns() == {}


# ===========================================================================
# FrameIndex construction
# ===========================================================================

class TestFrameIndex:

    def test_index_groups_by_class(self, tmp_path):
        ev = RuleEvaluator.__new__(RuleEvaluator)
        threats = [
            MockThreatState(1, "handgun"),
            MockThreatState(2, "handgun"),
            MockThreatState(3, "crowbar"),
        ]
        idx = ev._build_index(threats)
        assert len(idx.by_class["handgun"]) == 2
        assert len(idx.by_class["crowbar"]) == 1

    def test_index_groups_by_all_zones(self, tmp_path):
        """An object in multiple zones is indexed under each."""
        ev = RuleEvaluator.__new__(RuleEvaluator)
        threat = MockThreatState(1, "crowbar", active_zones=["porch", "front_yard"])
        idx = ev._build_index([threat])
        assert threat in idx.by_zone["porch"]
        assert threat in idx.by_zone["front_yard"]

    def test_index_all_contains_everything(self, tmp_path):
        ev = RuleEvaluator.__new__(RuleEvaluator)
        threats = [MockThreatState(i, "handgun") for i in range(5)]
        idx = ev._build_index(threats)
        assert idx.all is threats


# ===========================================================================
# Multiple rules in a single frame
# ===========================================================================

class TestMultipleRules:

    def test_two_rules_both_fire(self, tmp_path):
        data = {"rules": [
            {"name": "WeaponAlert", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 0},
            {"name": "ToolAlert",   "conditions": [{"class_name": "crowbar"}], "cooldown_seconds": 0},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        threats = [
            MockThreatState(1, "handgun"),
            MockThreatState(2, "crowbar"),
        ]
        alerts = ev.evaluate(threats)
        names = {a.rule_name for a in alerts}
        assert names == {"WeaponAlert", "ToolAlert"}

    def test_mixed_severities_fire_independently(self, tmp_path):
        """A low and a critical rule can both fire in the same frame, each
        carrying its own severity."""
        data = {"rules": [
            {"name": "WeaponAlert", "severity": "critical", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 0},
            {"name": "ToolAlert",   "severity": "low",      "conditions": [{"class_name": "crowbar"}], "cooldown_seconds": 0},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        threats = [
            MockThreatState(1, "handgun"),
            MockThreatState(2, "crowbar"),
        ]
        alerts = ev.evaluate(threats)
        by_name = {a.rule_name: a.severity for a in alerts}
        assert by_name["WeaponAlert"] == Severity.CRITICAL
        assert by_name["ToolAlert"] == Severity.LOW

    def test_only_matching_rule_fires(self, tmp_path):
        data = {"rules": [
            {"name": "WeaponAlert", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 0},
            {"name": "ToolAlert",   "conditions": [{"class_name": "crowbar"}], "cooldown_seconds": 0},
        ]}
        ev = RuleEvaluator(rules_path=write_rules(tmp_path, data))
        # Only a weapon present
        threats = [MockThreatState(1, "handgun")]
        alerts = ev.evaluate(threats)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "WeaponAlert"


# ===========================================================================
# Hot-reload
# ===========================================================================

class TestHotReload:

    def test_reload_loads_new_rules(self, tmp_path):
        rules_file = tmp_path / "rules.json"
        ev = RuleEvaluator(rules_path=str(rules_file))
        assert ev.bypass is True

        rules_file.write_text(
            json.dumps({"rules": [{"name": "NewRule", "conditions": [{"class_name": "handgun"}]}]}),
            encoding="utf-8",
        )
        result = ev.reload()
        assert result is True
        assert ev.rule_count == 1
        assert ev._rules[0].name == "NewRule"

    def test_reload_preserves_cooldown_ledger(self, tmp_path):
        """Cooldowns already in progress must survive a hot-reload."""
        data = {"rules": [{"name": "R", "conditions": [{"class_name": "handgun"}], "cooldown_seconds": 60}]}
        path = write_rules(tmp_path, data)
        ev = RuleEvaluator(rules_path=path)

        ev.evaluate([MockThreatState(1, "handgun")])
        assert "R" in ev._cooldown_ledger

        ev.reload()
        assert "R" in ev._cooldown_ledger

    def test_reload_to_invalid_file_returns_false(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        assert ev.rule_count == 1

        (tmp_path / "rules.json").unlink()
        result = ev.reload()
        assert result is False
        assert ev.bypass is True


# ===========================================================================
# Diagnostics
# ===========================================================================

class TestDiagnostics:

    def test_diagnostics_bypass_mode(self, tmp_path):
        ev = RuleEvaluator(rules_path=str(tmp_path / "nope.json"))
        d = ev.diagnostics()
        assert d["bypass"] is True
        assert d["rule_count"] == 0
        assert d["rules"] == []

    def test_diagnostics_loaded_mode(self, tmp_path):
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}], cooldown=45.0, severity="critical"))
        ev = RuleEvaluator(rules_path=path)
        d = ev.diagnostics()
        assert d["bypass"] is False
        assert d["rule_count"] == 1
        assert d["rules"][0]["name"] == "TestRule"
        assert d["rules"][0]["cooldown_seconds"] == 45.0
        assert d["rules"][0]["severity"] == "critical"

    def test_diagnostics_is_json_serialisable(self, tmp_path):
        import json
        path = write_rules(tmp_path, single_rule([{"class_name": "handgun"}]))
        ev = RuleEvaluator(rules_path=path)
        json.dumps(ev.diagnostics())


# ===========================================================================
# Sample rules.json integration test
# ===========================================================================

class TestSampleRulesJson:
    """Smoke-test a rules.json placed alongside this test file, if present."""

    SAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json")

    @pytest.fixture
    def ev(self):
        if not os.path.exists(self.SAMPLE_PATH):
            pytest.skip("rules.json not present alongside test file")
        return RuleEvaluator(rules_path=self.SAMPLE_PATH)

    def test_sample_file_loads_without_bypass(self, ev):
        assert ev.bypass is False
        assert ev.rule_count > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
