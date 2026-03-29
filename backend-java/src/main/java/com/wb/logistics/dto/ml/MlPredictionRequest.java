package com.wb.logistics.dto.ml;

import com.wb.logistics.dto.IntegrationData;

/**
 * Полный запрос к Python ML-сервису.
 * Содержит сырые данные со склада + интеграционные данные.
 *
 * Python внутри себя:
 *  1. Запускает Macro модель (promo + macroWeather) → macro_daily_baseline
 *  2. Передаёт baseline в Micro модель (+ microWeather + traffic)
 *  3. Decision Engine → dispatches
 *
 * Java НЕ знает про macro_daily_baseline —
 * это внутренний контракт между Python-моделями.
 */
public record MlPredictionRequest(
        int officeFromId,
        int routeId,
        long timestamp,
        int status1,
        int status2,
        int status3,
        int status4,
        int status5,
        int status6,
        int status7,
        int status8,
        IntegrationData integrations
) {
}