"""
Configuration loader.

* Reads business settings from a YAML file.
* Falls back to safe defaults when the file is absent.
* The file path can be overridden via the SETTINGS_PATH env-var.
* `get_settings()` provides cached, singleton-like access.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SETTINGS_PATH = _PROJECT_ROOT / "config" / "settings.yaml"

ENV_SETTINGS_PATH = "SETTINGS_PATH"


# ── helper models ────────────────────────────────────────────────

class VehicleSpec(BaseModel):
    """Single entry in the vehicle catalog."""

    capacity: float

    @field_validator("capacity")
    @classmethod
    def capacity_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Vehicle capacity must be positive")
        return v


# ── main settings model ─────────────────────────────────────────

class Settings(BaseModel):
    """All runtime-configurable business settings."""

    micro_step_minutes: int = 30
    micro_horizon_steps: int = 10
    truck_capacity: float = 30.0
    base_sla_hours: float = 4.0
    standard_vehicle_type: str = "20t_truck"
    vehicle_catalog: dict[str, VehicleSpec] = Field(
        default_factory=lambda: {
            "van": VehicleSpec(capacity=5.0),
            "10t_truck": VehicleSpec(capacity=15.0),
            "20t_truck": VehicleSpec(capacity=30.0),
        },
    )

    # ── field validators ─────────────────────────────────────────

    @field_validator("micro_step_minutes")
    @classmethod
    def _micro_step_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("micro_step_minutes must be > 0")
        return v

    @field_validator("micro_horizon_steps")
    @classmethod
    def _micro_horizon_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("micro_horizon_steps must be > 0")
        return v

    @field_validator("truck_capacity")
    @classmethod
    def _truck_capacity_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("truck_capacity must be > 0")
        return v

    @field_validator("base_sla_hours")
    @classmethod
    def _base_sla_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("base_sla_hours must be > 0")
        return v

    @field_validator("vehicle_catalog")
    @classmethod
    def _catalog_not_empty(
        cls, v: dict[str, VehicleSpec]
    ) -> dict[str, VehicleSpec]:
        if not v:
            raise ValueError("vehicle_catalog must not be empty")
        return v

    # ── cross-field validation ───────────────────────────────────

    @model_validator(mode="after")
    def _standard_vehicle_in_catalog(self) -> "Settings":
        if self.standard_vehicle_type not in self.vehicle_catalog:
            raise ValueError(
                f"standard_vehicle_type '{self.standard_vehicle_type}' "
                f"not found in vehicle_catalog: {list(self.vehicle_catalog)}"
            )
        return self

    @model_validator(mode="after")
    def _standard_vehicle_can_cover_threshold(self) -> "Settings":
        standard_capacity = self.vehicle_catalog[self.standard_vehicle_type].capacity
        if standard_capacity < self.truck_capacity:
            raise ValueError(
                f"standard_vehicle_type '{self.standard_vehicle_type}' "
                f"has capacity {standard_capacity}, which is smaller than "
                f"truck_capacity={self.truck_capacity}"
            )
        return self

    # ── derived helpers ──────────────────────────────────────────

    @property
    def micro_horizon_minutes(self) -> int:
        """Total micro-forecast horizon in minutes."""
        return self.micro_step_minutes * self.micro_horizon_steps

    @property
    def standard_vehicle_capacity(self) -> float:
        """Capacity of the standard vehicle type."""
        return self.vehicle_catalog[self.standard_vehicle_type].capacity


# ── loaders ──────────────────────────────────────────────────────


def load_settings(path: Path | None = None) -> Settings:
    """Load and validate settings from *path* (or the default location).

    If the file does not exist, safe built-in defaults are returned.
    """
    if path is None:
        env = os.environ.get(ENV_SETTINGS_PATH)
        path = Path(env) if env else _DEFAULT_SETTINGS_PATH

    if path.exists():
        logger.info("Loading settings from %s", path)
        with open(path) as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}
        return Settings(**raw)

    logger.warning(
        "Settings file not found at %s – using defaults", path
    )
    return Settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton access to the current settings."""
    return load_settings()