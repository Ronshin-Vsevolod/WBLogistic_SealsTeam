package com.wb.logistics.config;

import com.wb.logistics.client.MlServiceClient;
import com.wb.logistics.dto.ml.MlPredictionRequest;
import com.wb.logistics.dto.ml.MlPredictionResponse;
import com.wb.logistics.dto.ml.MlPredictionResponse.MlDispatch;
import com.wb.logistics.dto.ml.MlPredictionResponse.MlPlanEntry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.annotation.Profile;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

/**
 * Профиль "local" — подменяет ML-клиент заглушкой.
 * Java работает полностью автономно: БД + API + моковые данные.
 *
 * Активируется: --spring.profiles.active=local
 */
@Configuration
@Profile("local")
public class LocalProfile {

    private static final Logger log = LoggerFactory.getLogger(LocalProfile.class);

    @Bean
    @Primary  // Перекрывает настоящий MlServiceClient
    public MlServiceClient mockMlClient() {
        log.warn("⚠️  MOCK ML-клиент активирован (профиль local)");

        return new MlServiceClient(new AppProperties("http://mock")) {
            @Override
            public MlPredictionResponse predict(MlPredictionRequest req) {
                String wh = String.valueOf(req.officeFromId());
                var now = Instant.ofEpochMilli(req.timestamp());

                log.info("MOCK ML получил интеграции: traffic={}, promo={}, "
                                + "microWeather={} шт, macroWeather={} шт",
                        req.integrations().traffic(),
                        req.integrations().promo(),
                        req.integrations().microWeather().size(),
                        req.integrations().macroWeather().size());

                // Генерируем 2 тестовых рейса
                var dispatches = List.of(
                        new MlDispatch(wh, req.routeId(), now.plusSeconds(1800),
                                "20t_truck", new BigDecimal("28.5"),
                                new BigDecimal("30"), new BigDecimal("0.95"),
                                "CAPACITY_FULL", 2),
                        new MlDispatch(wh, req.routeId(), now.plusSeconds(3600),
                                "small_van", new BigDecimal("4.2"),
                                new BigDecimal("5"), new BigDecimal("0.84"),
                                "SLA_PREEMPTIVE", 1)
                );

                // Генерируем план на 3 дня
                var today = LocalDate.now();
                var plan = List.of(
                        new MlPlanEntry(wh, today, new BigDecimal("90"), 3),
                        new MlPlanEntry(wh, today.plusDays(1), new BigDecimal("120"), 4),
                        new MlPlanEntry(wh, today.plusDays(2), new BigDecimal("75"), 3)
                );

                log.info("MOCK → {} рейсов, {} строк плана", dispatches.size(), plan.size());
                return new MlPredictionResponse(dispatches, plan);
            }
        };
    }
}