from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import warnings
"""Micro-level intra-day demand forecaster.

Architecture
------------
This module exposes one stable public function: ``predict_micro(...)``.

Internally it uses a two-stage pipeline:

1. Raw forecast source
   - preferred: trained raw-data ML models (when runtime context and
     artifacts are available)
   - fallback: deterministic raw stub

2. Product adjustments
   - microWeather interpolation
   - traffic modulation
"""

logger = logging.getLogger(__name__)

_CONTROL_HOURS: list[float] = [0.0, 3.0, 6.0, 9.0, 12.0]

_MODEL_DIR = Path(__file__).resolve().parents[3] / "models"
_CAT_PATH = _MODEL_DIR / "micro_chain_catboost.cbm"
_LGBM_PATH = _MODEL_DIR / "micro_chain_lightgbm.txt"
_K_PATH = _MODEL_DIR / "best_k_multiplier.json"
_UNCERTAINTY_PATH = _MODEL_DIR / "micro_uncertainty_profile.json"
_SCHEMA_PATH = _MODEL_DIR / "micro_feature_schema.json"

_models_loaded = False
_model_cat: Any | None = None
_model_lgbm: Any | None = None
_best_k: np.ndarray | None = None
_margins: np.ndarray | None = None
_feature_cols: list[str] | None = None


@dataclass
class MicroForecastResult:
    """Outcome of a micro forecast run with uncertainty bounds.
    
    Attributes
    ----------
    mean:
        The expected intra-day volume forecast (point prediction).
    lower:
        The optimistic/safe lower bound (e.g., based on p90 residuals).
    upper:
        The pessimistic upper bound used to evaluate maximum potential demand.
    """
    mean: list[float]
    lower: list[float]
    upper: list[float]


def _steps_per_day(step_minutes: int) -> float:
    return (24.0 * 60.0) / step_minutes


def _interpolate_control(control_hours: list[float], control_values: list[float], query_hour: float) -> float:
    if not control_values: return 0.0
    if len(control_values) == 1: return control_values[0]
    if query_hour <= control_hours[0]: return control_values[0]
    if query_hour >= control_hours[-1]: return control_values[-1]

    for i in range(len(control_hours) - 1):
        h_lo, h_hi = control_hours[i], control_hours[i + 1]
        if h_lo <= query_hour <= h_hi:
            t = (query_hour - h_lo) / (h_hi - h_lo)
            return control_values[i] + t * (control_values[i + 1] - control_values[i])
    return control_values[-1]


def _load_models() -> bool:
    global _models_loaded, _model_cat, _model_lgbm, _best_k, _margins, _feature_cols

    if _models_loaded:
        return _model_cat is not None

    try:
        if not (
            _CAT_PATH.exists()
            and _LGBM_PATH.exists()
            and _K_PATH.exists()
            and _UNCERTAINTY_PATH.exists()
            and _SCHEMA_PATH.exists()
        ):
            logger.info("Micro ML artifacts not found — stub fallback will be used")
            _models_loaded = True
            return False

        _model_cat = joblib.load(_CAT_PATH)
        _model_lgbm = joblib.load(_LGBM_PATH)

        with open(_K_PATH, encoding="utf-8") as fh:
            k_raw = json.load(fh)
        _best_k = np.array([k_raw[f"k_{i}"] for i in range(10)], dtype=np.float32)

        with open(_UNCERTAINTY_PATH, encoding="utf-8") as fh:
            m_raw = json.load(fh)
        _margins = np.array(
            [m_raw[f"p90_abs_error_step_{i+1}"] for i in range(10)],
            dtype=np.float32,
        )

        with open(_SCHEMA_PATH, encoding="utf-8") as fh:
            _feature_cols = json.load(fh)

        _models_loaded = True
        logger.info(
            "Micro ML artifacts loaded successfully | features=%d",
            len(_feature_cols or []),
        )
        return True
    except Exception:
        logger.warning("Failed to load micro ML artifacts", exc_info=True)
        _models_loaded = True
        _model_cat = None
        _model_lgbm = None
        _best_k = None
        _margins = None
        _feature_cols = None
        return False


def _feature_enabled(name: str) -> bool:
    return _feature_cols is not None and name in _feature_cols

def _model_uses_weather_features() -> bool:
    return any(_feature_enabled(f"micro_weather_{i}") for i in range(5))

def _model_uses_traffic_feature() -> bool:
    return _feature_enabled("traffic")


def _build_micro_raw_features(
    *,
    statuses: list[float],
    timestamp: int,
    office_from_id: int,
    route_id: int,
    traffic: float,
    micro_weather: list[float],
    macro_daily_baseline: float,
) -> np.ndarray:
    """Build a single-row numpy object array matching the training schema.

    Model was trained on numpy arrays with positional feature names '0'..'16'.
    Columns 0 (office_from_id) and 1 (route_id) must be strings — CatBoost
    inferred cat_feature_indices=[0,1] from object dtype during training.
    All other columns are float.

    Column order must exactly match micro_feature_schema.json:
        office_from_id, route_id, status_1..8,
        macro_daily_baseline, traffic, micro_weather_0..4
    """
    if _feature_cols is None:
        raise RuntimeError("Feature schema not loaded")

    values: dict[str, object] = {}

    values["office_from_id"] = str(office_from_id)
    values["route_id"] = str(route_id)

    for i, value in enumerate(statuses[:8], start=1):
        values[f"status_{i}"] = float(value)

    values["macro_daily_baseline"] = float(macro_daily_baseline)
    values["traffic"] = float(traffic)

    for i in range(5):
        values[f"micro_weather_{i}"] = float(micro_weather[i]) if i < len(micro_weather) else 0.0

    # Build row in exact schema order
    row = [values[col] for col in _feature_cols if col in values]

    return np.array([row], dtype=object)


def _predict_chain_manual(chain, X: np.ndarray) -> np.ndarray:
    """Run RegressorChain inference manually to preserve object dtype.

    RegressorChain.predict() passes data through sklearn's validate_data()
    which converts object arrays to float64, breaking CatBoost cat_features.
    We replicate the chain logic directly: each estimator gets X augmented
    with all previous predictions appended as new columns.
    """
    X_curr = X.copy()
    predictions = []

    for estimator in chain.estimators_:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="X does not have valid feature names",
                category=UserWarning,
            )
            pred = estimator.predict(X_curr)
        predictions.append(pred[0])
        X_curr = np.hstack([X_curr, pred.reshape(-1, 1)])

    return np.array(predictions, dtype=np.float32)


def _predict_micro_raw_ml(
    statuses: list[float],
    micro_weather: list[float],
    traffic: float,
    macro_daily_baseline: float,
    micro_horizon_steps: int,
    timestamp: int | None,
    office_from_id: int | None,
    route_id: int | None,
) -> MicroForecastResult | None:
    if micro_horizon_steps != 10 or timestamp is None or office_from_id is None or route_id is None:
        return None

    if not _load_models() or _best_k is None or _margins is None:
        return None

    try:
        X = _build_micro_raw_features(
            statuses=statuses,
            timestamp=timestamp,
            office_from_id=office_from_id,
            route_id=route_id,
            traffic=traffic,
            micro_weather=micro_weather,
            macro_daily_baseline=macro_daily_baseline,
        )

        pred_cat = _predict_chain_manual(_model_cat, X)
        pred_lgbm = _predict_chain_manual(_model_lgbm, X)

        mean_pred = ((pred_cat + pred_lgbm) / 2.0) * _best_k
        mean_pred = np.maximum(mean_pred, 0.0)

        lower_pred = np.maximum(mean_pred - _margins, 0.0)
        upper_pred = mean_pred + _margins

        return MicroForecastResult(
            mean=mean_pred.tolist(),
            lower=lower_pred.tolist(),
            upper=upper_pred.tolist(),
        )
    except Exception:
        logger.warning("Micro ML inference failed — stub fallback will be used", exc_info=True)
        return None


def _predict_micro_raw_stub(statuses: list[float], macro_daily_baseline: float, micro_horizon_steps: int, micro_step_minutes: int) -> MicroForecastResult:
    steps_per_day = _steps_per_day(micro_step_minutes)
    if macro_daily_baseline > 0:
        base = macro_daily_baseline / steps_per_day
    elif statuses:
        fallback_daily = max(sum(statuses) / len(statuses), 0.0)
        base = (fallback_daily / steps_per_day) if fallback_daily > 0 else 1.0
    else:
        base = 1.0

    forecast = [max(0.0, base)] * micro_horizon_steps
    return MicroForecastResult(mean=forecast, lower=forecast, upper=forecast)


def _apply_micro_integrations(raw_result: MicroForecastResult, micro_weather: list[float], traffic: float, micro_step_minutes: int) -> MicroForecastResult:
    def adjust(raw_list: list[float]) -> list[float]:
        adjusted = []
        for step, raw_value in enumerate(raw_list):
            step_hour = (step * micro_step_minutes) / 60.0
            w_val = _interpolate_control(_CONTROL_HOURS, micro_weather, step_hour)
            factor = (1.0 + w_val * 0.01) * (1.0 + traffic * 0.05)
            adjusted.append(max(0.0, float(raw_value * factor)))
        return adjusted

    return MicroForecastResult(
        mean=adjust(raw_result.mean),
        lower=adjust(raw_result.lower),
        upper=adjust(raw_result.upper),
    )


def predict_micro(
    statuses: list[float],
    micro_weather: list[float],
    traffic: float,
    macro_daily_baseline: float,
    micro_horizon_steps: int,
    micro_step_minutes: int,
    timestamp: int | None = None,
    office_from_id: int | None = None,
    route_id: int | None = None,
    runtime_mode: str = "auto",
) -> MicroForecastResult:
    """Produce an intra-day product forecast with uncertainty bounds.
    
    Uses ML artifacts and residual profiles if available, otherwise falls
    back to a deterministic stub (where lower == mean == upper).
    ...
    Returns
    -------
    MicroForecastResult
        Dataclass containing `mean`, `lower`, and `upper` forecast vectors,
        each of length exactly ``micro_horizon_steps`` (every value ≥ 0).
    """
    raw_result = None
    if runtime_mode != "stub":
        raw_result = _predict_micro_raw_ml(
            statuses=statuses,
            micro_weather=micro_weather,
            traffic=traffic,
            macro_daily_baseline=macro_daily_baseline,
            micro_horizon_steps=micro_horizon_steps,
            timestamp=timestamp,
            office_from_id=office_from_id,
            route_id=route_id,
        )
    if raw_result is None:
        raw_result = _predict_micro_raw_stub(statuses, macro_daily_baseline, micro_horizon_steps, micro_step_minutes)

    return _apply_micro_integrations(raw_result, micro_weather, traffic, micro_step_minutes)