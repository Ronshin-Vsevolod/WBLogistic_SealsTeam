"""Macro-level 7-day demand forecaster."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "macro_daily_prophet.pkl"

_artifact_loaded = False
_artifact: dict[str, Any] | None = None


@dataclass
class MacroForecastResult:
    daily_forecast: list[float]
    macro_daily_baseline: float


def _load_artifact() -> bool:
    global _artifact_loaded, _artifact

    if _artifact_loaded:
        return _artifact is not None

    try:
        if not _MODEL_PATH.exists():
            logger.info("Macro ML artifact not found at %s — stub fallback", _MODEL_PATH)
            _artifact_loaded = True
            return False

        raw = joblib.load(_MODEL_PATH)

        if not isinstance(raw, dict) or "models" not in raw:
            logger.warning("Macro artifact unexpected structure — stub fallback")
            _artifact_loaded = True
            return False

        _artifact = raw
        _artifact_loaded = True
        logger.info("Macro ML artifact loaded — %d office models", len(_artifact["models"]))
        return True

    except Exception:
        logger.warning("Failed to load macro ML artifact", exc_info=True)
        _artifact_loaded = True
        _artifact = None
        return False


def _predict_macro_raw_ml(
    timestamp: int,
    office_from_id: int,
    macro_weather: list[float],
    promo: list[float],
) -> list[float] | None:
    if not _load_artifact() or _artifact is None:
        return None

    models_dict: dict = _artifact["models"]
    model = models_dict.get(office_from_id)

    if model is None:
        logger.info(
            "No Prophet model for office_from_id=%s — stub fallback",
            office_from_id,
        )
        return None

    try:
        import pandas as pd

        base_date = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc).date()
        future_dates = pd.date_range(start=base_date, periods=7, freq="D")

        future_df = pd.DataFrame({
            "ds": future_dates,
            "macro_weather": macro_weather[:7],
            "promo": promo[:7],
        })

        forecast = model.predict(future_df)
        raw_daily = [max(0.0, float(v)) for v in forecast["yhat"].tolist()[:7]]

        if len(raw_daily) != 7:
            raise ValueError(f"Prophet returned {len(raw_daily)} rows, expected 7")

        logger.info("Macro ML inference OK for office_from_id=%s", office_from_id)
        return raw_daily

    except Exception:
        logger.warning(
            "Macro ML inference failed for office_from_id=%s — stub fallback",
            office_from_id,
            exc_info=True,
        )
        return None


def _predict_macro_raw_stub(statuses: list[float]) -> list[float]:
    baseline = sum(statuses) / len(statuses) if statuses else 0.0
    return [max(0.0, baseline)] * 7


def _apply_macro_integrations(
    *,
    raw_daily_forecast: list[float],
    macro_weather: list[float],
    promo: list[float],
) -> list[float]:
    adjusted: list[float] = []
    for day_idx, raw_value in enumerate(raw_daily_forecast):
        w_val = macro_weather[day_idx] if day_idx < len(macro_weather) else 0.0
        p_val = promo[day_idx] if day_idx < len(promo) else 0.0
        weather_factor = 1.0 + w_val * 0.01
        promo_factor = 1.0 + p_val * 0.1
        adjusted.append(max(0.0, float(raw_value * weather_factor * promo_factor)))
    return adjusted


def predict_macro(
    statuses: list[float],
    macro_weather: list[float],
    promo: list[float],
    timestamp: int | None = None,
    office_from_id: int | None = None,
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
        Request timestamp in milliseconds (required for ML inference).
    office_from_id:
        Warehouse identifier — selects the per-office Prophet model.
    runtime_mode:
        ``"auto"`` → try ML, fallback to stub;
        ``"stub"`` → stub only;
        ``"ml"``   → require ML, raise if unavailable.
    """
    if runtime_mode not in {"auto", "stub", "ml"}:
        raise ValueError("runtime_mode must be one of: auto, stub, ml")

    raw_daily: list[float] | None = None

    if runtime_mode != "stub" and timestamp is not None and office_from_id is not None:
        # Pass real integration values from Java into Prophet future_df.
        # Prophet applies them internally — yhat already reflects the signal.
        raw_daily = _predict_macro_raw_ml(
            timestamp=timestamp,
            office_from_id=office_from_id,
            macro_weather=macro_weather,
            promo=promo,
        )

    if raw_daily is None:
        if runtime_mode == "ml":
            raise RuntimeError(
                f"Macro ML inference unavailable (office_from_id={office_from_id})"
            )
        # ML unavailable — flat stub baseline, apply integration signal manually.
        raw_daily = _predict_macro_raw_stub(statuses)
        daily_forecast = _apply_macro_integrations(
            raw_daily_forecast=raw_daily,
            macro_weather=macro_weather,
            promo=promo,
        )
    else:
        # ML succeeded — Prophet already consumed macro_weather and promo
        # via regressor columns in future_df. Only clamp negatives.
        daily_forecast = [max(0.0, float(v)) for v in raw_daily]

    baseline = sum(statuses) / len(statuses) if statuses else 0.0

    return MacroForecastResult(
        daily_forecast=daily_forecast,
        macro_daily_baseline=max(0.0, baseline),
    )