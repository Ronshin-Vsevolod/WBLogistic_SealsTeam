"""Integration tests for the HTTP API."""

import copy
from fastapi.testclient import TestClient

from backend_service.main import app

client = TestClient(app)

_VALID_PAYLOAD = {
    "officeFromId": 42,
    "routeId": 101,
    "timestamp": 1718438400000,
    "status1": 10.0,
    "status2": 20.0,
    "status3": 30.0,
    "status4": 40.0,
    "status5": 50.0,
    "status6": 60.0,
    "status7": 70.0,
    "status8": 80.0,
    "integrations": {
        "microWeather": [0.0, 1.0, 2.0, 1.5, 0.5],
        "traffic": 0.3,
        "promo": [0.5] * 7,
        "macroWeather": [1.0, 2.0, 1.0, 0.5, 3.0, 0.5, 1.5],
    },
}


class TestHealth:
    def test_returns_200_with_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
#  POST /predict — happy path
# ═══════════════════════════════════════════════════════════════════


class TestPredictHappyPath:
    """All tests in this class send the same valid payload."""

    def test_returns_200(self):
        resp = client.post("/predict", json=_VALID_PAYLOAD)
        assert resp.status_code == 200

    def test_response_contains_dispatches(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        assert "dispatches" in data
        assert isinstance(data["dispatches"], list)

    def test_response_contains_tactical_plan(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        assert "tacticalPlan" in data
        assert isinstance(data["tacticalPlan"], list)
        assert len(data["tacticalPlan"]) == 7

    # ── camelCase verification ──────────────────────────────────

    def test_tactical_plan_uses_camel_case(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        row = data["tacticalPlan"][0]
        for expected_key in ("warehouseId", "planDate",
                             "forecastVolume", "requiredTrucks"):
            assert expected_key in row, f"missing camelCase key {expected_key}"
        # snake_case must not leak into external JSON
        for leaked_key in ("warehouse_id", "plan_date",
                           "forecast_volume", "required_trucks"):
            assert leaked_key not in row, f"snake_case key leaked: {leaked_key}"

    def test_dispatches_use_camel_case(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        assert len(data["dispatches"]) > 0, (
            "expected dispatches for the default payload"
        )
        d = data["dispatches"][0]
        for expected_key in ("warehouseId", "routeId", "scheduledAt",
                             "vehicleType", "expectedVolume",
                             "vehicleCapacity", "fillRate",
                             "triggerReason", "priority"):
            assert expected_key in d, f"missing camelCase key {expected_key}"

    # ── real-pipeline verification ──────────────────────────────

    def test_uses_real_pipeline_not_placeholder(self):
        """The route must return computed values, not an empty stub."""
        data = client.post("/predict", json=_VALID_PAYLOAD).json()

        # Tactical plan contains real forecast volumes
        assert any(
            row["forecastVolume"] > 0.0
            for row in data["tacticalPlan"]
        )

        # Dispatches are produced (statuses mean ≈ 45 with
        # truck_capacity=100 → capacity dispatches fire)
        assert len(data["dispatches"]) > 0

    def test_dispatch_fill_rate_within_bounds(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        for d in data["dispatches"]:
            assert 0.0 <= d["fillRate"] <= 1.0

    def test_tactical_plan_trucks_non_negative(self):
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        for row in data["tacticalPlan"]:
            assert row["requiredTrucks"] >= 0

    def test_macro_baseline_not_exposed(self):
        """macro_daily_baseline is internal and must never appear in
        the public response."""
        data = client.post("/predict", json=_VALID_PAYLOAD).json()
        raw = str(data)
        assert "macro_daily_baseline" not in raw
        assert "macroDailyBaseline" not in raw


# ═══════════════════════════════════════════════════════════════════
#  POST /predict — validation
# ═══════════════════════════════════════════════════════════════════


class TestPredictValidation:
    def test_empty_body_returns_422(self):
        resp = client.post("/predict", json={})
        assert resp.status_code == 422

    def test_missing_integrations_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items()
                   if k != "integrations"}
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 422

    def test_missing_status_field_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items()
                   if k != "status1"}
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 422

    def test_missing_route_id_returns_422(self):
        payload = {k: v for k, v in _VALID_PAYLOAD.items()
                   if k != "routeId"}
        resp = client.post("/predict", json=payload)
        assert resp.status_code == 422