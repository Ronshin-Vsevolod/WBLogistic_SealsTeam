"""
Pydantic schemas for the Java ↔ Python REST contract.

The **external JSON contract** uses camelCase because the Java backend
already sends and expects it.  Internal Python attribute names stay
snake_case; Pydantic's alias generator bridges the two worlds.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


# ── base model ───────────────────────────────────────────────────


class CamelModel(BaseModel):
    """Base model that (de)serialises JSON keys as camelCase."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )

# ── request schemas ──────────────────────────────────────────────


class Integrations(CamelModel):
    """External-signal block inside a forecast request."""

    micro_weather: list[float] = Field(min_length=5, max_length=5)
    traffic: float = Field(ge=0)
    macro_weather: list[float] = Field(min_length=7, max_length=7)
    promo: list[float] = Field(min_length=7, max_length=7)

    @field_validator("micro_weather", "macro_weather", "promo")
    @classmethod
    def _arrays_must_be_non_negative(cls, values: list[float], info) -> list[float]:
        if any(v < 0 for v in values):
            raise ValueError(f"{info.field_name} must contain only non-negative values")
        return values


class ForecastRequest(CamelModel):
    """Inbound request sent by the Java backend."""

    office_from_id: int = Field(gt=0)
    route_id: int = Field(gt=0)
    timestamp: int = Field(gt=0)

    status1: int = Field(ge=0)
    status2: int = Field(ge=0)
    status3: int = Field(ge=0)
    status4: int = Field(ge=0)
    status5: int = Field(ge=0)
    status6: int = Field(ge=0)
    status7: int = Field(ge=0)
    status8: int = Field(ge=0)

    integrations: Integrations


# ── response schemas ─────────────────────────────────────────────


class DispatchEntry(CamelModel):
    """Single dispatch instruction returned to Java."""

    warehouse_id: str
    route_id: int
    scheduled_at: datetime
    vehicle_type: str
    expected_volume: float = Field(ge=0)
    vehicle_capacity: float = Field(ge=0)
    fill_rate: float
    trigger_reason: str
    priority: int = Field(ge=1)

    @field_validator("fill_rate")
    @classmethod
    def clamp_fill_rate(cls, v: float) -> float:
        """Enforce fill_rate ∈ [0.0, 1.0] by clamping."""
        return max(0.0, min(1.0, v))


class TacticalPlanEntry(CamelModel):
    """Single row of the 7-day tactical plan."""

    warehouse_id: str
    plan_date: date
    forecast_volume: float = Field(ge=0)
    required_trucks: int = Field(ge=0)


class ForecastResponse(CamelModel):
    """Top-level response envelope."""

    dispatches: list[DispatchEntry]
    tactical_plan: list[TacticalPlanEntry]