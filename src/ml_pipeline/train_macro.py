"""
Macro ML Pipeline — Prophet-based 7-day daily forecast.

Target definition:
    daily_volume = sum(target_2h) per (date, office_from_id)
    → агрегируем все route_id внутри одного офиса в дневной объём.

Granularity: per-office models (dict {office_from_id: Prophet}).

External regressors (synthetic, deterministic):
    macro_weather  ∈ [0, 10]  — имитирует сезонность погоды
    promo          ∈ [0, 10]  — имитирует промо-активность

Validation: time-based holdout (последние 14 дней, или 7 если данных мало).
Metric: WAPE = sum(|y - ŷ|) / sum(|y|) × 100 [%]

Artifacts saved to models/:
    macro_daily_prophet.pkl     — {office_id: Prophet} + meta
    macro_feature_schema.json   — список регрессоров
    macro_train_meta.json       — метаданные обучения
"""

from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import polars as pl
from prophet import Prophet

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

DATA_PATH   = Path("data/train_team_track.parquet")
MODELS_DIR  = Path("models")

HOLDOUT_DAYS       = 14   # дней на валидацию; если данных < 30 → 7
MIN_DAYS_THRESHOLD = 30   # порог для переключения holdout
FORECAST_HORIZON   = 7    # дней прогноза (для мета)

REGRESSORS: list[str] = ["macro_weather", "promo"]

SYNTHETIC_SEED = 42       # детерминированный seed для регрессоров

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# 1. Загрузка и агрегация данных
# ---------------------------------------------------------------------------

def _parse_timestamp_column(df: pl.DataFrame) -> pl.DataFrame:
    """
    Определяет тип / единицу колонки timestamp и добавляет колонку ds (Date).

    Поддерживаемые форматы:
        Datetime / Date  → конвертируем напрямую
        Int/Float        → определяем единицу по порядку значения:
                           < 1e10  → секунды
                           < 1e13  → миллисекунды
                           < 1e16  → микросекунды
                           иначе   → наносекунды
    """
    ts_dtype = df["timestamp"].dtype
    log.info("Тип колонки timestamp: %s", ts_dtype)

    dtype_str = str(ts_dtype)

    # ── уже Datetime ──────────────────────────────────────────────────────
    if dtype_str.startswith("Datetime") or ts_dtype == pl.Date:
        return df.with_columns(
            pl.col("timestamp")
            .cast(pl.Datetime("us"))
            .dt.replace_time_zone("UTC")
            .dt.date()
            .alias("ds")
        )

    # ── числовой ──────────────────────────────────────────────────────────
    numeric_types = (
        pl.Int8, pl.Int16, pl.Int32, pl.Int64,
        pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
        pl.Float32, pl.Float64,
    )
    if ts_dtype not in numeric_types:
        raise TypeError(
            f"Неожиданный тип колонки timestamp: {ts_dtype}. "
            "Ожидается числовой (Int/Float) или Datetime."
        )

    sample_val = float(df["timestamp"].drop_nulls()[0])
    abs_val = abs(sample_val)
    log.info("Пример значения timestamp: %.0f  (abs=%.3e)", sample_val, abs_val)

    if abs_val < 1e10:
        # секунды → мкс
        log.info("Единица: epoch seconds → умножаем на 1_000_000")
        expr = (pl.col("timestamp").cast(pl.Int64) * 1_000_000).cast(
            pl.Datetime("us", "UTC")
        )
    elif abs_val < 1e13:
        # миллисекунды → мкс
        log.info("Единица: epoch milliseconds → умножаем на 1_000")
        expr = (pl.col("timestamp").cast(pl.Int64) * 1_000).cast(
            pl.Datetime("us", "UTC")
        )
    elif abs_val < 1e16:
        # микросекунды
        log.info("Единица: epoch microseconds → cast напрямую")
        expr = pl.col("timestamp").cast(pl.Datetime("us", "UTC"))
    else:
        # наносекунды → через ns Datetime
        log.info("Единица: epoch nanoseconds → cast через Datetime ns")
        expr = (
            pl.col("timestamp")
            .cast(pl.Datetime("ns", "UTC"))
            .cast(pl.Datetime("us", "UTC"))
        )

    return df.with_columns(expr.dt.date().alias("ds"))


def load_and_aggregate(path: Path) -> pl.DataFrame:
    """
    Загружает parquet, приводит timestamp к UTC-дате,
    агрегирует daily_volume = sum(target_2h) по (date, office_from_id).

    Возвращает DataFrame с колонками:
        ds              — pl.Date
        office_from_id  — идентификатор склада
        y               — daily_volume (sum of target_2h)
    """
    log.info("Загрузка данных из %s", path)
    df = pl.read_parquet(path)
    log.info(
        "Исходный датасет: %d строк, колонки: %s", len(df), df.columns
    )

    df = _parse_timestamp_column(df)

    # Агрегируем все route_id → дневной объём на уровне склада
    daily = (
        df.group_by(["ds", "office_from_id"])
        .agg(pl.col("target_2h").sum().alias("y"))
        .sort(["office_from_id", "ds"])
    )

    log.info(
        "После агрегации: %d строк, офисов: %d, диапазон дат: %s → %s",
        len(daily),
        daily["office_from_id"].n_unique(),
        daily["ds"].min(),
        daily["ds"].max(),
    )
    return daily


# ---------------------------------------------------------------------------
# 2. Синтетические регрессоры (детерминированные)
# ---------------------------------------------------------------------------

def build_synthetic_regressors(dates: list) -> pl.DataFrame:
    """
    Генерирует синтетические регрессоры для заданного списка дат.

    Логика (одинаковая для всех офисов, seed=SYNTHETIC_SEED):
        macro_weather: годовой синусоидальный цикл + шум  → [0, 10]
        promo:         14-дневный цикл + шум              → [0, 10]

    Детерминированность: фиксированный seed + функция от t=np.arange(n).
    """
    rng = np.random.default_rng(SYNTHETIC_SEED)
    n = len(dates)
    t = np.arange(n, dtype=np.float64)

    # macro_weather: годовая сезонность
    weather_base  = np.sin(2 * np.pi * t / 365.25) * 3 + 5   # [2, 8]
    weather_noise = rng.normal(0, 0.5, n)
    macro_weather = np.clip(weather_base + weather_noise, 0, 10)

    # promo: 14-дневный цикл (промо-периоды)
    promo_base  = np.sin(2 * np.pi * t / 14) * 2.5 + 5        # [2.5, 7.5]
    promo_noise = rng.normal(0, 0.7, n)
    promo       = np.clip(promo_base + promo_noise, 0, 10)

    return pl.DataFrame({
        "ds":            dates,
        "macro_weather": macro_weather,
        "promo":         promo,
    })


# ---------------------------------------------------------------------------
# 3. Метрика
# ---------------------------------------------------------------------------

def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    WAPE = sum(|y - ŷ|) / sum(|y|) × 100  [%]
    Устойчива к нулям: если sum(|y|) == 0 → nan.
    """
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)


# ---------------------------------------------------------------------------
# 4. Обучение per-office модели Prophet
# ---------------------------------------------------------------------------

def train_office_model(
    df_office: pl.DataFrame,
    office_id: Any,
    regressors_df: pl.DataFrame,
) -> tuple[Prophet | None, dict]:
    """
    Обучает Prophet для одного office_from_id.

    Возвращает (fitted_model | None, metrics_dict).
    """
    # Merge с регрессорами по ds
    df_office = df_office.join(regressors_df, on="ds", how="left")

    # Pandas для Prophet
    df_pd = df_office.to_pandas()

    # ds: pl.Date → python date → pandas Timestamp (без timezone — Prophet требует)
    df_pd["ds"] = df_pd["ds"].apply(
        lambda d: datetime(d.year, d.month, d.day) if hasattr(d, "year") else d
    )

    n_total = len(df_pd)

    # Определяем размер holdout
    holdout = HOLDOUT_DAYS if n_total >= MIN_DAYS_THRESHOLD else 7

    if n_total < holdout + 3:
        log.warning(
            "Офис %s: слишком мало дат (%d), пропускаем.", office_id, n_total
        )
        return None, {
            "office_from_id": str(office_id),
            "train_rows": 0,
            "val_rows": 0,
            "wape_pct": float("nan"),
        }

    # Time-based split
    df_train = df_pd.iloc[:-holdout].copy()
    df_val   = df_pd.iloc[-holdout:].copy()

    cols = ["ds", "y"] + REGRESSORS

    # -----------------------------------------------------------------------
    # Prophet конфигурация
    # -----------------------------------------------------------------------
    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False,
    )
    for reg in REGRESSORS:
        model.add_regressor(reg)

    model.fit(df_train[cols])

    # Predict на val
    future_val    = df_val[["ds"] + REGRESSORS].copy()
    forecast_val  = model.predict(future_val)

    y_true = df_val["y"].values
    y_pred = np.clip(forecast_val["yhat"].values, 0, None)   # объём ≥ 0

    metric = wape(y_true, y_pred)

    return model, {
        "office_from_id": str(office_id),
        "train_rows": int(len(df_train)),
        "val_rows":   int(len(df_val)),
        "wape_pct":   round(metric, 4) if not np.isnan(metric) else None,
    }


# ---------------------------------------------------------------------------
# 5. Главная функция
# ---------------------------------------------------------------------------

def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 5.1 Загрузка данных
    # ------------------------------------------------------------------
    daily = load_and_aggregate(DATA_PATH)

    # Глобальный диапазон дат → регрессоры (одинаковые для всех офисов)
    all_dates_pl = (
        daily.select("ds")
        .unique()
        .sort("ds")["ds"]
        .to_list()
    )
    regressors_df = build_synthetic_regressors(all_dates_pl)

    log.info(
        "Диапазон дат: %s → %s (%d уникальных дней)",
        all_dates_pl[0], all_dates_pl[-1], len(all_dates_pl),
    )

    # ------------------------------------------------------------------
    # 5.2 Per-office обучение
    # ------------------------------------------------------------------
    offices = sorted(daily["office_from_id"].unique().to_list())
    log.info("Офисов для обучения: %d", len(offices))

    models_dict: dict[Any, Prophet] = {}
    metrics_list: list[dict]         = []

    for i, office_id in enumerate(offices, 1):
        log.info("[%d/%d] Обучаем офис: %s", i, len(offices), office_id)

        df_office = daily.filter(
            pl.col("office_from_id") == office_id
        ).sort("ds")

        model, metrics = train_office_model(
            df_office, office_id, regressors_df
        )

        metrics_list.append(metrics)

        if model is not None:
            models_dict[office_id] = model
            wape_str = (
                f"{metrics['wape_pct']:.2f}%"
                if metrics["wape_pct"] is not None
                else "N/A"
            )
            log.info(
                "  → train=%d  val=%d  WAPE=%s",
                metrics["train_rows"],
                metrics["val_rows"],
                wape_str,
            )

    # ------------------------------------------------------------------
    # 5.3 Итоговая печать
    # ------------------------------------------------------------------
    valid_wapes = [
        m["wape_pct"]
        for m in metrics_list
        if m["wape_pct"] is not None
    ]
    avg_wape = float(np.mean(valid_wapes)) if valid_wapes else float("nan")

    print("\n" + "=" * 62)
    print("  MACRO PROPHET — РЕЗУЛЬТАТЫ ОБУЧЕНИЯ")
    print("=" * 62)
    print(f"  Офисов обучено:     {len(models_dict)}")
    print(f"  Офисов пропущено:   {len(offices) - len(models_dict)}")
    print(f"  Регрессоры:         {REGRESSORS}")
    print("-" * 62)
    print(f"  {'Офис':<28} {'Train':>6} {'Val':>6} {'WAPE %':>8}")
    print("-" * 62)
    for m in metrics_list:
        wape_s = f"{m['wape_pct']:8.2f}" if m["wape_pct"] is not None else "     N/A"
        print(
            f"  {str(m['office_from_id']):<28} "
            f"{m['train_rows']:>6} "
            f"{m['val_rows']:>6} "
            f"{wape_s}"
        )
    print("-" * 62)
    avg_s = f"{avg_wape:.2f}%" if not np.isnan(avg_wape) else "N/A"
    print(f"  Средний WAPE:       {avg_s}")
    print("=" * 62 + "\n")

    # ------------------------------------------------------------------
    # 5.4 Сохранение артефактов
    # ------------------------------------------------------------------

    # macro_daily_prophet.pkl
    artifact = {
        "models":     models_dict,
        "regressors": REGRESSORS,
    }
    pkl_path = MODELS_DIR / "macro_daily_prophet.pkl"
    joblib.dump(artifact, pkl_path)
    log.info("Сохранён: %s", pkl_path)

    # macro_feature_schema.json
    schema_path = MODELS_DIR / "macro_feature_schema.json"
    schema_path.write_text(
        json.dumps(REGRESSORS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Сохранён: %s", schema_path)

    # macro_train_meta.json
    meta = {
        "trained_at_utc":        datetime.now(tz=timezone.utc).isoformat(),
        "forecast_horizon_days": FORECAST_HORIZON,
        "regressors":            REGRESSORS,
        "offices_total":         len(offices),
        "offices_trained":       len(models_dict),
        "data_period": {
            "min_date":    str(all_dates_pl[0]),
            "max_date":    str(all_dates_pl[-1]),
            "total_days":  len(all_dates_pl),
        },
        "holdout_days":        HOLDOUT_DAYS,
        "per_office_metrics":  metrics_list,
        "average_wape_pct":    round(avg_wape, 4) if not np.isnan(avg_wape) else None,
    }
    meta_path = MODELS_DIR / "macro_train_meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Сохранён: %s", meta_path)
    log.info("Готово. Артефакты в %s/", MODELS_DIR)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()