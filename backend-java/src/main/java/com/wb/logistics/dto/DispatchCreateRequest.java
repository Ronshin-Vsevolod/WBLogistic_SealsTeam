package com.wb.logistics.dto;

import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Ручное создание рейса диспетчером через POST /dispatch.
 */
public record DispatchCreateRequest(

        @NotBlank
        String warehouseId,

        Integer routeId,

        @NotNull
        Instant scheduledAt,

        @NotBlank
        String vehicleType,

        @NotNull @DecimalMin("0")
        BigDecimal expectedVolume,

        @NotNull @DecimalMin("0.01")
        BigDecimal vehicleCapacity,

        @Min(1) @Max(5)
        int priority
) {
}