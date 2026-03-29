package com.wb.logistics.dto;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * Одна строка тактического плана для API-ответа.
 */
public record TacticalPlanDto(
        String warehouseId,
        LocalDate planDate,
        BigDecimal forecastVolume,
        int requiredTrucks
) {
}