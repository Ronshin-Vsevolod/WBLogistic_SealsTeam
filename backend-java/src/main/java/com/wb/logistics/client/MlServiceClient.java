package com.wb.logistics.client;

import com.wb.logistics.config.AppProperties;
import com.wb.logistics.dto.ml.MlPredictionRequest;
import com.wb.logistics.dto.ml.MlPredictionResponse;
import com.wb.logistics.exception.MlServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;

import java.time.Duration;
/**
 * HTTP-клиент для вызова Python ML-сервиса.
 *
 * Использует Spring RestClient (Spring Boot 3.2+)
 */
@Component
@Profile("!local")
public class MlServiceClient {

    private static final Logger log = LoggerFactory.getLogger(MlServiceClient.class);

    private final RestClient restClient;

    public MlServiceClient(AppProperties props) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(15));

        this.restClient = RestClient.builder()
                .baseUrl(props.mlServiceUrl())
                .requestFactory(factory)
                .build();

        log.info("ML-client → {} (connect=5s, read=15s)", props.mlServiceUrl());
    }

    /**
     * Отправляет сырые данные в Python и получает обратно
     * готовые заявки + тактический план.
     */
    public MlPredictionResponse predict(MlPredictionRequest request) {
        log.info("→ ML: warehouse={}, route={}", request.officeFromId(), request.routeId());

        try {
            var response = restClient.post()
                    .uri("/predict")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(request)
                    .retrieve()
                    .body(MlPredictionResponse.class);

            if (response == null) {
                throw new MlServiceException("ML вернул пустой ответ");
            }

            log.info("← ML: {} рейсов, {} строк плана",
                    response.dispatches().size(), response.tacticalPlan().size());
            return response;

        } catch (MlServiceException e) {
            throw e;
        } catch (Exception e) {
            throw new MlServiceException("ML недоступен: " + e.getMessage(), e);
        }
    }
}