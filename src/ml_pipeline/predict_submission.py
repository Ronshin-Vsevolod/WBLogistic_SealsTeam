import polars as pl
import joblib
import numpy as np
import json

# 1. Загружаем артефакты (с именами по ТЗ!)
print("Loading models and coefficients...")
model_cat = joblib.load("models/micro_chain_catboost.cbm")
model_lgbm = joblib.load("models/micro_chain_lightgbm.txt")

with open("models/best_k_multiplier.json", "r") as f:
    best_k_dict = json.load(f)
best_k = np.array([best_k_dict[f"k_{i}"] for i in range(10)])

# 2. Загружаем данные
print("Loading test and train data...")
test_df = pl.read_parquet("data/test_team_track.parquet")
train_df = pl.read_parquet("data/train_team_track.parquet")

# 3. Достаем последние статусы маршрутов из трейна
print("Extracting last known states for features...")
last_known_states = (
    train_df
    .sort("timestamp")
    .group_by("route_id")
    .last()
    .select(pl.all().exclude(['timestamp', 'target_2h']))
)

# Склеиваем тест с фичами
test_with_features = (
    test_df
    .select(["id", "route_id", "timestamp"])
    .join(last_known_states, on="route_id", how="left")
    .with_columns(pl.col('route_id').cast(pl.Categorical))
)

# Оставляем только фичи для модели (исключая id и timestamp)
# Теперь тут гарантированно будет route_id + status_1...8
X_inference = test_with_features.select(pl.all().exclude(["id", "timestamp"])).to_pandas()

# 4. Предсказания
print("Making predictions...")
preds_cat = model_cat.predict(X_inference)
preds_lgbm = model_lgbm.predict(X_inference)

# 5. Ансамбль и калибровка
print("Ensembling and applying k-multipliers...")
final_preds = ((preds_cat + preds_lgbm) / 2.0) * best_k

# 6. Перевод бейзлайна на Polars
print("Formatting to baseline standard via Polars...")
target_cols = [f"target_step_{i}" for i in range(1, 11)]
wide_preds = pl.DataFrame(final_preds, schema=target_cols)

# Добавляем ключи
wide_preds = wide_preds.with_columns([
    pl.Series("route_id", test_df["route_id"]),
    pl.Series("inference_ts", test_df["timestamp"])
])

# Разворачиваем в длинный формат
long_preds = wide_preds.unpivot(
    index=["route_id", "inference_ts"],
    on=target_cols,
    variable_name="step",
    value_name="y_pred"
)

# Считаем timestamp для каждого шага
long_preds = long_preds.with_columns([
    pl.col("step").str.extract(r"(\d+)").cast(pl.Int32).alias("step_num")
])
long_preds = long_preds.with_columns([
    (pl.col("inference_ts") + pl.col("step_num") * 30 * 60 * 1000).alias("timestamp")
])

# 7. Финальный Merge с оригинальным тестом
submission = test_df.select(["id", "route_id", "timestamp"]).join(
    long_preds.select(["route_id", "timestamp", "y_pred"]),
    on=["route_id", "timestamp"],
    how="left"
)

# Заполняем пропуски нулями, если вдруг для какого-то шага не нашлось прогноза
submission = submission.with_columns(pl.col("y_pred").fill_null(0))

# Оставляем только две колонки, которые требует бейзлайн!
final_submission = submission.select(["id", "y_pred"])

# 8. Сохранение
final_submission.write_csv("submission_team.csv")
print(f"Submission saved! Shape: {final_submission.shape}")