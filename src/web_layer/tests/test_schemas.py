"""Tests for the Pydantic schemas in src/web_layer/schemas.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web_layer.schemas import (
    ConditionSchema,
    RuleSchema,
    RulesPayload,
    ZonesPayload,
)


class TestConditionSchema:
    def test_accepts_class_name_only(self) -> None:
        c = ConditionSchema(class_name="handgun")
        assert c.class_name == "handgun"

    def test_accepts_zone_only(self) -> None:
        c = ConditionSchema(zone="porch")
        assert c.zone == "porch"

    def test_rejects_all_none(self) -> None:
        with pytest.raises(ValidationError):
            ConditionSchema()

    def test_rejects_min_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            ConditionSchema(min_confidence=1.5)
        with pytest.raises(ValidationError):
            ConditionSchema(min_confidence=-0.1)


class TestRuleSchema:
    def test_round_trip(self) -> None:
        rule = RuleSchema(
            name="Porch Intruder",
            description="x",
            severity="critical",
            cooldown_seconds=10,
            conditions=[{"class_name": "person", "zone": "porch"}, {"class_name": "knife"}],
        )
        assert rule.cooldown_seconds == 10.0
        assert rule.severity == "critical"
        assert len(rule.conditions) == 2

    def test_severity_defaults_to_high(self) -> None:
        rule = RuleSchema(name="r", conditions=[{"class_name": "knife"}])
        assert rule.severity == "high"

    def test_invalid_severity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(name="r", severity="urgent", conditions=[{"class_name": "knife"}])

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(name="", conditions=[{"class_name": "handgun"}])

    def test_empty_conditions_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(name="x", conditions=[])

    def test_negative_cooldown_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuleSchema(name="x", cooldown_seconds=-1, conditions=[{"class_name": "handgun"}])


class TestRulesPayload:
    def test_round_trip(self) -> None:
        payload = RulesPayload(
            rules=[{"name": "r1", "conditions": [{"class_name": "handgun"}]}]
        )
        assert payload.rules[0].name == "r1"

    def test_empty_rules_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RulesPayload(rules=[])


class TestZonesPayload:
    def test_round_trip(self) -> None:
        payload = ZonesPayload.model_validate(
            {"porch": [[0, 0], [10, 0], [10, 10], [0, 10]]}
        )
        assert "porch" in payload.root
        assert len(payload.root["porch"]) == 4

    def test_polygon_under_three_vertices_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ZonesPayload.model_validate({"bad": [[0, 0], [1, 1]]})

    def test_negative_coordinates_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ZonesPayload.model_validate({"bad": [[-1, 0], [1, 0], [1, 1]]})

    def test_point_must_be_two_values(self) -> None:
        with pytest.raises(ValidationError):
            ZonesPayload.model_validate({"bad": [[0, 0, 5], [1, 0], [1, 1]]})

    def test_empty_dict_is_valid(self) -> None:
        # Empty zone set is a legal config (everything in 'global' bypass).
        payload = ZonesPayload.model_validate({})
        assert payload.root == {}
