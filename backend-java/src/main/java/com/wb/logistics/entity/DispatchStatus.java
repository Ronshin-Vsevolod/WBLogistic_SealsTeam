package com.wb.logistics.entity;

/**
 * Жизненный цикл рейса (заявки на ТС).
 *
 * Допустимые переходы:
 *   PLANNED → CONFIRMED → COMPLETED
 *   Любой   → CANCELLED
 *
 * COMPLETED и CANCELLED — терминальные, из них выйти нельзя.
 */
public enum DispatchStatus {
    PLANNED,
    CONFIRMED,
    COMPLETED,
    CANCELLED;

    /**
     * Проверяет, допустим ли переход из текущего статуса в целевой.
     */
    public boolean canTransitionTo(DispatchStatus target) {
        if (this == target) return true;          // idempotent
        if (this == COMPLETED || this == CANCELLED) return false; // терминальные

        return switch (this) {
            case PLANNED   -> target == CONFIRMED || target == CANCELLED;
            case CONFIRMED -> target == COMPLETED || target == CANCELLED;
            default -> false;
        };
    }
}