package com.wb.logistics.controller;

import com.wb.logistics.dto.IngestRequest;
import com.wb.logistics.service.IngestService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * POST /api/v1/ingest-data
 *
 * Принимает порцию данных со склада (формат feature_logger.py),
 * прогоняет через Python ML, сохраняет результаты в БД.
 */
@RestController
@RequestMapping("/api/v1")
public class IngestController {

    private final IngestService ingestService;
    
    public IngestController(IngestService ingestService) {
        this.ingestService = ingestService;
    }

    @PostMapping("/ingest-data")
    public ResponseEntity<Map<String, Object>> ingest(@Valid @RequestBody IngestRequest request) {
        int dispatchCount = ingestService.processIngest(request);

        return ResponseEntity.ok(Map.of(
                "status", "ok",
                "dispatches_created", dispatchCount
        ));
    }
}