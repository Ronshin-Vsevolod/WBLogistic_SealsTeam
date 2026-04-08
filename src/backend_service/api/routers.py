"""FastAPI routes — wires the HTTP API to the internal forecast and
dispatch pipeline.

Responsibilities
----------------
* Accept validated JSON (camelCase from Java)
* Orchestrate: macro forecast → micro forecast → dispatch → tactical plan
* Map internal snake_case engine objects to camelCase response models
* Return typed Pydantic responses

No business math lives here — all computation is delegated to the
engine layer.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

from backend_service.engine.forecaster_macro import predict_macro
from backend_service.engine.forecaster_micro import predict_micro
from backend_service.engine.auto_dispatcher import (
    DispatchRequest as _EngineDispatch,
    TacticalPlanRow as _EngineTacticalRow,
    generate_dispatches,
    build_tactical_plan,
)
from backend_service.api.schemas import ForecastRequest
from backend_service.core.config import get_settings
from backend_service.core.feature_logger import get_feature_logger

logger = logging.getLogger(__name__)
router = APIRouter()

# ═══════════════════════════════════════════════════════════════════
#  Response schemas (camelCase aliases → Java contract)
# ═══════════════════════════════════════════════════════════════════


class _DispatchItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    warehouse_id: str = Field(alias="warehouseId")
    route_id: int = Field(alias="routeId")
    scheduled_at: datetime = Field(alias="scheduledAt")
    vehicle_type: str = Field(alias="vehicleType")
    expected_volume: float = Field(alias="expectedVolume")
    vehicle_capacity: float = Field(alias="vehicleCapacity")
    fill_rate: float = Field(alias="fillRate")
    trigger_reason: str = Field(alias="triggerReason")
    priority: int


class _TacticalPlanItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    warehouse_id: str = Field(alias="warehouseId")
    plan_date: date = Field(alias="planDate")
    forecast_volume: float = Field(alias="forecastVolume")
    required_trucks: int = Field(alias="requiredTrucks")


class PredictResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dispatches: list[_DispatchItem]
    tactical_plan: list[_TacticalPlanItem] = Field(alias="tacticalPlan")

# ═══════════════════════════════════════════════════════════════════
#  Internal helpers — request unpacking & response mapping
# ═══════════════════════════════════════════════════════════════════


def _extract_statuses(req: ForecastRequest) -> list[float]:
    """Collect ``status1`` … ``status8`` into a flat list."""
    return [
        req.status1, req.status2, req.status3, req.status4,
        req.status5, req.status6, req.status7, req.status8,
    ]


def _map_dispatch(d: _EngineDispatch) -> _DispatchItem:
    """Engine dataclass → API response model (camelCase via alias)."""
    return _DispatchItem(
        warehouse_id=d.warehouse_id,
        route_id=d.route_id,
        scheduled_at=d.scheduled_at,
        vehicle_type=d.vehicle_type,
        expected_volume=d.expected_volume,
        vehicle_capacity=d.vehicle_capacity,
        fill_rate=d.fill_rate,
        trigger_reason=d.trigger_reason,
        priority=d.priority,
    )


def _map_tactical(t: _EngineTacticalRow) -> _TacticalPlanItem:
    """Engine dataclass → API response model (camelCase via alias)."""
    return _TacticalPlanItem(
        warehouse_id=t.warehouse_id,
        plan_date=t.plan_date,
        forecast_volume=t.forecast_volume,
        required_trucks=t.required_trucks,
    )

# ═══════════════════════════════════════════════════════════════════
#  Background logging helper
# ═══════════════════════════════════════════════════════════════════


def _background_log_inference(
    request: ForecastRequest,
    response: PredictResponse,
    macro_daily_baseline: float,
    daily_forecast: list[float],
    micro_forecast_mean: list[float],
    micro_forecast_lower: list[float],
    micro_forecast_upper: list[float],
    inference_ms: float,
) -> None:
    """Background task: serialise and persist the inference payload.

    Captures intermediate pipeline state (macro baseline and the full
    micro forecast distribution: mean / lower / upper) that is not
    exposed in the public API response.
    """
    try:
        fl = get_feature_logger()
        fl.log_inference(
            request_data=request.model_dump(by_alias=True),
            response_data=response.model_dump(by_alias=True),
            pipeline_state={
                "macro_daily_baseline": macro_daily_baseline,
                "daily_forecast": daily_forecast,
                "micro_forecast_mean": micro_forecast_mean,
                "micro_forecast_lower": micro_forecast_lower,
                "micro_forecast_upper": micro_forecast_upper,
            },
            inference_duration_ms=inference_ms,
        )
    except Exception:
        logger.warning("Feature logging background task failed", exc_info=True)


# ═══════════════════════════════════════════════════════════════════
#  Routes
# ═══════════════════════════════════════════════════════════════════


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — smoke tests, Docker healthchecks, and quick
    verification before calling ``/predict``."""
    return {"status": "ok"}


@router.post("/predict", response_model=PredictResponse)
async def predict(
    request: ForecastRequest,
    background_tasks: BackgroundTasks,
) -> PredictResponse:
    """Run the full forecast → dispatch pipeline.

    Orchestration order
    -------------------
    1. Macro forecast  – 7-day daily volumes
    2. Micro forecast  – intra-day steps (uses macro baseline)
    3. Dispatch engine  – capacity / SLA dispatch generation
    4. Tactical plan    – weekly truck-requirement summary
    5. Feature logging  – async background capture to ``.jsonl``
    """
    t_start = time.perf_counter()

    settings = get_settings()
    statuses = _extract_statuses(request)

    # ── 1. Macro forecast ───────────────────────────────────────
    macro_result = predict_macro(
        statuses=statuses,
        macro_weather=request.integrations.macro_weather,
        promo=request.integrations.promo,
        timestamp=request.timestamp,
        runtime_mode="auto",
    )
    # macro_result.macro_daily_baseline is internal pipeline state
    # and must NOT appear in the public response.

    # ── 2. Micro forecast ───────────────────────────────────────
    micro_result = predict_micro(
        statuses=statuses,
        micro_weather=request.integrations.micro_weather,
        traffic=request.integrations.traffic,
        macro_daily_baseline=macro_result.macro_daily_baseline,
        micro_horizon_steps=settings.micro_horizon_steps,
        micro_step_minutes=settings.micro_step_minutes,
        timestamp=request.timestamp,
        office_from_id=request.office_from_id,
        route_id=request.route_id,
        runtime_mode="auto",
    )

    # ── 3. Dispatch generation ──────────────────────────────────
    engine_dispatches = generate_dispatches(
        office_from_id=request.office_from_id,
        route_id=request.route_id,
        timestamp=request.timestamp,
        micro_forecast=micro_result.mean,
        micro_forecast_upper=micro_result.upper,
        settings=settings,
    )

    # ── 4. Tactical plan ────────────────────────────────────────
    engine_plan = build_tactical_plan(
        office_from_id=request.office_from_id,
        timestamp=request.timestamp,
        daily_forecast=macro_result.daily_forecast,
        truck_capacity=settings.truck_capacity,
    )

    # ── 5. Map to API response models ───────────────────────────
    response = PredictResponse(
        dispatches=[_map_dispatch(d) for d in engine_dispatches],
        tactical_plan=[_map_tactical(t) for t in engine_plan],
    )

    # ── 6. Schedule background feature logging ──────────────────
    t_end = time.perf_counter()
    inference_ms = (t_end - t_start) * 1000.0

    background_tasks.add_task(
        _background_log_inference,
        request=request,
        response=response,
        macro_daily_baseline=macro_result.macro_daily_baseline,
        daily_forecast=macro_result.daily_forecast,
        micro_forecast_mean=micro_result.mean,
        micro_forecast_lower=micro_result.lower,
        micro_forecast_upper=micro_result.upper,
        inference_ms=inference_ms,
    )


    return response