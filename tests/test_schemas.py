"""Tests for Pydantic request / response schemas."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from backend_service.api.schemas import (
    DispatchEntry,
    ForecastRequest,
    ForecastResponse,
    Integrations,
    TacticalPlanEntry,
)

# ── helpers ──────────────────────────────────────────────────────

_VALID_INTEGRATIONS = {
    "microWeather": [2.0, 2.5, 3.0, 3.5, 3.0],
    "traffic": 3.0,
    "macroWeather": [2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 2.0],
    "promo": [2.0, 1.0, 1.0, 3.0, 2.0, 1.0, 1.0],
}


def _base_request(**overrides) -> dict:
    data = {
        "officeFromId": 4,
        "routeId": 29,
        "timestamp": 1740787200000,
        "status1": 3105,
        "status2": 340,
        "status3": 2160,
        "status4": 484,
        "status5": 4018,
        "status6": 3462,
        "status7": 0,
        "status8": 0,
        "integrations": dict(_VALID_INTEGRATIONS),
    }
    data.update(overrides)
    return data


def _dispatch(**overrides) -> dict:
    data = dict(
        warehouse_id="4",
        route_id=29,
        scheduled_at=datetime(2026, 3, 29, 16, 30, tzinfo=timezone.utc),
        vehicle_type="20t_truck",
        expected_volume=28.5,
        vehicle_capacity=30.0,
        fill_rate=0.95,
        trigger_reason="CAPACITY_FULL",
        priority=2,
    )
    data.update(overrides)
    return data


# ── request tests ────────────────────────────────────────────────


class TestForecastRequest:
    def test_valid_camelcase_request(self):
        req = ForecastRequest(**_base_request())
        assert req.office_from_id == 4
        assert req.route_id == 29
        assert req.timestamp == 1740787200000
        assert len(req.integrations.micro_weather) == 5

    def test_serialises_to_camelcase(self):
        req = ForecastRequest(**_base_request())
        out = req.model_dump(by_alias=True)
        assert "officeFromId" in out
        assert "routeId" in out
        nested = out["integrations"]
        assert "microWeather" in nested
        assert "macroWeather" in nested

    def test_negative_micro_weather_value_rejected(self):
        integrations = dict(_VALID_INTEGRATIONS, microWeather=[2.0, -1.0, 3.0, 3.5, 3.0])
        with pytest.raises(ValidationError):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_negative_macro_weather_value_rejected(self):
        integrations = dict(_VALID_INTEGRATIONS, macroWeather=[2.0, 3.0, -1.0, 3.0, 2.0, 1.0, 2.0])
        with pytest.raises(ValidationError):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_negative_promo_value_rejected(self):
        integrations = dict(_VALID_INTEGRATIONS, promo=[2.0, 1.0, -1.0, 3.0, 2.0, 1.0, 1.0])
        with pytest.raises(ValidationError):
            ForecastRequest(**_base_request(integrations=integrations))

    # ── array length constraints ─────────────────────────────────

    def test_micro_weather_too_short(self):
        integrations = dict(_VALID_INTEGRATIONS, microWeather=[1.0, 2.0])
        with pytest.raises(ValidationError, match="microWeather"):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_micro_weather_too_long(self):
        integrations = dict(
            _VALID_INTEGRATIONS, microWeather=[1.0] * 6
        )
        with pytest.raises(ValidationError, match="microWeather"):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_macro_weather_wrong_length(self):
        integrations = dict(
            _VALID_INTEGRATIONS, macroWeather=[1.0, 2.0]
        )
        with pytest.raises(ValidationError, match="macroWeather"):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_promo_wrong_length(self):
        integrations = dict(_VALID_INTEGRATIONS, promo=[1.0])
        with pytest.raises(ValidationError, match="promo"):
            ForecastRequest(**_base_request(integrations=integrations))

    # ── numeric constraints ──────────────────────────────────────

    @pytest.mark.parametrize("field", [f"status{i}" for i in range(1, 9)])
    def test_negative_status_rejected(self, field: str):
        with pytest.raises(ValidationError):
            ForecastRequest(**_base_request(**{field: -1}))

    def test_negative_traffic_rejected(self):
        integrations = dict(_VALID_INTEGRATIONS, traffic=-0.5)
        with pytest.raises(ValidationError, match="traffic"):
            ForecastRequest(**_base_request(integrations=integrations))

    def test_zero_status_accepted(self):
        req = ForecastRequest(**_base_request(status7=0))
        assert req.status7 == 0

    def test_zero_traffic_accepted(self):
        integrations = dict(_VALID_INTEGRATIONS, traffic=0.0)
        req = ForecastRequest(**_base_request(integrations=integrations))
        assert req.integrations.traffic == 0.0


# ── response tests ───────────────────────────────────────────────


class TestDispatchEntry:
    def test_fill_rate_within_range_unchanged(self):
        entry = DispatchEntry(**_dispatch(fill_rate=0.5))
        assert entry.fill_rate == 0.5

    def test_fill_rate_clamped_above_one(self):
        entry = DispatchEntry(**_dispatch(fill_rate=1.5))
        assert entry.fill_rate == 1.0

    def test_fill_rate_clamped_below_zero(self):
        entry = DispatchEntry(**_dispatch(fill_rate=-0.3))
        assert entry.fill_rate == 0.0

    def test_fill_rate_boundary_zero(self):
        entry = DispatchEntry(**_dispatch(fill_rate=0.0))
        assert entry.fill_rate == 0.0

    def test_fill_rate_boundary_one(self):
        entry = DispatchEntry(**_dispatch(fill_rate=1.0))
        assert entry.fill_rate == 1.0

    def test_priority_zero_rejected(self):
        with pytest.raises(ValidationError, match="priority"):
            DispatchEntry(**_dispatch(priority=0))

    def test_priority_negative_rejected(self):
        with pytest.raises(ValidationError, match="priority"):
            DispatchEntry(**_dispatch(priority=-1))

    def test_camelcase_keys(self):
        entry = DispatchEntry(**_dispatch())
        out = entry.model_dump(by_alias=True, mode="json")
        for key in (
            "warehouseId",
            "routeId",
            "scheduledAt",
            "vehicleType",
            "expectedVolume",
            "vehicleCapacity",
            "fillRate",
            "triggerReason",
            "priority",
        ):
            assert key in out, f"Missing camelCase key: {key}"


class TestTacticalPlanEntry:
    def test_valid_entry(self):
        entry = TacticalPlanEntry(
            warehouse_id="4",
            plan_date=date(2026, 3, 30),
            forecast_volume=1500.0,
            required_trucks=50,
        )
        assert entry.required_trucks == 50

    def test_required_trucks_negative_rejected(self):
        with pytest.raises(ValidationError, match="required_trucks"):
            TacticalPlanEntry(
                warehouse_id="4",
                plan_date=date(2026, 3, 30),
                forecast_volume=1500.0,
                required_trucks=-1,
            )

    def test_required_trucks_zero_accepted(self):
        entry = TacticalPlanEntry(
            warehouse_id="4",
            plan_date=date(2026, 3, 30),
            forecast_volume=0.0,
            required_trucks=0,
        )
        assert entry.required_trucks == 0

    def test_camelcase_keys(self):
        entry = TacticalPlanEntry(
            warehouse_id="4",
            plan_date=date(2026, 3, 30),
            forecast_volume=1500.0,
            required_trucks=50,
        )
        out = entry.model_dump(by_alias=True, mode="json")
        assert "warehouseId" in out
        assert "planDate" in out
        assert "forecastVolume" in out
        assert "requiredTrucks" in out


class TestForecastResponse:
    def test_full_response_camelcase(self):
        resp = ForecastResponse(
            dispatches=[DispatchEntry(**_dispatch())],
            tactical_plan=[
                TacticalPlanEntry(
                    warehouse_id="4",
                    plan_date=date(2026, 3, 30),
                    forecast_volume=1500.0,
                    required_trucks=50,
                )
            ],
        )
        out = resp.model_dump(by_alias=True, mode="json")
        assert "dispatches" in out
        assert "tacticalPlan" in out
        assert len(out["dispatches"]) == 1
        assert len(out["tacticalPlan"]) == 1

    def test_empty_lists_accepted(self):
        resp = ForecastResponse(dispatches=[], tactical_plan=[])
        assert resp.dispatches == []
        assert resp.tactical_plan == []