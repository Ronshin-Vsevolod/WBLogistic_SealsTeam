"""Tests for configuration loading and (future) engine logic."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from backend_service.engine.forecaster_macro import predict_macro
from backend_service.engine.forecaster_micro import predict_micro
from backend_service.core.config import (
    Settings,
    VehicleSpec,
    get_settings,
    load_settings,
)
from backend_service.engine.auto_dispatcher import (
    generate_dispatches,
    build_tactical_plan,
    _select_vehicle,
)

_STATUSES = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0]
_MACRO_WEATHER = [1.0, 2.0, 1.0, 0.5, 3.0, 0.5, 1.5]
_PROMO = [0.5] * 7

_MICRO_WEATHER = [0.0, 1.0, 2.0, 1.5, 0.5]
_TRAFFIC = 0.3
_MACRO_BASELINE = 45.0
_MICRO_HORIZON = 24
_MICRO_STEP_MIN = 30

_VEHICLE_CATALOG = {
    "van": VehicleSpec(capacity=50.0),
    "standard_truck": VehicleSpec(capacity=100.0),
    "large_truck": VehicleSpec(capacity=200.0),
}

_TIMESTAMP = 1718438400000
_OFFICE_ID = 42
_ROUTE_ID = 101
_STANDARD_VEHICLE = "standard_truck"
_TRUCK_CAPACITY = 100.0


# ── Settings validation ──────────────────────────────────────────

class TestSettingsValidation:
    def test_defaults_are_valid(self):
        s = Settings()
        assert s.micro_step_minutes == 30
        assert s.micro_horizon_steps == 10
        assert s.truck_capacity == 30.0
        assert s.base_sla_hours == 4.0
        assert s.standard_vehicle_type in s.vehicle_catalog
    
    def test_standard_vehicle_capacity_must_cover_truck_capacity(self):
        with pytest.raises(ValidationError, match="smaller than truck_capacity"):
            Settings(
                truck_capacity=30.0,
                standard_vehicle_type="10t_truck",
                vehicle_catalog={
                    "10t_truck": VehicleSpec(capacity=15.0),
                    "20t_truck": VehicleSpec(capacity=30.0),
                },
            )

    # ── positive-value checks ────────────────────────────────────

    def test_micro_step_zero_rejected(self):
        with pytest.raises(ValidationError, match="micro_step_minutes"):
            Settings(micro_step_minutes=0)

    def test_micro_step_negative_rejected(self):
        with pytest.raises(ValidationError, match="micro_step_minutes"):
            Settings(micro_step_minutes=-10)

    def test_micro_horizon_zero_rejected(self):
        with pytest.raises(ValidationError, match="micro_horizon_steps"):
            Settings(micro_horizon_steps=0)

    def test_truck_capacity_zero_rejected(self):
        with pytest.raises(ValidationError, match="truck_capacity"):
            Settings(truck_capacity=0)

    def test_truck_capacity_negative_rejected(self):
        with pytest.raises(ValidationError, match="truck_capacity"):
            Settings(truck_capacity=-5.0)

    def test_base_sla_zero_rejected(self):
        with pytest.raises(ValidationError, match="base_sla_hours"):
            Settings(base_sla_hours=0)

    # ── vehicle catalog checks ───────────────────────────────────

    def test_empty_catalog_rejected(self):
        with pytest.raises(ValidationError, match="vehicle_catalog"):
            Settings(vehicle_catalog={})

    def test_negative_vehicle_capacity_rejected(self):
        with pytest.raises(ValidationError, match="capacity"):
            Settings(
                vehicle_catalog={"truck": VehicleSpec(capacity=-10.0)}
            )

    def test_zero_vehicle_capacity_rejected(self):
        with pytest.raises(ValidationError, match="capacity"):
            VehicleSpec(capacity=0.0)

    def test_standard_vehicle_not_in_catalog(self):
        with pytest.raises(ValidationError, match="not found"):
            Settings(
                standard_vehicle_type="nonexistent",
                vehicle_catalog={"20t_truck": VehicleSpec(capacity=30.0)},
            )

    # ── derived helpers ──────────────────────────────────────────

    def test_micro_horizon_minutes(self):
        s = Settings(micro_step_minutes=15, micro_horizon_steps=4)
        assert s.micro_horizon_minutes == 60

    def test_standard_vehicle_capacity(self):
        s = Settings()
        assert s.standard_vehicle_capacity == 30.0


# ── YAML file loading ────────────────────────────────────────────


class TestLoadSettings:
    def test_load_from_yaml_file(self, tmp_path: Path):
        data = {
            "micro_step_minutes": 15,
            "micro_horizon_steps": 8,
            "truck_capacity": 25.0,
            "base_sla_hours": 12.0,
            "standard_vehicle_type": "20t_truck",
            "vehicle_catalog": {
                "van": {"capacity": 5.0},
                "20t_truck": {"capacity": 30.0},
                },
        }
        path = tmp_path / "settings.yaml"
        path.write_text(yaml.dump(data))

        s = load_settings(path)

        assert s.micro_step_minutes == 15
        assert s.micro_horizon_steps == 8
        assert s.truck_capacity == 25.0
        assert s.standard_vehicle_type == "20t_truck"
        assert s.vehicle_catalog["van"].capacity == 5.0
        assert s.vehicle_catalog["20t_truck"].capacity == 30.0

    def test_missing_file_returns_defaults(self):
        s = load_settings(Path("/does/not/exist.yaml"))
        assert s == Settings()

    def test_empty_yaml_returns_defaults(self, tmp_path: Path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        s = load_settings(path)
        assert s == Settings()

    def test_partial_yaml_merges_with_defaults(self, tmp_path: Path):
        path = tmp_path / "partial.yaml"
        path.write_text(yaml.dump({"micro_step_minutes": 10}))
        s = load_settings(path)
        assert s.micro_step_minutes == 10
        assert s.micro_horizon_steps == 10  # default

    def test_invalid_yaml_values_rejected(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump({"micro_step_minutes": -1}))
        with pytest.raises(ValidationError):
            load_settings(path)


# ── env-var override ─────────────────────────────────────────────


class TestGetSettings:
    def test_env_var_override(self, monkeypatch, tmp_path: Path):
        data = {
            "micro_step_minutes": 45,
            "standard_vehicle_type": "20t_truck",
            "vehicle_catalog": {"20t_truck": {"capacity": 30.0}},
        }
        path = tmp_path / "custom.yaml"
        path.write_text(yaml.dump(data))
        monkeypatch.setenv("SETTINGS_PATH", str(path))

        s = get_settings()

        assert s.micro_step_minutes == 45

    def test_caching_returns_same_object(self):
        a = get_settings()
        b = get_settings()
        assert a is b



# ═══════════════════════════════════════════════════════════════════
# Macro forecaster
# ═══════════════════════════════════════════════════════════════════


class TestMacroForecaster:
    def test_returns_seven_values(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert len(result.daily_forecast) == 7

    def test_values_non_negative(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert all(v >= 0.0 for v in result.daily_forecast)

    def test_returns_macro_daily_baseline(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert isinstance(result.macro_daily_baseline, float)
        assert result.macro_daily_baseline >= 0.0

    def test_reacts_to_changed_weather(self):
        r1 = predict_macro(_STATUSES, [0.0] * 7, _PROMO)
        r2 = predict_macro(_STATUSES, [10.0] * 7, _PROMO)
        assert r1.daily_forecast != r2.daily_forecast

    def test_reacts_to_changed_promo(self):
        r1 = predict_macro(_STATUSES, _MACRO_WEATHER, [0.0] * 7)
        r2 = predict_macro(_STATUSES, _MACRO_WEATHER, [1.0] * 7)
        assert r1.daily_forecast != r2.daily_forecast

    def test_deterministic(self):
        r1 = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        r2 = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert r1.daily_forecast == r2.daily_forecast
        assert r1.macro_daily_baseline == r2.macro_daily_baseline


# ═══════════════════════════════════════════════════════════════════
# Micro forecaster
# ═══════════════════════════════════════════════════════════════════


def _micro(**overrides):
    """Call predict_micro with defaults, overriding selected args."""
    kwargs = dict(
        statuses=_STATUSES,
        micro_weather=_MICRO_WEATHER,
        traffic=_TRAFFIC,
        macro_daily_baseline=_MACRO_BASELINE,
        micro_horizon_steps=_MICRO_HORIZON,
        micro_step_minutes=_MICRO_STEP_MIN,
    )
    kwargs.update(overrides)
    return predict_micro(**kwargs)


class TestMicroForecaster:
    def test_returns_exact_horizon_steps(self):
        result = _micro()
        assert len(result) == _MICRO_HORIZON

    def test_horizon_not_derived_from_micro_weather_len(self):
        """Horizon must come from config, not ``len(microWeather) * 2``."""
        arbitrary_horizon = 36
        result = _micro(micro_horizon_steps=arbitrary_horizon)
        assert len(result) == arbitrary_horizon
        assert len(result) != len(_MICRO_WEATHER) * 2

    def test_micro_scale_is_step_level_not_daily_level(self):
        result = _micro(
            macro_daily_baseline=48.0,
            micro_horizon_steps=48,
            micro_step_minutes=30,
            micro_weather=[0.0] * 5,
            traffic=0.0,
        )
        assert sum(result) < 48.0 * 5

    def test_values_non_negative(self):
        result = _micro()
        assert all(v >= 0.0 for v in result)

    def test_reacts_to_changed_traffic(self):
        r1 = _micro(traffic=0.0)
        r2 = _micro(traffic=1.0)
        assert r1 != r2

    def test_reacts_to_changed_micro_weather(self):
        r1 = _micro(micro_weather=[0.0, 0.0, 0.0, 0.0, 0.0])
        r2 = _micro(micro_weather=[5.0, 10.0, 15.0, 10.0, 5.0])
        assert r1 != r2

    def test_deterministic(self):
        r1 = _micro()
        r2 = _micro()
        assert r1 == r2



# ═══════════════════════════════════════════════════════════════════
#  Macro forecaster
# ═══════════════════════════════════════════════════════════════════


class TestMacroForecaster:
    def test_returns_seven_values(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert len(result.daily_forecast) == 7

    def test_values_non_negative(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert all(v >= 0.0 for v in result.daily_forecast)

    def test_returns_macro_daily_baseline(self):
        result = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert isinstance(result.macro_daily_baseline, float)
        assert result.macro_daily_baseline >= 0.0

    def test_reacts_to_changed_weather(self):
        r1 = predict_macro(_STATUSES, [0.0] * 7, _PROMO)
        r2 = predict_macro(_STATUSES, [10.0] * 7, _PROMO)
        assert r1.daily_forecast != r2.daily_forecast

    def test_reacts_to_changed_promo(self):
        r1 = predict_macro(_STATUSES, _MACRO_WEATHER, [0.0] * 7)
        r2 = predict_macro(_STATUSES, _MACRO_WEATHER, [1.0] * 7)
        assert r1.daily_forecast != r2.daily_forecast

    def test_deterministic(self):
        r1 = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        r2 = predict_macro(_STATUSES, _MACRO_WEATHER, _PROMO)
        assert r1.daily_forecast == r2.daily_forecast
        assert r1.macro_daily_baseline == r2.macro_daily_baseline


# ═══════════════════════════════════════════════════════════════════
#  Micro forecaster
# ═══════════════════════════════════════════════════════════════════


def _micro(**overrides):
    """Call predict_micro with defaults, overriding selected args."""
    kwargs = dict(
        statuses=_STATUSES,
        micro_weather=_MICRO_WEATHER,
        traffic=_TRAFFIC,
        macro_daily_baseline=_MACRO_BASELINE,
        micro_horizon_steps=_MICRO_HORIZON,
        micro_step_minutes=_MICRO_STEP_MIN,
    )
    kwargs.update(overrides)
    return predict_micro(**kwargs)


class TestMicroForecaster:
    def test_returns_exact_horizon_steps(self):
        result = _micro()
        assert len(result) == _MICRO_HORIZON

    def test_horizon_not_derived_from_micro_weather_len(self):
        arbitrary_horizon = 36
        result = _micro(micro_horizon_steps=arbitrary_horizon)
        assert len(result) == arbitrary_horizon
        assert len(result) != len(_MICRO_WEATHER) * 2

    def test_values_non_negative(self):
        result = _micro()
        assert all(v >= 0.0 for v in result)

    def test_reacts_to_changed_traffic(self):
        r1 = _micro(traffic=0.0)
        r2 = _micro(traffic=1.0)
        assert r1 != r2

    def test_reacts_to_changed_micro_weather(self):
        r1 = _micro(micro_weather=[0.0, 0.0, 0.0, 0.0, 0.0])
        r2 = _micro(micro_weather=[5.0, 10.0, 15.0, 10.0, 5.0])
        assert r1 != r2

    def test_deterministic(self):
        r1 = _micro()
        r2 = _micro()
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════
#  Shared defaults — Decision Engine
# ═══════════════════════════════════════════════════════════════════

def _dispatches(**overrides):
    """Call generate_dispatches with sane defaults, overriding
    selected arguments for the specific scenario under test."""
    kwargs = dict(
        office_from_id=_OFFICE_ID,
        route_id=_ROUTE_ID,
        timestamp=_TIMESTAMP,
        micro_forecast=[10.0] * 4,
        settings=Settings(
            micro_step_minutes=30,
            micro_horizon_steps=10,
            truck_capacity=_TRUCK_CAPACITY,
            base_sla_hours=24.0,   # high — won't trigger unless lowered
            standard_vehicle_type=_STANDARD_VEHICLE,
            vehicle_catalog=_VEHICLE_CATALOG,
        ),
    )
    kwargs.update(overrides)
    return generate_dispatches(**kwargs)


# ═══════════════════════════════════════════════════════════════════
#  Capacity-threshold behaviour
# ═══════════════════════════════════════════════════════════════════


class TestCapacityThreshold:
    def test_emits_dispatch_when_threshold_reached(self):
        # Two steps of 50 → buffer hits 100 at step 1
        result = _dispatches(micro_forecast=[50.0, 50.0])
        cap = [d for d in result if d.trigger_reason == "CAPACITY_FULL"]
        assert len(cap) == 1
        assert cap[0].expected_volume == _TRUCK_CAPACITY
        assert cap[0].vehicle_type == _STANDARD_VEHICLE
        assert cap[0].fill_rate == 1.0

    def test_emits_multiple_dispatches_for_large_buffer(self):
        # Single step of 250 → two full-load dispatches, 50 leftover
        result = _dispatches(micro_forecast=[250.0])
        cap = [d for d in result if d.trigger_reason == "CAPACITY_FULL"]
        assert len(cap) == 2
        assert all(d.expected_volume == _TRUCK_CAPACITY for d in cap)
        assert all(d.fill_rate == 1.0 for d in cap)


# ═══════════════════════════════════════════════════════════════════
#  SLA-breach behaviour
# ═══════════════════════════════════════════════════════════════════


class TestSLABreach:
    def test_emits_sla_dispatch_when_waiting_time_exceeded(self):
        # step=30 min, SLA=1 h → SLA fires at step 1 (wait=60 min)
        result = _dispatches(
            micro_forecast=[10.0, 10.0],
            settings=Settings(
                micro_step_minutes=30,
                micro_horizon_steps=10,
                truck_capacity=_TRUCK_CAPACITY,
                base_sla_hours=1.0,
                standard_vehicle_type=_STANDARD_VEHICLE,
                vehicle_catalog=_VEHICLE_CATALOG,
            ),
        )
        sla = [d for d in result if d.trigger_reason == "SLA_BREACH"]
        assert len(sla) >= 1
        assert sla[0].priority == 1

    def test_fully_covers_overdue_volume(self):
        # 4 steps × 10 → SLA fires at step 1 (buf=20) and step 3 (buf=20)
        # total dispatched must equal total forecast (no residue lost)
        result = _dispatches(
            micro_forecast=[10.0, 10.0, 10.0, 10.0],
            settings=Settings(
                micro_step_minutes=30,
                micro_horizon_steps=10,
                truck_capacity=_TRUCK_CAPACITY,
                base_sla_hours=1.0,
                standard_vehicle_type=_STANDARD_VEHICLE,
                vehicle_catalog=_VEHICLE_CATALOG,
            ),
        )
        total_dispatched = sum(d.expected_volume for d in result)
        assert total_dispatched == 40.0

"""
Моя хотелка (как я думаю будет лучше), чтобы при виде micro_forecast=[150.0, 0.0 и дальше много нулей] логика не ждала истечения времени SLA, понимая бессмысленность ожидания и наличия ТС под остаток.
Сделаю позже.
    def test_does_not_leave_overdue_residue(self):
        # 150 units at SLA trigger with max vehicle = 100
        # engine must send enough vehicles to cover ALL 150
        small_catalog = {
            "small": VehicleSpec(capacity=50.0),
            "medium": VehicleSpec(capacity=100.0),
        }
        result = _dispatches(
            micro_forecast=[150.0, 0.0],
            settings=Settings(
                micro_step_minutes=30,
                micro_horizon_steps=10,
                truck_capacity=_TRUCK_CAPACITY,
                base_sla_hours=1.0,
                standard_vehicle_type="medium",
                vehicle_catalog=small_catalog,
            ),
        )
        sla = [d for d in result if d.trigger_reason == "SLA_BREACH"]
        total_sla_volume = sum(d.expected_volume for d in sla)
        assert total_sla_volume == 150.0
        assert len(sla) >= 2            # needs more than one vehicle
        assert all(0.0 <= d.fillRate <= 1.0 for d in sla)
"""

# ═══════════════════════════════════════════════════════════════════
#  Horizon-end behaviour
# ═══════════════════════════════════════════════════════════════════


class TestHorizonEnd:
    def test_no_artificial_dispatch_at_horizon_end(self):
        # Small volumes, huge capacity, huge SLA → nothing triggers
        result = _dispatches(
            micro_forecast=[10.0, 10.0, 10.0],
            settings=Settings(
                micro_step_minutes=30,
                micro_horizon_steps=10,
                truck_capacity=_TRUCK_CAPACITY,
                base_sla_hours=10.0,
                standard_vehicle_type=_STANDARD_VEHICLE,
                vehicle_catalog=_VEHICLE_CATALOG,
            ),
        )
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════
#  Tactical-plan builder
# ═══════════════════════════════════════════════════════════════════


class TestTacticalPlan:
    def test_returns_seven_rows(self):
        plan = build_tactical_plan(
            office_from_id=_OFFICE_ID,
            timestamp=_TIMESTAMP,
            daily_forecast=[100.0] * 7,
            truck_capacity=_TRUCK_CAPACITY,
        )
        assert len(plan) == 7
        assert all(row.warehouse_id == str(_OFFICE_ID) for row in plan)

    def test_non_negative_required_trucks(self):
        plan = build_tactical_plan(
            office_from_id=_OFFICE_ID,
            timestamp=_TIMESTAMP,
            daily_forecast=[0.0, 50.0, 100.0, 150.0, 200.0, 0.0, 75.0],
            truck_capacity=_TRUCK_CAPACITY,
        )
        assert all(row.required_trucks >= 0 for row in plan)
        # spot-check ceil logic
        by_vol = {row.forecast_volume: row.required_trucks for row in plan}
        assert by_vol[0.0] == 0
        assert by_vol[50.0] == 1      # ceil(50/100)  = 1
        assert by_vol[150.0] == 2     # ceil(150/100) = 2


# ═══════════════════════════════════════════════════════════════════
#  Vehicle selection (config-driven)
# ═══════════════════════════════════════════════════════════════════


class TestVehicleSelection:
    def test_selects_smallest_sufficient_vehicle(self):
        vehicle_type, capacity = _select_vehicle(30.0, _VEHICLE_CATALOG)
        assert vehicle_type == "van"
        assert capacity == 50.0

    def test_falls_back_to_largest_available(self):
        vehicle_type, capacity = _select_vehicle(999.0, _VEHICLE_CATALOG)
        assert vehicle_type == "large_truck"
        assert capacity == 200.0