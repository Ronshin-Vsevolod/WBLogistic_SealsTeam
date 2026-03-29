package com.wb.logistics.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * JPA-сущность: один рейс (заявка на вызов ТС).
 *
 * Lombok-аннотации:
 * - @Getter / @Setter — генерирует get/set для всех полей
 * - @NoArgsConstructor — пустой конструктор (требование JPA)
 */
@Entity
@Table(name = "dispatches")
@Getter
@Setter
@NoArgsConstructor
public class Dispatch {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    /** ID склада (соответствует office_from_id из сырых данных). */
    @Column(nullable = false)
    private String warehouseId;

    /** ID маршрута — для уведомления перевозчика, отвечающего за этот маршрут. */
    private Integer routeId;

    /** Плановое время подачи ТС на гейт. */
    @Column(nullable = false)
    private Instant scheduledAt;

    /** Тип ТС: small_van / 10t_truck / 20t_truck. */
    @Column(nullable = false)
    private String vehicleType;

    /** Ожидаемый объём загрузки (ед. ёмкости). */
    @Column(nullable = false)
    private BigDecimal expectedVolume;

    /** Полная ёмкость выбранного ТС. */
    @Column(nullable = false)
    private BigDecimal vehicleCapacity;

    /** Коэффициент заполнения: expected / capacity (0.0–1.0). */
    @Column(nullable = false)
    private BigDecimal fillRate;

    /** Причина вызова: CAPACITY_FULL, SLA_BREACH, SLA_PREEMPTIVE, HORIZON_END, MANUAL. */
    @Column(nullable = false)
    private String triggerReason;

    /** Текущий статус рейса. */
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private DispatchStatus status = DispatchStatus.PLANNED;

    /** Приоритет: 1 = критический, 5 = фоновый. */
    @Column(nullable = false)
    private int priority = 3;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    // --- Lifecycle callbacks: автозаполнение дат ---

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