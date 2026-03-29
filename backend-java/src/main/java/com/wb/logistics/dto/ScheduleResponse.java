package com.wb.logistics.dto;

import java.time.Instant;
import java.util.List;

/**
 * Ответ GET /schedule — всё, что нужно фронтенду:
 * текущее расписание рейсов + тактический план на неделю.
 */
public record ScheduleResponse(
        List<DispatchDto> dispatches,
        List<TacticalPlanDto> tacticalPlan,
        Instant generatedAt
) {
}