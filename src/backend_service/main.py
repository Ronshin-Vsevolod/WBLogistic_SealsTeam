"""Application entry-point.

Run with:
    uvicorn backend_service.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from backend_service.api.routers import router
from backend_service.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail fast on invalid config
    logger.info(
        "Config loaded – step=%d min, horizon=%d steps, truck=%.1f t",
        settings.micro_step_minutes,
        settings.micro_horizon_steps,
        settings.truck_capacity,
    )
    yield


app = FastAPI(
    title="Python ML Engine",
    version="0.1.0",
    description="Stateless computation engine for logistics dispatch forecasting",
    lifespan=lifespan,
)
app.include_router(router)