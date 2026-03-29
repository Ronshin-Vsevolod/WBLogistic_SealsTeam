package com.wb.logistics.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

/**
 * JPA-сущность: одна строка тактического плана.
 * Каждая строка = прогноз на один день для одного склада.
 *
 * Уникальный ключ (warehouse_id, plan_date) гарантирует,
 * что на один день/склад — ровно одна строка.
 * При обновлении прогноза мы перезаписываем существующую строку.
 */
@Entity
@Table(
        name = "tactical_plan",
        uniqueConstraints = @UniqueConstraint(
                columnNames = {"warehouseId", "planDate"}
        )
)
@Getter
@Setter
@NoArgsConstructor
public class TacticalPlanEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String warehouseId;

    /** День, на который составлен прогноз. */
    @Column(nullable = false)
    private LocalDate planDate;

    /** Суммарный прогнозный объём за день (ед. ёмкости). */
    @Column(nullable = false)
    private BigDecimal forecastVolume;

    /** Необходимое количество фур (целое число). */
    @Column(nullable = false)
    private int requiredTrucks;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void onCreate() {
        var now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = Instant.now();
    }
}