package com.wb.logistics.service;

import com.wb.logistics.dto.IntegrationData;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Заглушки внешних интеграций.
 *
 * В продакшне каждый метод — HTTP-вызов к реальному API:
 *   - Яндекс.Погода → microWeatherHourly, macroWeatherDaily
 *   - Яндекс.Пробки → traffic
 *   - CRM/ERP       → promo
 *
 * Сейчас возвращает фиксированные правдоподобные данные.
 * Для демо этого достаточно — показываем, что архитектура
 * готова к подключению реальных источников.
 */
@Service
public class IntegrationService {

    private static final Logger log = LoggerFactory.getLogger(IntegrationService.class);

    /**
     * Собрать все интеграционные данные для одного запроса.
     *
     * @param warehouseId ID склада (в будущем — для geo-привязки погоды)
     */
    public IntegrationData gatherIntegrations(String warehouseId) {

        List<Double> microWeather = fetchMicroWeather(warehouseId);
        double traffic = fetchTraffic(warehouseId);
        List<Double> macroWeather = fetchMacroWeather(warehouseId);
        List<Double> promo = fetchPromo(warehouseId);

        log.info("Интеграции для склада {}: "
                        + "microWeather={} шт, traffic={}, macroWeather={} шт, promo={}",
                warehouseId, microWeather.size(), traffic, macroWeather.size(), promo);

        return new IntegrationData(microWeather, traffic, macroWeather, promo);
    }

    // ── Заглушки (каждая — будущая точка подключения реального API) ──

    /**
     * STUB: Погода по часам на 5 часов вперёд.
     * В продакшне: GET https://api.weather.yandex.ru/v2/forecast?hours=6
     */
    private List<Double> fetchMicroWeather(String warehouseId) {
        // Умеренная погода: severity 2-3, с ухудшением к вечеру
        return List.of(2.0, 2.5, 3.0, 3.5, 3.0);
    }

    /**
     * STUB: Коэффициент пробок.
     * В продакшне: GET https://api.routing.yandex.net/v2/summary
     */
    private double fetchTraffic(String warehouseId) {
        // Умеренные пробки
        return 3.0;
    }

    /**
     * STUB: Средняя погода по дням на 7 дней.
     * В продакшне: GET https://api.weather.yandex.ru/v2/forecast?days=7
     */
    private List<Double> fetchMacroWeather(String warehouseId) {
        return List.of(2.0, 3.0, 4.0, 3.0, 2.0, 1.0, 2.0);
    }

    /**
     * STUB: Промо-коэффициент.
     * В продакшне: GET https://erp.internal/api/promo?warehouse=...
     */
    private List<Double> fetchPromo(String warehouseId) {
        // Нет активных промо
        return List.of(2.0, 1.0, 1.0, 3.0, 2.0, 1.0, 1.0);
    }
}