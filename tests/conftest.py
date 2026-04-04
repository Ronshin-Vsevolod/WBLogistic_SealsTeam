"""Shared fixtures for the test suite."""

import pytest
from fastapi.testclient import TestClient

from backend_service.core.config import get_settings
from backend_service.main import app


@pytest.fixture()
def client():
    """Provide a TestClient with lifespan properly managed."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def valid_request_payload() -> dict:
    """A known-good request payload using the camelCase contract."""
    return {
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
        "integrations": {
            "microWeather": [2.0, 2.5, 3.0, 3.5, 3.0],
            "traffic": 3.0,
            "macroWeather": [2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 2.0],
            "promo": [2.0, 1.0, 1.0, 3.0, 2.0, 1.0, 1.0],
        },
    }


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Ensure each test starts with a fresh settings cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()