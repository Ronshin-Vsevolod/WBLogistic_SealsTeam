package com.wb.logistics.service;

import com.wb.logistics.dto.TacticalPlanDto;
import com.wb.logistics.repository.TacticalPlanRepository;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Чтение тактического плана.
 * Обновление происходит только через IngestService (при получении нового прогноза).
 */
@Service
public class TacticalPlanService {

    private final TacticalPlanRepository repo;

    public TacticalPlanService(TacticalPlanRepository repo) {
        this.repo = repo;
    }

    public List<TacticalPlanDto> getByWarehouse(String warehouseId) {
        return repo.findByWarehouseIdOrderByPlanDateAsc(warehouseId)
                .stream()
                .map(e -> new TacticalPlanDto(
                        e.getWarehouseId(),
                        e.getPlanDate(),
                        e.getForecastVolume(),
                        e.getRequiredTrucks()
                ))
                .toList();
    }
}