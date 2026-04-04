import json

from backend_service.core.feature_logger import FeatureLogger


def test_feature_logger_writes_jsonl(tmp_path):
    fl = FeatureLogger(log_dir=tmp_path, enabled=True)

    fl.log_inference(
        request_data={"officeFromId": 1},
        response_data={"dispatches": [], "tacticalPlan": []},
        pipeline_state={
            "macro_daily_baseline": 10.0,
            "daily_forecast": [1, 2, 3],
            "micro_forecast": [0.1, 0.2],
        },
        inference_duration_ms=12.34,
    )

    files = list(tmp_path.glob("features_*.jsonl"))
    assert len(files) == 1

    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert "request" in record
    assert "response" in record
    assert "pipeline_state" in record
    assert record["inference_duration_ms"] == 12.34