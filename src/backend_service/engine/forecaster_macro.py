"""Macro-level 7-day demand forecaster.

Architecture
------------
This module exposes one stable public function: ``predict_macro(...)``.

Internally it uses a two-stage pipeline:

1. Raw forecast source
   - preferred: trained raw-data macro model (when runtime context and
     artifacts are available)
   - fallback: deterministic raw stub

2. Product adjustments
   - macroWeather
   - promo

This keeps leaderboard-oriented raw ML separated from product-only
integrations while preserving one public API for the backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "macro_daily_prophet.pkl"

_model_loaded = False
_prophet_model: Any | None = None


@dataclass
class MacroForecastResult:
    daily_forecast: list[float]
    macro_daily_baseline: float


def _load_prophet() -> bool:
    """Lazy-load macro ML artifact."""
    global _model_loaded, _prophet_model

    if _model_loaded:
        return _prophet_model is not None

    try:
        if not _MODEL_PATH.exists():
            logger.info("Macro ML artifact not found — stub fallback will be used")
            _model_loaded = True
            return False

        _prophet_model = joblib.load(_MODEL_PATH)
        _model_loaded = True
        logger.info("Macro ML artifact loaded successfully")
        return True
    except Exception:
        logger.warning("Failed to load macro ML artifact", exc_info=True)
        _model_loaded = True
        _prophet_model = None
        return False


def _predict_macro_raw_ml(timestamp: int | None) -> list[float] | None:
    """Try to produce a raw 7-day forecast from the trained macro model.

    Returns ``None`` when ML inference is not possible.
    """
    if timestamp is None:
        logger.info("Macro ML runtime missing timestamp → fallback to stub")
        return None

    if not _load_prophet():
        return None

    try:
        import pandas as pd
        from datetime import datetime, timezone

        base_date = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc).date()
        future_dates = pd.date_range(start=base_date, periods=7, freq="D")
        future_df = pd.DataFrame({"ds": future_dates})

        forecast = _prophet_model.predict(future_df)
        raw_daily = [max(0.0, float(v)) for v in forecast["yhat"].tolist()[:7]]

        if len(raw_daily) != 7:
            raise ValueError(f"Macro ML returned {len(raw_daily)} rows instead of 7")

        return raw_daily
    except Exception:
        logger.warning("Macro ML inference failed — stub fallback will be used", exc_info=True)
        return None


def _predict_macro_raw_stub(statuses: list[float]) -> list[float]:
    """Produce a raw 7-day baseline without integrations."""
    baseline = sum(statuses) / len(statuses) if statuses else 0.0
    baseline = max(0.0, baseline)
    return [baseline] * 7


def _apply_macro_integrations(
    *,
    raw_daily_forecast: list[float],
    macro_weather: list[float],
    promo: list[float],
) -> list[float]:
    """Apply product-level integration adjustments to a raw macro forecast."""
    adjusted: list[float] = []

    for day_idx, raw_value in enumerate(raw_daily_forecast):
        w_val = macro_weather[day_idx] if day_idx < len(macro_weather) else 0.0
        p_val = promo[day_idx] if day_idx < len(promo) else 0.0

        weather_factor = 1.0 + w_val * 0.01
        promo_factor = 1.0 + p_val * 0.1

        value = raw_value * weather_factor * promo_factor
        adjusted.append(max(0.0, float(value)))

    return adjusted


def predict_macro(
    statuses: list[float],
    macro_weather: list[float],
    promo: list[float],
    timestamp: int | None = None,
    runtime_mode: str = "auto",
) -> MacroForecastResult:
    """Produce a 7-day product forecast.

    Parameters
    ----------
    statuses:
        Current warehouse status values (``status1`` … ``status8``).
    macro_weather:
        Seven macro-weather values, one per forecast day.
    promo:
        Seven promo values, one per forecast day.
    timestamp:
        Optional request timestamp required for ML runtime inference.
    runtime_mode:
        ``"auto"`` → try ML, fallback to stub;
        ``"stub"`` → use stub only;
        ``"ml"``   → require ML, otherwise raise.

    Returns
    -------
    MacroForecastResult
        Contains ``daily_forecast`` (length 7) and
        ``macro_daily_baseline``.
    """
    if runtime_mode not in {"auto", "stub", "ml"}:
        raise ValueError("runtime_mode must be one of: auto, stub, ml")

    raw_daily: list[float] | None = None

    if runtime_mode != "stub":
        raw_daily = _predict_macro_raw_ml(timestamp)

    if raw_daily is None:
        if runtime_mode == "ml":
            raise RuntimeError("Macro ML inference requested but unavailable")
        raw_daily = _predict_macro_raw_stub(statuses)

    adjusted_daily = _apply_macro_integrations(
        raw_daily_forecast=raw_daily,
        macro_weather=macro_weather,
        promo=promo,
    )

    baseline = sum(statuses) / len(statuses) if statuses else 0.0

    return MacroForecastResult(
        daily_forecast=adjusted_daily,
        macro_daily_baseline=max(0.0, baseline),
    )