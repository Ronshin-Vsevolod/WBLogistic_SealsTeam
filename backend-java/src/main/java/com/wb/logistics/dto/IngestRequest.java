package com.wb.logistics.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

/**
 * Входящие данные со склада.
 * Формат совпадает с тем, что генерирует feature_logger.py.
 *
 * Java record — иммутабельный класс-контейнер.
 * Компилятор сам генерирует конструктор, equals, hashCode, toString.
 */
public record IngestRequest(

        @NotNull
        Integer officeFromId,

        @NotNull
        @Positive
        Integer routeId,

        @NotNull
        Long timestamp,

        // Статусы — количество единиц в каждом статусе на гейте.
        // Имена совпадают с колонками в train_team_track.parquet.
        int status1,
        int status2,
        int status3,
        int status4,
        int status5,
        int status6,
        int status7,
        int status8
) {
}