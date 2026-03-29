package com.wb.logistics.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * Рейс для API-ответов.
 * Не содержит внутренних JPA-деталей — только то, что видит фронтенд.
 */
public record DispatchDto(
        UUID id,
        String warehouseId,
        Integer routeId,
        Instant scheduledAt,
        String vehicleType,
        BigDecimal expectedVolume,
        BigDecimal vehicleCapacity,
        BigDecimal fillRate,
        String triggerReason,
        String status,
        int priority,
        Instant createdAt
) {
}