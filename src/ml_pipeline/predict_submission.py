import joblib
import json
import numpy as np
import polars as pl

# Пути к файлам из вашего ТЗ
MODEL_DIR = "models"
CAT_PATH = f"{MODEL_DIR}/micro_chain_catboost.cbm"
LGBM_PATH = f"{MODEL_DIR}/micro_chain_lightgbm.txt"
K_PATH = f"{MODEL_DIR}/best_k_multiplier.json"

# Загружаем модели
model_cat = joblib.load(CAT_PATH)
model_lgbm = joblib.load(LGBM_PATH)

# Загружаем коэффициенты k и переводим в numpy array
with open(K_PATH, "r") as f:
    k_dict = json.load(f)
    # Гарантируем правильный порядок от 0 до 9
    best_k = np.array([k_dict[f"k_{i}"] for i in range(10)], dtype=np.float32)

def create_submission_polars(test_df, preds_cat, preds_lgbm, best_k, submission_path):
    """
    Формирует финальный сабмишен: ансамблирует, калибрует и разворачивает данные через Polars.
    """
    # 1. Ансамблирование и калибровка k-множителями
    # Усредняем прогнозы и применяем вектор весов (best_k)
    final_preds = ((preds_cat + preds_lgbm) / 2.0) * best_k 
    
    # 2. Подготовка названий колонок шагов
    target_cols = [f"target_step_{i}" for i in range(1, 11)]
    
    # 3. Создаем DataFrame с прогнозами и ключами для разворота
    wide_preds = pl.DataFrame(final_preds, schema=target_cols).with_columns([
        pl.Series("route_id", test_df["route_id"]),
        pl.Series("inference_ts", test_df["timestamp"])
    ])
    
    # 4. Разворачиваем в длинный формат (unpivot)
    long_preds = wide_preds.unpivot(
        index=["route_id", "inference_ts"],
        on=target_cols,
        variable_name="step",
        value_name="y_pred"
    )
    
    # 5. Расчет целевого timestamp (+30 минут за каждый шаг)
    long_preds = long_preds.with_columns([
        pl.col("step").str.extract(r"(\d+)").cast(pl.Int32).alias("step_num")
    ]).with_columns([
        # В Polars время удобно считать через миллисекунды: 30 мин * 60 сек * 1000 мс
        (pl.col("inference_ts") + pl.col("step_num") * 30 * 60 * 1000).alias("timestamp")
    ])
    
    # 6. Финальный Merge с оригинальным тестом
    final_submission = (
        test_df.select(["id", "route_id", "timestamp"])
        .join(
            long_preds.select(["route_id", "timestamp", "y_pred"]),
            on=["route_id", "timestamp"],
            how="left"
        )
        .with_columns(pl.col("y_pred").fill_null(0)) # Защита от пропусков
        .select(["id", "y_pred"])
    )
    
    # Проверка на целостность
    assert final_submission["id"].null_count() == 0, "Критическая ошибка: потеряны ID!"

    # 7. Сохранение
    final_submission.write_csv(submission_path)
    print(f"Submission saved to: {submission_path}")
    
    return final_submission