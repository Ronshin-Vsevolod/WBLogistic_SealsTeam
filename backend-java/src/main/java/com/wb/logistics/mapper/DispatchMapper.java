package com.wb.logistics.mapper;

import com.wb.logistics.dto.DispatchDto;
import com.wb.logistics.dto.ml.MlPredictionResponse.MlDispatch;
import com.wb.logistics.entity.Dispatch;

/** Ручной маппер Entity <-> DTO. */
public final class DispatchMapper {

    private DispatchMapper() {}

    /** Entity → DTO (для API-ответов). */
    public static DispatchDto toDto(Dispatch e) {
        return new DispatchDto(
                e.getId(),
                e.getWarehouseId(),
                e.getRouteId(),
                e.getScheduledAt(),
                e.getVehicleType(),
                e.getExpectedVolume(),
                e.getVehicleCapacity(),
                e.getFillRate(),
                e.getTriggerReason(),
                e.getStatus().name(),
                e.getPriority(),
                e.getCreatedAt()
        );
    }

    /** ML-ответ → Entity (для сохранения в БД). */
    public static Dispatch fromMlDispatch(MlDispatch ml) {
        var entity = new Dispatch();
        entity.setWarehouseId(ml.warehouseId());
        entity.setRouteId(ml.routeId());
        entity.setScheduledAt(ml.scheduledAt());
        entity.setVehicleType(ml.vehicleType());
        entity.setExpectedVolume(ml.expectedVolume());
        entity.setVehicleCapacity(ml.vehicleCapacity());
        entity.setFillRate(ml.fillRate());
        entity.setTriggerReason(ml.triggerReason());
        entity.setPriority(ml.priority());
        return entity;
    }
}