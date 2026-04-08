import gc
import json
import os
import logging

import joblib
import numpy as np
import pandas as pd
import polars as pl
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
from scipy.optimize import minimize
from sklearn.model_selection import TimeSeriesSplit
from sklearn.multioutput import RegressorChain

from .metrics import WapePlusRbias

import warnings
logger = logging.getLogger(__name__)
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names, but LGBMRegressor was fitted with feature names",
    category=UserWarning,
)

def add_product_mvp_features(df: pl.DataFrame) -> pl.DataFrame:
    """Add MVP product features for micro ML.

    Notes
    -----
    * ``target_2h`` stays the supervised target only.
    * Integrations are synthetic at train time, but runtime will receive
      real values from Java IntegrationService.
    * ``macro_daily_baseline`` is currently a proxy based on current statuses.
    """
    status_cols = [f"status_{i}" for i in range(1, 9)]

    # Proxy macro baseline from current warehouse state
    macro_baseline_expr = (
        sum(pl.col(col) for col in status_cols) / len(status_cols)
    ).alias("macro_daily_baseline")

    # Simple deterministic traffic proxy from current total load
    traffic_expr = (
        (
            sum(pl.col(col) for col in status_cols) / 1000.0
        ).clip(0.0, 10.0)
    ).alias("traffic")

    # Deterministic synthetic micro-weather control points
    # based on current status mix (cheap MVP proxy)
    weather_base = (
        (pl.col("status_1") + pl.col("status_2") + pl.col("status_3")) / 3000.0
    ).clip(0.0, 10.0)

    return df.with_columns(
        [
            macro_baseline_expr,
            traffic_expr,
            weather_base.alias("micro_weather_0"),
            (weather_base * 1.05).clip(0.0, 10.0).alias("micro_weather_1"),
            (weather_base * 1.10).clip(0.0, 10.0).alias("micro_weather_2"),
            (weather_base * 1.15).clip(0.0, 10.0).alias("micro_weather_3"),
            (weather_base * 1.10).clip(0.0, 10.0).alias("micro_weather_4"),
        ]
    )

class ChainRegressorEnsemble:
    """
    An ensemble of Regressor Chains using CatBoost and LightGBM for multi-step
    time series forecasting, with built-in calibration and cross-validation.

    Parameters
    ----------
    df : pl.DataFrame
        Input dataset containing features, timestamps, and the base target.
    config : dict, optional
        Configuration dictionary for hyperparameters, seeds, and training mode.
        If None, default production parameters are used.
    """

    def __init__(self, df: pl.DataFrame, config: dict | None = None):
        self.df = df
        self.config = config or {}

        self.seed = self.config.get("seed", 42)
        self.mode = self.config.get("mode", "chain")  # "chain" or "catboost_multi"
        self.test_size = self.config.get("test_size", 10000)
        self.n_splits = self.config.get("n_splits", 3)
        self.max_train_size = self.config.get("max_train_size", 200000)
        self.tail_rows = self.config.get("tail_rows", 260000)

        self.target_col = "target_2h"
        self.horizon = 10
        self.model_dir = "models"

        self.target_cols = []
        self.feature_cols = []
        self.cat_features = ["route_id", "office_from_id"]
        self.cat_indices = []

        self.cb_iterations = self.config.get("cb_iterations", 300)
        self.lgbm_estimators = self.config.get("lgbm_estimators", 300)

        self.best_k = np.ones(self.horizon, dtype=np.float32)

        self.metric: WapePlusRbias = WapePlusRbias()

        self._prepare_data()
        self._build_targets()

        self.catboost_task_type = self.config.get("catboost_task_type", "GPU")
        self.catboost_devices = self.config.get("catboost_devices", "0")

    def evaluate(self) -> dict:
        """
        Run time-series cross-validation, compute raw scores, and optimize
        the calibration vector k.

        Returns
        -------
        dict
            A dictionary containing:
            - oof_score (float): Raw WAPE + Rbias on OOF predictions.
            - oof_score_calibrated (float): Calibrated WAPE + Rbias.
            - best_k (np.ndarray): Optimized multipliers of shape (10,).
        """
        print(f"Starting evaluation in '{self.mode}' mode...")

        X = self._get_feature_matrix()
        y = self.df.select(self.target_cols).to_numpy()

        min_required = self.test_size * self.n_splits
        assert len(X) > min_required, (
            f"Dataset size {len(X)} too small for {self.n_splits} splits of size {self.test_size}"
        )

        tscv = TimeSeriesSplit(
            n_splits=self.n_splits,
            test_size=self.test_size,
            max_train_size=self.max_train_size,
        )

        oof_true = []
        oof_pred = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X), start=1):
            logger.info("Fold %d/%d: fit start", fold_idx, self.n_splits)

            X_train, y_train = X.iloc[train_idx], y[train_idx]
            X_val, y_val = X.iloc[val_idx], y[val_idx]

            models = self._fit_fold(X_train, y_train)

            logger.info("Fold %d/%d: predict start", fold_idx, self.n_splits)
            y_fold_pred = self._predict_ensemble(models, X_val)

            logger.info("Fold %d/%d: done", fold_idx, self.n_splits)

            oof_true.append(y_val)
            oof_pred.append(y_fold_pred)

            del models, X_train, y_train, X_val, y_val
            gc.collect()

        oof_true = np.vstack(oof_true)
        oof_pred = np.vstack(oof_pred)

        raw_score = self.metric.calculate(oof_true, oof_pred)

        self.best_k = self._optimize_k(oof_true, oof_pred)

        oof_pred_calibrated = oof_pred * self.best_k
        calibrated_score = self.metric.calculate(oof_true, oof_pred_calibrated)

        abs_errors = np.abs(oof_true - oof_pred_calibrated)
        p90_errors = np.percentile(abs_errors, 90, axis=0)
        
        os.makedirs(self.model_dir, exist_ok=True)
        uncertainty_profile = {
            f"p90_abs_error_step_{i+1}": float(err)
            for i, err in enumerate(p90_errors)
        }
        
        with open(os.path.join(self.model_dir, "micro_uncertainty_profile.json"), "w") as f:
            json.dump(uncertainty_profile, f, indent=2)

        return {"oof_score": float(raw_score), "oof_score_calibrated": float(calibrated_score), "best_k": self.best_k}

    def train_full_save(self, best_k: np.ndarray) -> None:
        """
        Train the model on the full dataset and save artifacts to disk.

        Parameters
        ----------
        best_k : np.ndarray
            The optimal multiplier vector of shape (10,) obtained from evaluate().
        """
        logger.info("Final training on %d rows", len(self.df))
        X = self._get_feature_matrix()
        y = self.df.select(self.target_cols).to_numpy()

        models = self._fit_fold(X, y)

        os.makedirs(self.model_dir, exist_ok=True)

        if self.mode == "chain":
            chain_cat, chain_lgbm = models
            joblib.dump(chain_cat, os.path.join(self.model_dir, "micro_chain_catboost.cbm"))
            joblib.dump(chain_lgbm, os.path.join(self.model_dir, "micro_chain_lightgbm.txt"))
        else:
            cat_multi = models[0]
            joblib.dump(cat_multi, os.path.join(self.model_dir, "micro_multi_catboost.cbm"))

        k_dict = {f"k_{i}": float(val) for i, val in enumerate(best_k)}
        with open(os.path.join(self.model_dir, "best_k_multiplier.json"), "w") as f:
            json.dump(k_dict, f, indent=2)
        with open(os.path.join(self.model_dir, "micro_feature_schema.json"), "w") as f:
            json.dump(self.feature_cols, f, indent=2)

    def _prepare_data(self) -> None:
        """
        Convert data types for memory optimization and strictly cast categoricals.
        """

        self.df = self.df.with_columns([pl.col(pl.Float64).cast(pl.Float32), pl.col(pl.Int64).cast(pl.Int32)])

        for col in self.cat_features:
            if col in self.df.columns:
                self.df = self.df.with_columns(pl.col(col).cast(pl.String).cast(pl.Categorical))

        self.df = self.df.sort(["timestamp", "route_id"])

        if self.tail_rows is not None and len(self.df) > self.tail_rows:
            self.df = self.df.tail(self.tail_rows)

        gc.collect()

    def _build_targets(self) -> None:
        """
        Generate 10-step horizon targets, drop timestamp, and isolate valid feature columns.
        """
        self.target_cols = []
        shifts = []

        for i in range(1, self.horizon + 1):
            col_name = f"target_step_{i}" if i > 1 else "target_2h_t1"
            shifts.append(pl.col(self.target_col).shift(-i).over("route_id").alias(col_name))
            self.target_cols.append(col_name)

        self.df = self.df.with_columns(shifts).drop_nulls(subset=self.target_cols)

        if "timestamp" in self.df.columns:
            self.df = self.df.drop("timestamp")

        excluded_cols = {self.target_col} | set(self.target_cols)
        self.feature_cols = [c for c in self.df.columns if c not in excluded_cols]

        self.cat_indices = [i for i, col in enumerate(self.feature_cols) if col in self.cat_features]

        print(f"Target construction complete. Feature count: {len(self.feature_cols)}")

    def _fit_fold(self, X: pd.DataFrame, y: np.ndarray) -> tuple:
        """
        Train models using fit_params to avoid Scikit-Learn cloning errors.
        """

        if self.cat_indices:
            fit_params_cb = {"cat_features": self.cat_indices}
            fit_params_lgbm = {"categorical_feature": self.cat_indices}
        else:
            fit_params_cb = {}
            fit_params_lgbm = {}

        if self.mode == "catboost_multi":
            model = CatBoostRegressor(
                loss_function="MultiRMSE",
                random_seed=self.seed,
                iterations=self.cb_iterations,
                verbose=False,
                allow_writing_files=False,
                task_type=self.catboost_task_type,
                devices=self.catboost_devices,
            )
            model.fit(X, y, **fit_params_cb)
            return (model,)

        elif self.mode == "chain":
            base_cat = CatBoostRegressor(
                loss_function="MAE",
                eval_metric="RMSE",
                random_seed=self.seed,
                iterations=self.cb_iterations,
                verbose=False,
                allow_writing_files=False,
                task_type=self.catboost_task_type,
                devices=self.catboost_devices,
            )

            chain_cat = RegressorChain(estimator=base_cat, random_state=self.seed)
            chain_cat.fit(X, y, **fit_params_cb)

            base_lgbm = LGBMRegressor(
                objective="mae",
                random_state=self.seed,
                n_estimators=self.lgbm_estimators,
                verbose=-1,
            )
            chain_lgbm = RegressorChain(estimator=base_lgbm, random_state=self.seed)
            chain_lgbm.fit(X, y, **fit_params_lgbm)

            return (chain_cat, chain_lgbm)

        else:
            raise ValueError(f"Mode {self.mode} doesn't exist only catboost_multi or chain are supported")

    def _get_feature_matrix(self) -> pd.DataFrame:
        """
        Extract features safely preserving categorical dtypes through Pandas.
        """
        df_pd = self.df.select(self.feature_cols).to_pandas()

        for col in self.cat_features:
            if col in df_pd.columns:
                df_pd[col] = df_pd[col].astype("category")

        return df_pd

    def _predict_ensemble(self, models: tuple, X: np.ndarray) -> np.ndarray:
        """
        Generate predictions using the trained ensemble.
        """
        if self.mode == "catboost_multi":
            return models[0].predict(X)

        elif self.mode == "chain":
            pred_cat = models[0].predict(X)
            pred_lgbm = models[1].predict(X)
            return (pred_cat + pred_lgbm) / 2.0

        else:
            raise ValueError(f"Mode {self.mode} doesn't exist only catboost_multi or chain are supported")

    def _optimize_k(self, y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
        """
        Find the optimal calibration vector 'k' using Nelder-Mead.
        """

        def objective(k):
            calibrated = y_pred * k
            return self.metric.calculate(y_true, calibrated)

        initial_k = np.ones(self.horizon, dtype=np.float32)
        res = minimize(objective, initial_k, method="Nelder-Mead")
        return res.x

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    data_path = "data/train_team_track.parquet"
    logger.info("Loading dataset from %s", data_path)

    df = pl.read_parquet(data_path)
    logger.info("Loaded %d rows", len(df))

    df = add_product_mvp_features(df)
    logger.info("Added MVP product features for micro ML")

    trainer = ChainRegressorEnsemble(
        df=df,
        config={
            "seed": 42,
            "mode": "chain",
            "test_size": 10000,
            "n_splits": 2,
            "max_train_size": 200000,
            "tail_rows": 260000,
            "cb_iterations": 300,
            "lgbm_estimators": 300,
            "catboost_task_type": "GPU",
            "catboost_devices": "0",
        },
    )

    logger.info("Starting evaluation")
    result = trainer.evaluate()
    logger.info(
        "Evaluation complete | oof_score=%.6f | calibrated=%.6f",
        result["oof_score"],
        result["oof_score_calibrated"],
    )

    logger.info("Training final models and saving artifacts")
    trainer.train_full_save(result["best_k"])
    logger.info("Artifacts saved to ./models")


if __name__ == "__main__":
    main()