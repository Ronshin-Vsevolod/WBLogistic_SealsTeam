package com.wb.logistics.service;

import com.wb.logistics.dto.DispatchDto;
import com.wb.logistics.entity.Dispatch;
import com.wb.logistics.entity.DispatchStatus;
import com.wb.logistics.exception.ResourceNotFoundException;
import com.wb.logistics.repository.DispatchRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import com.wb.logistics.mapper.DispatchMapper;

import java.util.List;
import java.util.UUID;

/**
 * CRUD рейсов + управление статусами.
 */
@Service
public class DispatchService {

    private final DispatchRepository repo;

    public DispatchService(DispatchRepository repo) {
        this.repo = repo;
    }

    /** Все рейсы для склада, по возрастанию времени. */
    public List<DispatchDto> getByWarehouse(String warehouseId) {
        return repo.findByWarehouseIdOrderByScheduledAtAsc(warehouseId)
                .stream()
                .map(DispatchMapper::toDto)
                .toList();
    }

    /** Один рейс по ID. */
    public DispatchDto getById(UUID id) {
        return DispatchMapper.toDto(findOrThrow(id));
    }

    /** Удаление рейса. */
    @Transactional
    public void delete(UUID id) {
        if (!repo.existsById(id)) {
            throw new ResourceNotFoundException("Рейс не найден: " + id);
        }
        repo.deleteById(id);
    }

    /**
     * Смена статуса рейса с проверкой допустимости перехода.
     * Правила переходов определены в DispatchStatus.canTransitionTo().
     */
    @Transactional
    public DispatchDto updateStatus(UUID id, DispatchStatus newStatus) {
        Dispatch entity = findOrThrow(id);
        DispatchStatus current = entity.getStatus();

        if (!current.canTransitionTo(newStatus)) {
            throw new IllegalStateException(
                    "Недопустимый переход статуса: " + current + " → " + newStatus
            );
        }

        entity.setStatus(newStatus);
        return DispatchMapper.toDto(repo.save(entity));
    }

    // --- Внутренние методы ---

    private Dispatch findOrThrow(UUID id) {
        return repo.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Рейс не найден: " + id));
    }
}