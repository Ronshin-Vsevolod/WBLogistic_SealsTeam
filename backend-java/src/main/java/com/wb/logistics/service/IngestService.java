package com.wb.logistics.service;

import com.wb.logistics.client.MlServiceClient;
import com.wb.logistics.dto.IngestRequest;
import com.wb.logistics.dto.IntegrationData;
import com.wb.logistics.dto.ml.MlPredictionRequest;
import com.wb.logistics.dto.ml.MlPredictionResponse;
import com.wb.logistics.entity.Dispatch;
import com.wb.logistics.entity.DispatchStatus;
import com.wb.logistics.entity.TacticalPlanEntry;
import com.wb.logistics.mapper.DispatchMapper;
import com.wb.logistics.repository.DispatchRepository;
import com.wb.logistics.repository.TacticalPlanRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Сервис приёма данных.
 *
 * Вызывается каждые ~30 мин, когда приходит новая порция
 * данных со склада.
 *
 * Алгоритм:
 *  1. Валидация входных данных (на уровне DTO + здесь)
 *  2. Отправка в Python ML-сервис
 *  3. Получение готовых заявок + плана
 *  4. Удаление старых PLANNED-рейсов (они устарели — новый прогноз их заменяет)
 *  5. Сохранение новых рейсов
 *  6. Upsert тактического плана
 */
@Service
public class IngestService {

    private static final Logger log = LoggerFactory.getLogger(IngestService.class);

    private final MlServiceClient mlClient;
    private final IntegrationService integrationService;
    private final DispatchRepository dispatchRepo;
    private final TacticalPlanRepository planRepo;

    public IngestService(
            MlServiceClient mlClient,
            IntegrationService integrationService,
            DispatchRepository dispatchRepo,
            TacticalPlanRepository planRepo
    ) {
        this.mlClient = mlClient;
        this.integrationService = integrationService;
        this.dispatchRepo = dispatchRepo;
        this.planRepo = planRepo;
    }

    @Transactional
    public int processIngest(IngestRequest req) {
        String warehouseId = String.valueOf(req.officeFromId());

        log.info("Ingest: склад={}, маршрут={}, ts={}", warehouseId, req.routeId(), req.timestamp());
        // 1. Собираем интеграционные данные (заглушки)
        IntegrationData integrations = integrationService.gatherIntegrations(warehouseId);

        // 2. Формируем запрос к Python ML (данные + интеграции)
        var mlRequest = new MlPredictionRequest(
                req.officeFromId(),
                req.routeId(),
                req.timestamp(),
                req.status1(), req.status2(), req.status3(), req.status4(),
                req.status5(), req.status6(), req.status7(), req.status8(),
                integrations
        );

        // 3. Вызываем Python (Macro → baseline → Micro → Decision Engine)
        MlPredictionResponse mlResponse = mlClient.predict(mlRequest);

        // 4. Удаляем устаревшие PLANNED-рейсы
        dispatchRepo.deleteByWarehouseIdAndStatus(warehouseId, DispatchStatus.PLANNED);

        // 5. Сохраняем новые рейсы через маппер
        for (var mlDispatch : mlResponse.dispatches()) {
            Dispatch entity = DispatchMapper.fromMlDispatch(mlDispatch);
            dispatchRepo.save(entity);
        }

        // 6. Upsert тактического плана
        for (var mlPlan : mlResponse.tacticalPlan()) {
            TacticalPlanEntry entry = planRepo
                    .findByWarehouseIdAndPlanDate(mlPlan.warehouseId(), mlPlan.planDate())
                    .orElseGet(TacticalPlanEntry::new);

            entry.setWarehouseId(mlPlan.warehouseId());
            entry.setPlanDate(mlPlan.planDate());
            entry.setForecastVolume(mlPlan.forecastVolume());
            entry.setRequiredTrucks(mlPlan.requiredTrucks());
            planRepo.save(entry);
        }

        log.info("Ingest OK: {} рейсов, {} строк плана",
                mlResponse.dispatches().size(), mlResponse.tacticalPlan().size());

        return mlResponse.dispatches().size();
    }
}