package com.wb.logistics.dto.ml;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

/**
 * Что Python ML-сервис возвращает.
 * Содержит два блока:
 *  1) dispatches — готовые заявки от Decision Engine (micro-уровень)
 *  2) tacticalPlan — прогноз на 7 дней (macro-уровень)
 */
public record MlPredictionResponse(
        List<MlDispatch> dispatches,
        List<MlPlanEntry> tacticalPlan
) {

    /** Одна заявка, сгенерированная Python Decision Engine. */
    public record MlDispatch(
            String warehouseId,
            Integer routeId,
            Instant scheduledAt,
            String vehicleType,
            BigDecimal expectedVolume,
            BigDecimal vehicleCapacity,
            BigDecimal fillRate,
            String triggerReason,
            int priority
    ) {}

    /** Одна строка макро-прогноза. */
    public record MlPlanEntry(
            String warehouseId,
            LocalDate planDate,
            BigDecimal forecastVolume,
            int requiredTrucks
    ) {}
}