"""Decision Engine — converts micro forecasts into dispatch requests
and builds tactical plans from macro forecasts.

Business rules implemented:
  1. Rolling buffer accumulation across micro forecast steps
  2. Capacity-threshold dispatch (full-load, standard vehicle)
  3. SLA-breach dispatch (fully covers *all* overdue volume)
  4. Waiting-time handling (reset only when buffer is truly empty)
  5. scheduledAt in ISO-8601 UTC with trailing Z
  6. No artificial horizon-end dispatch

Vehicle selection is fully config-driven — no transport names are
hard-coded in business logic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


# ── Output data structures ──────────────────────────────────────────


@dataclass
class DispatchRequest:
    """A single dispatch instruction produced by the engine."""

    warehouse_id: str
    route_id: int
    scheduled_at: datetime
    vehicle_type: str
    expected_volume: float
    vehicle_capacity: float
    fill_rate: float
    trigger_reason: str
    priority: str            # NORMAL | HIGH


@dataclass
class TacticalPlanRow:
    """One row of the 7-day tactical plan."""

    warehouse_id: str
    plan_date: datetime.date
    forecast_volume: float
    required_trucks: int

# ── Vehicle selection (config-driven) ───────────────────────────────


def _select_vehicle(
    volume: float,
    vehicle_catalog: dict[str, object],
) -> tuple[str, float]:
    """Pick the best-fit vehicle from *catalog* for *volume*.

    Strategy
    --------
    1. If at least one vehicle has ``capacity >= volume``, return the
       **smallest sufficient** vehicle (tightest fit).
    2. Otherwise fall back to the **largest available** vehicle.

    The function is intentionally catalog-agnostic: it works correctly
    when capacities, names, or the number of vehicle types change.
    """
    sorted_catalog = sorted(
        vehicle_catalog.items(),
        key=lambda item: item[1].capacity,
    )
    for vehicle_type, spec in sorted_catalog:
        if spec.capacity >= volume:
            return vehicle_type, float(spec.capacity)

    vehicle_type, spec = sorted_catalog[-1]
    return vehicle_type, float(spec.capacity)

def _append_variable_vehicle_dispatches(
    dispatches: list[DispatchRequest],
    office_from_id: int,
    route_id: int,
    scheduled_at: datetime,
    volume: float,
    trigger_reason: str,
    priority: int,
    vehicle_catalog: dict[str, object],
) -> None:
    """Dispatch *volume* using best-fit vehicles from the catalog."""
    remaining = volume

    while remaining > 0.0:
        vehicle_type, cap = _select_vehicle(remaining, vehicle_catalog)
        dispatched = min(remaining, cap)
        fill = dispatched / cap if cap > 0.0 else 0.0

        dispatches.append(DispatchRequest(
            warehouse_id=str(office_from_id),
            route_id=route_id,
            scheduled_at=scheduled_at,
            vehicle_type=vehicle_type,
            expected_volume=round(dispatched, 4),
            vehicle_capacity=cap,
            fill_rate=round(min(fill, 1.0), 4),
            trigger_reason=trigger_reason,
            priority=priority,
        ))
        remaining -= dispatched


# ── Core dispatch generation ────────────────────────────────────────


def generate_dispatches(
    office_from_id: int,
    route_id: int,
    timestamp: int,
    micro_forecast: list[float],
    settings: Settings,
) -> list[DispatchRequest]:
    """Convert a micro forecast into concrete dispatch requests.

    Parameters
    ----------
    office_from_id:
        Warehouse / office identifier (becomes ``warehouseId``).
    route_id:
        Logistics route identifier.
    timestamp:
        Request timestamp (ISO-8601 UTC, trailing ``Z``).
    micro_forecast:
        Intra-day volume forecast (length = ``micro_horizon_steps``).
    micro_step_minutes:
        Duration of one forecast step in minutes (from config).
    truck_capacity:
        Capacity of the standard vehicle — also serves as the
        capacity-threshold trigger level.
    base_sla_hours:
        Maximum acceptable waiting time before an SLA-breach dispatch
        is forced.
    standard_vehicle_type:
        Name / label of the standard vehicle used for capacity-
        threshold dispatches (from config, **not** hard-coded).
    vehicle_catalog:
        List of ``{"type": str, "capacity": float}`` dicts
        describing all available vehicle types (from config).

    Returns
    -------
    list[DispatchRequest]
        Zero or more dispatch instructions.  No artificial
        ``HORIZON_END`` dispatch is ever emitted.
    """
    micro_step_minutes = settings.micro_step_minutes
    truck_capacity = settings.truck_capacity
    base_sla_hours = settings.base_sla_hours
    standard_vehicle_type = settings.standard_vehicle_type
    vehicle_catalog = settings.vehicle_catalog

    base_dt = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
    sla_minutes = base_sla_hours * 60.0

    dispatches: list[DispatchRequest] = []
    buffer = 0.0
    wait_minutes = 0.0

    for step_idx, step_volume in enumerate(micro_forecast):
        # ── Rule 1: rolling buffer ──────────────────────────────
        buffer += step_volume
        wait_minutes += micro_step_minutes

        scheduled_at = _format_scheduled_at(
            base_dt, step_idx, micro_step_minutes,
        )

        # ── Rule 2: capacity-threshold dispatch ─────────────────
        standard_capacity = vehicle_catalog[standard_vehicle_type].capacity
        had_capacity_dispatch = False

        while buffer >= truck_capacity:
            had_capacity_dispatch = True
            dispatches.append(DispatchRequest(
                warehouse_id=str(office_from_id),
                route_id=route_id,
                scheduled_at=scheduled_at,
                vehicle_type=standard_vehicle_type,
                expected_volume=round(truck_capacity, 4),
                vehicle_capacity=standard_capacity,
                fill_rate=round(min(truck_capacity / standard_capacity, 1.0), 4),
                trigger_reason="CAPACITY_FULL",
                priority=2,
            ))
            buffer -= truck_capacity

        # ── Rule 3: waiting-time handling ───────────────────────
        if buffer <= 0.0:
            buffer = 0.0
            wait_minutes = 0.0

        # ── Rule 4: early tail-clear only if SLA window is fully visible
        #            and no additional demand is expected before SLA ───
        if had_capacity_dispatch and buffer > 0.0 and wait_minutes < sla_minutes:
            remaining_minutes_to_sla = sla_minutes - wait_minutes
            steps_until_sla = math.ceil(remaining_minutes_to_sla / micro_step_minutes)

            future_until_sla = micro_forecast[
                step_idx + 1: step_idx + 1 + steps_until_sla
            ]
            horizon_covers_sla = len(future_until_sla) == steps_until_sla
            has_positive_before_sla = any(v > 0.0 for v in future_until_sla)

            if horizon_covers_sla and not has_positive_before_sla:
                _append_variable_vehicle_dispatches(
                    dispatches=dispatches,
                    office_from_id=office_from_id,
                    route_id=route_id,
                    scheduled_at=scheduled_at,
                    volume=buffer,
                    trigger_reason="NO_DEMAND_BEFORE_SLA",
                    priority=2,
                    vehicle_catalog=vehicle_catalog,
                )
                buffer = 0.0
                wait_minutes = 0.0
                continue

        # ── Rule 5: SLA-breach dispatch ─────────────────────────
        if wait_minutes >= sla_minutes and buffer > 0.0:
            _append_variable_vehicle_dispatches(
                dispatches=dispatches,
                office_from_id=office_from_id,
                route_id=route_id,
                scheduled_at=scheduled_at,
                volume=buffer,
                trigger_reason="SLA_BREACH",
                priority=1,
                vehicle_catalog=vehicle_catalog,
            )
            buffer = 0.0
            wait_minutes = 0.0

    return dispatches


# ── Tactical-plan builder ───────────────────────────────────────────


def build_tactical_plan(
    office_from_id: int,
    timestamp: str,
    daily_forecast: list[float],
    truck_capacity: float,
) -> list[TacticalPlanRow]:
    """Build a 7-day tactical plan from a macro forecast.

    Each day's ``requiredTrucks`` is calculated as::

        ceil(forecastVolume / truck_capacity)

    This is a simplified planning approximation in standard-truck
    equivalents.  It does **not** constrain the runtime dispatch
    engine to a single transport type.

    Parameters
    ----------
    office_from_id:
        Warehouse identifier.
    timestamp:
        Request timestamp (ISO-8601 UTC).
    daily_forecast:
        Seven non-negative daily volume forecasts.
    truck_capacity:
        Capacity of the standard truck for planning purposes.

    Returns
    -------
    list[TacticalPlanRow]
        One row per forecast day.
    """
    base_date = datetime.fromtimestamp(
        timestamp / 1000.0,
        tz=timezone.utc,
    ).date()

    plan: list[TacticalPlanRow] = []
    for day_idx, volume in enumerate(daily_forecast):
        plan_date = base_date + timedelta(days=day_idx)

        if volume > 0.0 and truck_capacity > 0.0:
            required = math.ceil(volume / truck_capacity)
        else:
            required = 0

        plan.append(TacticalPlanRow(
            warehouse_id=str(office_from_id),
            plan_date=plan_date,
            forecast_volume=volume,
            required_trucks=required,
        ))

    return plan


# ── Helpers ─────────────────────────────────────────────────────────


def _format_scheduled_at(
    base_dt: datetime,
    step_idx: int,
    micro_step_minutes: int,
) -> datetime:
    return base_dt + timedelta(minutes=step_idx * micro_step_minutes)