package com.wb.logistics.controller;

import com.wb.logistics.dto.DispatchDto;
import com.wb.logistics.dto.StatusUpdateRequest;
import com.wb.logistics.service.DispatchService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

/**
 * Рейсы создаются автоматически через IngestService (ML → БД).
 * Диспетчер может только просматривать и менять статус.
 */
@RestController
@RequestMapping("/api/v1/dispatch")
public class DispatchController {

    private final DispatchService service;

    public DispatchController(DispatchService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DispatchDto getById(@PathVariable UUID id) {
        return service.getById(id);
    }

    @PatchMapping("/{id}/status")
    public DispatchDto updateStatus(
            @PathVariable UUID id,
            @Valid @RequestBody StatusUpdateRequest request
    ) {
        return service.updateStatus(id, request.newStatus());
    }
}