package com.wb.logistics.controller;

import com.wb.logistics.dto.ScheduleResponse;
import com.wb.logistics.service.DispatchService;
import com.wb.logistics.service.TacticalPlanService;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;

/**
 * GET /api/v1/schedule?warehouseId=4
 *
 * Возвращает текущее расписание рейсов + тактический план.
 * Это основной эндпоинт для дашборда фронтенда.
 */
@RestController
@RequestMapping("/api/v1")
public class ScheduleController {

    private final DispatchService dispatchService;
    private final TacticalPlanService planService;

    public ScheduleController(DispatchService dispatchService, TacticalPlanService planService) {
        this.dispatchService = dispatchService;
        this.planService = planService;
    }

    @GetMapping("/schedule")
    public ScheduleResponse getSchedule(@RequestParam String warehouseId) {
        return new ScheduleResponse(
                dispatchService.getByWarehouse(warehouseId),
                planService.getByWarehouse(warehouseId),
                Instant.now()
        );
    }
}