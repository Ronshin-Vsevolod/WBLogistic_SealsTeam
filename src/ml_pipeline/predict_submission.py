"""
Little script example
test_df = pl.read_parquet("data/test_team_track.parquet")
preds_cat = model_cat.predict(test_df)
preds_lgbm = model_lgbm.predict(test_df)
final = create_submission_polars(test_df, preds_cat, preds_lgbm, best_k, "submission.csv")
"""

import json

import joblib
import numpy as np
import polars as pl

MODEL_DIR = "models"
CAT_PATH = f"{MODEL_DIR}/micro_chain_catboost.cbm"
LGBM_PATH = f"{MODEL_DIR}/micro_chain_lightgbm.txt"
K_PATH = f"{MODEL_DIR}/best_k_multiplier.json"

model_cat = joblib.load(CAT_PATH)
model_lgbm = joblib.load(LGBM_PATH)

with open(K_PATH) as f:
    k_dict = json.load(f)

    best_k = np.array([k_dict[f"k_{i}"] for i in range(10)], dtype=np.float32)


def create_submission_polars(test_df, preds_cat, preds_lgbm, best_k, submission_path):
    """
    Forms final submission: ensemble, calibrate and expands the data.
    """

    final_preds = ((preds_cat + preds_lgbm) / 2.0) * best_k

    target_cols = [f"target_step_{i}" for i in range(1, 11)]

    wide_preds = pl.DataFrame(final_preds, schema=target_cols).with_columns(
        [pl.Series("route_id", test_df["route_id"]), pl.Series("inference_ts", test_df["timestamp"])]
    )

    long_preds = wide_preds.unpivot(
        index=["route_id", "inference_ts"], on=target_cols, variable_name="step", value_name="y_pred"
    )

    long_preds = long_preds.with_columns(
        [pl.col("step").str.extract(r"(\d+)").cast(pl.Int32).alias("step_num")]
    ).with_columns([(pl.col("inference_ts") + pl.col("step_num") * 30 * 60 * 1000).alias("timestamp")])

    final_submission = (
        test_df.select(["id", "route_id", "timestamp"])
        .join(long_preds.select(["route_id", "timestamp", "y_pred"]), on=["route_id", "timestamp"], how="left")
        .with_columns(pl.col("y_pred").fill_null(0))
        .select(["id", "y_pred"])
    )

    assert final_submission["id"].null_count() == 0, "ERROR: ID lost!"

    final_submission.write_csv(submission_path)
    print(f"Submission saved to: {submission_path}")

    return final_submission