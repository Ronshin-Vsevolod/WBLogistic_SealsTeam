"""Micro-level intra-day demand forecaster (deterministic stub).

``microWeather`` contains **5 control points** (not 5 hourly
observations).  The control points correspond to:

    current time (0 h) · +3 h · +6 h · +9 h · +12 h

Forecast horizon length is always driven by ``micro_horizon_steps``
from configuration – it is **never** derived from
``len(microWeather)``.

The function signature is designed to remain stable when the stub
internals are later replaced with any ``model.predict(X)``
implementation.
"""

from __future__ import annotations


# Hours at which the five microWeather control points are defined.
_CONTROL_HOURS: list[float] = [0.0, 3.0, 6.0, 9.0, 12.0]

def _steps_per_day(step_minutes: int) -> float:
    return (24.0 * 60.0) / step_minutes

def _interpolate_control(
    control_hours: list[float],
    control_values: list[float],
    query_hour: float,
) -> float:
    """Linearly interpolate (with clamped extrapolation) across
    a set of control-point values.
    """
    if not control_values:
        return 0.0
    if len(control_values) == 1:
        return control_values[0]

    # Clamp below / above the defined range
    if query_hour <= control_hours[0]:
        return control_values[0]
    if query_hour >= control_hours[-1]:
        return control_values[-1]

    # Walk segments to find the enclosing pair
    for i in range(len(control_hours) - 1):
        h_lo, h_hi = control_hours[i], control_hours[i + 1]
        if h_lo <= query_hour <= h_hi:
            t = (query_hour - h_lo) / (h_hi - h_lo)
            return control_values[i] + t * (
                control_values[i + 1] - control_values[i]
            )

    return control_values[-1]  # defensive fallback


def predict_micro(
    statuses: list[float],
    micro_weather: list[float],
    traffic: float,
    macro_daily_baseline: float,
    micro_horizon_steps: int,
    micro_step_minutes: int,
) -> list[float]:
    """Produce a deterministic intra-day micro forecast.

    Parameters
    ----------
    statuses:
        Current warehouse status values (``status1`` … ``status8``).
    micro_weather:
        Five control-point values at 0 h, +3 h, +6 h, +9 h, +12 h.
        These are **not** hourly readings – they define a control
        curve that is interpolated across the configured horizon.
    traffic:
        External traffic integration signal scalar.
    macro_daily_baseline:
        Baseline daily level produced by the macro forecaster.
    micro_horizon_steps:
        Number of forecast steps (from config).
    micro_step_minutes:
        Duration of each step in minutes (from config).

    Returns
    -------
    list[float]
        Forecast of length exactly ``micro_horizon_steps``; every
        value ≥ 0.
    """
    # ── base level: prefer macro baseline, fall back to statuses ─
    steps_per_day = _steps_per_day(micro_step_minutes)

    if macro_daily_baseline > 0:
        base = macro_daily_baseline / steps_per_day
    elif statuses:
        fallback_daily = max(sum(statuses) / len(statuses), 0.0)
        base = (fallback_daily / steps_per_day) if fallback_daily > 0 else 1.0
    else:
        base = 1.0

    # ── step through the configured horizon ─────────────────────
    forecast: list[float] = []
    for step in range(micro_horizon_steps):
        step_hour = (step * micro_step_minutes) / 60.0

        # interpolate weather control curve at this point in time
        w_val = _interpolate_control(
            _CONTROL_HOURS, micro_weather, step_hour,
        )
        weather_factor = 1.0 + w_val * 0.01

        # traffic modulation
        traffic_factor = 1.0 + traffic * 0.05

        value = base * weather_factor * traffic_factor
        forecast.append(max(0.0, value))

    return forecast