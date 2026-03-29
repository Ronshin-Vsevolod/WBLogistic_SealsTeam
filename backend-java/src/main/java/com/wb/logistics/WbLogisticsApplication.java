package com.wb.logistics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import com.wb.logistics.config.AppProperties;

/**
 * Точка входа Java-бэкенда.
 *
 * Этот сервис отвечает ТОЛЬКО за:
 * - хранение рейсов и тактического плана (PostgreSQL)
 * - REST API для фронтенда (Flet)
 * - вызов Python ML-сервиса при поступлении новых данных
 *
 * Вся ML-логика и Decision Engine живут в Python.
 */
@SpringBootApplication
@EnableConfigurationProperties(AppProperties.class)
public class WbLogisticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(WbLogisticsApplication.class, args);
    }
}