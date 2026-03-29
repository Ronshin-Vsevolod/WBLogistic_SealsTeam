package com.wb.logistics.repository;

import com.wb.logistics.entity.Dispatch;
import com.wb.logistics.entity.DispatchStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Репозиторий рейсов.
 *
 * Spring Data JPA автоматически реализует эти методы
 * на основе имён (Query Derivation). SQL писать не нужно.
 */
@Repository
public interface DispatchRepository extends JpaRepository<Dispatch, UUID> {

    /** Все рейсы склада, отсортированные по времени подачи. */
    List<Dispatch> findByWarehouseIdOrderByScheduledAtAsc(String warehouseId);

    /** Рейсы склада в заданном временном окне. */
    List<Dispatch> findByWarehouseIdAndScheduledAtBetweenOrderByScheduledAtAsc(
            String warehouseId, Instant from, Instant to
    );

    /** Рейсы по статусу (для мониторинга). */
    List<Dispatch> findByStatus(DispatchStatus status);

    /** Удалить все PLANNED рейсы склада (перед пересозданием из нового прогноза). */
    void deleteByWarehouseIdAndStatus(String warehouseId, DispatchStatus status);
}