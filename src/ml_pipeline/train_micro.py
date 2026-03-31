from metrics import WapePlusRbias
from sklearn.model_selection import TimeSeriesSplit
from sklearn.multioutput import RegressorChain
from scipy.optimize import minimize
import polars as pl
from catboost import CatBoostRegressor
from lightgbm import LGBMRegressor
import numpy as np
import json
import joblib
import os
import gc
import pathlib

class ChainRegressorEnsemble:

    def __init__(self, df: pl.DataFrame) -> None:

        self.cat_features = [df.get_column_index('route_id')]

        self.model_catboost = CatBoostRegressor(
            iterations=200,
            depth=4,
            learning_rate=1e-1,
            loss_function="RMSE", task_type="CPU",
            allow_writing_files=False, used_ram_limit='7gb',
            verbose=False, thread_count=-1  
        )
        self.model_lightgbm = LGBMRegressor(n_estimators=200,
            max_depth=4, learning_rate=1e-1, verbose=-1,
            objective="regression", n_jobs=-1, importance_type='gain'
        )
        self.df: pl.DataFrame = df.with_columns([
                pl.col(pl.Float64).cast(pl.Float32),
                pl.col(pl.Int64).cast(pl.Int32)
            ])

        self.X, self.y = self._split_feat_target()

    def _split_feat_target(self) -> tuple:
        df_sorted_by_timestamp_and_route_id = self.df.sort(
            by=["timestamp", "route_id"], descending=False
        )

        df_with_targets = df_sorted_by_timestamp_and_route_id.with_columns([pl.col("route_id").cast(pl.String).cast(pl.Categorical),
            *[
                pl.col("target_2h").shift(-i).over("route_id").alias(f"target_route_{i}")
                for i in range(1, 10)
            ]
            ]
        ).drop_nulls()

        X = df_with_targets.select(
            pl.all().exclude(
                ["timestamp", "target_2h"]
                + [f"target_route_{i}" for i in range(1, 10)]
            )
        )
        y = df_with_targets.select(
            pl.col(["target_2h"] + [f"target_route_{i}" for i in range(1, 10)])
        )

        return X.to_pandas(), y.to_pandas()

    def get_oof_predictions(self):
        tcv = TimeSeriesSplit(n_splits=2, test_size=10000, gap=0)
        all_y_true, all_y_pred = [], []

        for train_index, val_index in tcv.split(self.X, self.y):
            X_train, y_train = self.X.iloc[train_index], self.y.iloc[train_index]
            X_val, y_val = self.X.iloc[val_index], self.y.iloc[val_index]

            chain_cat = RegressorChain(
                base_estimator=self.model_catboost, random_state=42
            )
            chain_lgbm = RegressorChain(
                base_estimator=self.model_lightgbm, random_state=42
            )

            chain_cat.fit(X_train, y_train, 
                          cat_features=self.cat_features)
            chain_lgbm.fit(X_train, y_train)

            pred_cat = chain_cat.predict(X_val)
            pred_lgbm = chain_lgbm.predict(X_val)

            pred_ensemble = (pred_cat + pred_lgbm) / 2.0

            all_y_true.append(y_val.to_numpy())
            all_y_pred.append(pred_ensemble)
            
            del X_train, y_train
            gc.collect()

        return np.vstack(all_y_true), np.vstack(all_y_pred)

    def find_best_k(self, y_true, y_pred):
        print("Optimizing multipliers with scipy.optimize...")
        metric_calculator = WapePlusRbias()

        # Целевая функция для Nelder-Mead (ищем 10 коэффициентов)
        def objective(k_arr):
            # Умножаем каждый из 10 шагов на свой коэффициент k
            calibrated_pred = y_pred * k_arr
            return metric_calculator.calculate(y_true, calibrated_pred)

        initial_k = np.ones(10)  # Начинаем с единиц
        res = minimize(
            objective, initial_k, method="Nelder-Mead", options={"maxiter": 100}
        )
        print(f"Optimal k found: {res.x}")
        return res.x

    def train_final_and_save(self, best_k: np.ndarray):
        os.makedirs("models", exist_ok=True)

        chain_cat = RegressorChain(
            base_estimator=self.model_catboost, random_state=42
        )
        chain_lgbm = RegressorChain(
            base_estimator=self.model_lightgbm, random_state=42
        )

        print("Training final models on full dataset...")
        chain_cat.fit(self.X, self.y, cat_features=self.cat_features,)
        chain_lgbm.fit(self.X, self.y)

        # Внимание: переименовал по ТЗ!
        joblib.dump(chain_cat, "models/micro_chain_catboost.cbm")
        joblib.dump(chain_lgbm, "models/micro_chain_lightgbm.txt")

        k_dict = {f"k_{i}": float(best_k[i]) for i in range(10)}
        with open("models/best_k_multiplier.json", "w") as f:
            json.dump(k_dict, f, indent=4)

        print("All artifacts saved successfully!")


''' problem with bad allocation 
SCRIPT EXAMPLE

base_pth  = base_path = pathlib.Path(__file__).parent.parent.parent
file_path = base_path / "data" / "train_team_track.parquet"


time_series_df = pl.read_parquet(file_path)
ensemble = ChainRegressorEnsemble(time_series_df)
metric = WapePlusRbias()
# 1. Получаем OOF предсказания
y_true, y_pred = ensemble.get_oof_predictions()

oof = metric.calculate(y_true, y_pred)

print(f"WAPE + Rbias oof: {oof:.5f}\n")
# 2. Оптимизируем веса k
best_k = ensemble.find_best_k(y_true, y_pred)


calibrated_y_pred = y_pred * best_k
oof_score_after = metric.calculate(y_true, calibrated_y_pred)
print(f"After calibration: {oof_score_after:.5f}\n")
# 3. Сохраняем модели и коэффициенты
ensemble.train_final_and_save(best_k)
'''
