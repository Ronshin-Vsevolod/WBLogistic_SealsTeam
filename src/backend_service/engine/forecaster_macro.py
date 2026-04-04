"""Macro-level 7-day demand forecaster (deterministic stub).

The function signature is designed to remain stable when the stub
internals are later replaced with CatBoost / LightGBM / Prophet or
any ``model.predict(X)`` implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MacroForecastResult:
    """Outcome of a macro forecast run.

    Attributes
    ----------
    daily_forecast:
        Seven non-negative floats – one per forecast day.
    macro_daily_baseline:
        Internal pipeline state derived from current statuses.
        **Must not** be exposed in the public API response.
    """

    daily_forecast: list[float]
    macro_daily_baseline: float


def predict_macro(
    statuses: list[float],
    macro_weather: list[float],
    promo: list[float],
) -> MacroForecastResult:
    """Produce a deterministic 7-day macro forecast.

    Parameters
    ----------
    statuses:
        Current warehouse status values (``status1`` … ``status8``).
    macro_weather:
        Seven macro-weather values, one per forecast day.
    promo:
        Seven promo values, one per forecast day.

    Returns
    -------
    MacroForecastResult
        Contains ``daily_forecast`` (length 7) and the internal
        ``macro_daily_baseline`` used downstream by the micro
        forecaster.
    """
    # ── derive baseline from current warehouse statuses ─────────
    baseline: float = (
        sum(statuses) / len(statuses) if statuses else 0.0
    )

    # ── build 7-day forecast modulated by weather + promo ───────
    daily_forecast: list[float] = []
    for day_idx in range(7):
        w_val = macro_weather[day_idx]
        p_val = promo[day_idx]

        weather_factor = 1.0 + w_val * 0.01
        promo_factor = 1.0 + p_val * 0.1

        value = baseline * weather_factor * promo_factor
        daily_forecast.append(max(0.0, value))

    return MacroForecastResult(
        daily_forecast=daily_forecast,
        macro_daily_baseline=max(0.0, baseline),
    )