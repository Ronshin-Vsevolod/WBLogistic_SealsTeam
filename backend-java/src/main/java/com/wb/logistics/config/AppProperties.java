package com.wb.logistics.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Кастомные настройки приложения.
 * Читаются из блока "app:" в application.yml.
 *
 * Аналог Pydantic Settings из Python-части.
 * Spring автоматически маппит app.ml-service-url → mlServiceUrl.
 */
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        /** URL Python ML-сервиса (напр. http://ml-service:8000) */
        String mlServiceUrl
) {
}