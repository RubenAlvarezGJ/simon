"""Pydantic v2 request/response schemas for the command-center API.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    RootModel,
    conint,
    conlist,
    model_validator,
)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class ConditionSchema(BaseModel):
    """A single rule condition. At least one field must be set."""

    class_name: Optional[str] = None
    zone: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "ConditionSchema":
        if all(
            v is None
            for v in (self.class_name, self.zone, self.min_confidence)
        ):
            raise ValueError(
                "Condition must set at least one of: "
                "class_name, zone, min_confidence."
            )
        return self


class RuleSchema(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    severity: Literal["low", "high", "critical"] = "high"
    cooldown_seconds: float = Field(default=30.0, ge=0.0)
    conditions: conlist(ConditionSchema, min_length=1)  # type: ignore[valid-type]


class RulesPayload(BaseModel):
    rules: conlist(RuleSchema, min_length=1)  # type: ignore[valid-type]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

Point = conlist(conint(ge=0), min_length=2, max_length=2)  # type: ignore[valid-type]
Polygon = conlist(Point, min_length=3)  # type: ignore[valid-type]


class ZonesPayload(RootModel[dict[str, Polygon]]):
    """Mapping of zone name -> polygon (>=3 points, each [x, y] non-negative)."""
