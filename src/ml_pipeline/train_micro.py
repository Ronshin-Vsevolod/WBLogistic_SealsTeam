import gc
import json
import os

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

        self.target_col = "target_2h"
        self.horizon = 10
        self.model_dir = "models"

        self.target_cols = []
        self.feature_cols = []
        self.cat_features = ["route_id", "office_from_id"]
        self.cat_indices = []

        self.best_k = np.ones(self.horizon, dtype=np.float32)

        self.metric: WapePlusRbias = WapePlusRbias()

        self._prepare_data()
        self._build_targets()

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

        tscv = TimeSeriesSplit(n_splits=self.n_splits, test_size=self.test_size)

        oof_true = []
        oof_pred = []

        for train_idx, val_idx in tscv.split(X):
            X_train, y_train = X.iloc[train_idx], y[train_idx]
            X_val, y_val = X.iloc[val_idx], y[val_idx]

            models = self._fit_fold(X_train, y_train)
            y_fold_pred = self._predict_ensemble(models, X_val)

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

        return {"oof_score": float(raw_score), "oof_score_calibrated": float(calibrated_score), "best_k": self.best_k}

    def train_full_save(self, best_k: np.ndarray) -> None:
        """
        Train the model on the full dataset and save artifacts to disk.

        Parameters
        ----------
        best_k : np.ndarray
            The optimal multiplier vector of shape (10,) obtained from evaluate().
        """
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

    def _prepare_data(self) -> None:
        """
        Convert data types for memory optimization and strictly cast categoricals.
        """

        self.df = self.df.with_columns([pl.col(pl.Float64).cast(pl.Float32), pl.col(pl.Int64).cast(pl.Int32)])

        for col in self.cat_features:
            if col in self.df.columns:
                self.df = self.df.with_columns(pl.col(col).cast(pl.String).cast(pl.Categorical))

        self.df = self.df.sort(["timestamp", "route_id"])
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
                loss_function="MultiRMSE", random_seed=self.seed, verbose=False, allow_writing_files=False
            )
            model.fit(X, y, **fit_params_cb)
            return (model,)

        elif self.mode == "chain":
            base_cat = CatBoostRegressor(
                loss_function="MAE", random_seed=self.seed, verbose=False, allow_writing_files=False
            )

            chain_cat = RegressorChain(base_estimator=base_cat, random_state=self.seed)
            chain_cat.fit(X, y, **fit_params_cb)

            base_lgbm = LGBMRegressor(objective="mae", random_state=self.seed, verbose=-1)
            chain_lgbm = RegressorChain(base_estimator=base_lgbm, random_state=self.seed)
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
