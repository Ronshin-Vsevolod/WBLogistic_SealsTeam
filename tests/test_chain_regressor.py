import os

import numpy as np
import polars as pl
import pytest

from src.ml_pipeline.train_micro import ChainRegressorEnsemble


def test_pipeline_runs():
    """Test that the full evaluation pipeline runs without errors."""
    n = 500
    start_dt = pl.datetime(2023, 1, 1)
    # Гарантируем ровно n элементов во временном ряду
    end_dt = start_dt + pl.duration(hours=n - 1)

    df = pl.DataFrame(
        {
            "office_from_id": np.random.randint(1, 5, n),
            "route_id": np.ones(n, dtype=np.int32),
            "timestamp": pl.datetime_range(start=start_dt, end=end_dt, interval="1h", eager=True),
            "status_1": np.random.randint(0, 10, n),
            "target_2h": np.random.rand(n),
        }
    )

    config = {"n_splits": 2, "test_size": 50}
    model = ChainRegressorEnsemble(df, config=config)

    result = model.evaluate()

    assert "oof_score" in result
    assert "best_k" in result
    assert result["best_k"].shape[0] == 10


def test_prediction_shape():
    """Test that the internal fit and predict yield the correct shape (N, 10)."""
    n = 300
    start_dt = pl.datetime(2023, 1, 1)
    end_dt = start_dt + pl.duration(hours=n - 1)

    df = pl.DataFrame(
        {
            "office_from_id": np.random.randint(1, 3, n),
            "route_id": np.random.randint(1, 5, n),
            "timestamp": pl.datetime_range(start=start_dt, end=end_dt, interval="1h", eager=True),
            "status_1": np.random.randint(0, 10, n),
            "target_2h": np.random.rand(n),
        }
    ).with_columns(
        [
            pl.col("office_from_id").cast(pl.Int64),
            pl.col("route_id").cast(pl.Int64),
        ]
    )

    model = ChainRegressorEnsemble(df)

    X = model._get_feature_matrix()
    y = model.df.select(model.target_cols).to_numpy()

    models = model._fit_fold(X, y)
    preds = model._predict_ensemble(models, X)

    assert preds.shape[1] == 10
    assert preds.shape[0] == X.shape[0]


def test_calibration_improves_metric():
    """Test that the Nelder-Mead optimization successfully reduces/retains the metric."""
    y_true = np.random.rand(100, 10)
    y_pred = y_true * 0.8  # Создаём искусственное смещение

    model = ChainRegressorEnsemble.__new__(ChainRegressorEnsemble)
    model.horizon = 10

    raw = model.metric.calculate(y_true, y_pred)
    k = model._optimize_k(y_true, y_pred)
    calibrated = model.metric.calculate(y_true, y_pred * k)

    assert calibrated <= raw


def test_model_saving(tmp_path):
    """Test that training on the full dataset saves artifacts to disk."""
    n = 200
    start_dt = pl.datetime(2023, 1, 1)
    end_dt = start_dt + pl.duration(hours=n - 1)

    df = pl.DataFrame(
        {
            "office_from_id": np.random.randint(1, 3, n),
            "route_id": np.random.randint(1, 5, n),
            "timestamp": pl.datetime_range(start=start_dt, end=end_dt, interval="1h", eager=True),
            "status_1": np.random.randint(0, 10, n),
            "target_2h": np.random.rand(n),
        }
    )

    config = {"n_splits": 2, "test_size": 30}
    model = ChainRegressorEnsemble(df, config=config)
    result = model.evaluate()

    model.model_dir = str(tmp_path)
    model.train_full_save(result["best_k"])

    assert (tmp_path / "best_k_multiplier.json").exists()
    assert (tmp_path / "micro_chain_catboost.cbm").exists()
    assert (tmp_path / "micro_chain_lightgbm.txt").exists()


def test_catboost_multi_mode():
    """Test that the fallback 'catboost_multi' mode runs and creates artifacts."""
    n = 200
    start_dt = pl.datetime(2023, 1, 1)
    end_dt = start_dt + pl.duration(hours=n - 1)

    df = pl.DataFrame(
        {
            "office_from_id": np.random.randint(1, 3, n),
            "route_id": np.random.randint(1, 5, n),
            "timestamp": pl.datetime_range(start=start_dt, end=end_dt, interval="1h", eager=True),
            "status_1": np.random.randint(0, 10, n),
            "target_2h": np.random.rand(n),
        }
    )

    # Переключаем режим на direct multi-output
    config = {"n_splits": 2, "test_size": 30, "mode": "catboost_multi"}
    model = ChainRegressorEnsemble(df, config=config)

    result = model.evaluate()

    assert "oof_score" in result
    assert result["best_k"].shape[0] == 10
