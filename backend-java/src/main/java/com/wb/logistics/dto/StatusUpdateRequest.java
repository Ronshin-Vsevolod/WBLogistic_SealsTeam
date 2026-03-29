package com.wb.logistics.dto;

import jakarta.validation.constraints.NotNull;
import com.wb.logistics.entity.DispatchStatus;

/**
 * Запрос на смену статуса рейса.
 */
public record StatusUpdateRequest(
        @NotNull DispatchStatus newStatus
) {
}