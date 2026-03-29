package com.wb.logistics.repository;

import com.wb.logistics.entity.TacticalPlanEntry;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface TacticalPlanRepository extends JpaRepository<TacticalPlanEntry, UUID> {

    /** Весь план для склада, отсортированный по дате. */
    List<TacticalPlanEntry> findByWarehouseIdOrderByPlanDateAsc(String warehouseId);

    /** Конкретный день для конкретного склада (для upsert). */
    Optional<TacticalPlanEntry> findByWarehouseIdAndPlanDate(
            String warehouseId, LocalDate planDate
    );
}