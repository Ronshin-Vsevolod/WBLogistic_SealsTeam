-- Тактический план: прогноз объёмов и потребности в ТС на каждый день.
-- Обновляется при каждом прогоне macro-модели.
CREATE TABLE tactical_plan (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    warehouse_id      VARCHAR(64)    NOT NULL,
    plan_date         DATE           NOT NULL,       -- День, на который прогноз
    forecast_volume   DECIMAL(12,2)  NOT NULL,       -- Ожидаемый суммарный объём за день
    required_trucks   INTEGER        NOT NULL CHECK (required_trucks >= 0),

    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),

    -- Один склад + один день = одна строка (при обновлении перезаписываем)
    UNIQUE (warehouse_id, plan_date)
);

CREATE INDEX idx_plan_warehouse_date ON tactical_plan(warehouse_id, plan_date);