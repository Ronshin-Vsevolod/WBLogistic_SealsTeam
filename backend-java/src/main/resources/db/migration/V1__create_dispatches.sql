-- Таблица рейсов.
-- Каждая строка = одна заявка на вызов ТС на конкретный склад.
CREATE TABLE dispatches (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    warehouse_id      VARCHAR(64)    NOT NULL,     -- ID склада (office_from_id)
    route_id          INTEGER,                     -- ID маршрута (для уведомления перевозчика)
    scheduled_at      TIMESTAMPTZ    NOT NULL,     -- Когда ТС должно быть на гейте

    vehicle_type      VARCHAR(32)    NOT NULL,     -- Тип ТС: small_van / 10t_truck / 20t_truck
    expected_volume   DECIMAL(10,2)  NOT NULL CHECK (expected_volume >= 0),
    vehicle_capacity  DECIMAL(10,2)  NOT NULL CHECK (vehicle_capacity > 0),
    fill_rate         DECIMAL(5,4)   NOT NULL CHECK (fill_rate BETWEEN 0 AND 1),

    trigger_reason    VARCHAR(32)    NOT NULL,     -- CAPACITY_FULL / SLA_BREACH / SLA_PREEMPTIVE / HORIZON_END / MANUAL
    status            VARCHAR(20)    NOT NULL DEFAULT 'PLANNED',
    priority          INTEGER        NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),

    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Индексы для типичных запросов фронтенда
CREATE INDEX idx_dispatches_warehouse  ON dispatches(warehouse_id);
CREATE INDEX idx_dispatches_scheduled  ON dispatches(scheduled_at);
CREATE INDEX idx_dispatches_status     ON dispatches(status);