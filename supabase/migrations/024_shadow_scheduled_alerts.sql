-- Migration 024: Shadow Scheduled Alerts
-- Programmable alerts and reminders for users

CREATE TABLE IF NOT EXISTS shadow_scheduled_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL,

    -- Alert timing
    alert_time TIME NOT NULL,  -- HH:MM format
    timezone TEXT DEFAULT 'America/Sao_Paulo',

    -- Recurrence
    recurrence TEXT NOT NULL DEFAULT 'daily',  -- daily, weekly, weekdays, custom
    days_of_week INTEGER[] DEFAULT '{1,2,3,4,5,6,7}',  -- 1=Monday, 7=Sunday

    -- Alert content
    alert_type TEXT NOT NULL DEFAULT 'summary',  -- summary, reminder, custom
    custom_message TEXT,  -- For custom alerts

    -- Summary options (when alert_type = 'summary')
    include_tasks BOOLEAN DEFAULT TRUE,
    include_appointments BOOLEAN DEFAULT TRUE,
    include_reminders BOOLEAN DEFAULT TRUE,
    include_overdue BOOLEAN DEFAULT TRUE,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_sent_at TIMESTAMPTZ,
    next_scheduled_at TIMESTAMPTZ,

    -- Metadata
    name TEXT,  -- Optional friendly name for the alert
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_owner ON shadow_scheduled_alerts(owner_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_active ON shadow_scheduled_alerts(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_scheduled_alerts_next ON shadow_scheduled_alerts(next_scheduled_at) WHERE is_active = TRUE;

-- Alert history for tracking sent alerts
CREATE TABLE IF NOT EXISTS shadow_alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID REFERENCES shadow_scheduled_alerts(id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    content TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_history_alert ON shadow_alert_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_history_owner ON shadow_alert_history(owner_id);

-- Trigger para atualizar updated_at
CREATE OR REPLACE FUNCTION update_shadow_scheduled_alerts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_shadow_scheduled_alerts_updated_at ON shadow_scheduled_alerts;
CREATE TRIGGER trigger_shadow_scheduled_alerts_updated_at
    BEFORE UPDATE ON shadow_scheduled_alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_shadow_scheduled_alerts_updated_at();

-- Function to calculate next scheduled time
CREATE OR REPLACE FUNCTION shadow_calculate_next_alert(
    p_alert_time TIME,
    p_timezone TEXT,
    p_recurrence TEXT,
    p_days_of_week INTEGER[]
) RETURNS TIMESTAMPTZ AS $$
DECLARE
    v_now TIMESTAMPTZ;
    v_today_alert TIMESTAMPTZ;
    v_next_alert TIMESTAMPTZ;
    v_current_dow INTEGER;
    v_days_ahead INTEGER;
    v_check_dow INTEGER;
BEGIN
    v_now := NOW() AT TIME ZONE p_timezone;
    v_today_alert := (DATE(v_now) + p_alert_time) AT TIME ZONE p_timezone;
    v_current_dow := EXTRACT(ISODOW FROM v_now)::INTEGER;  -- 1=Monday, 7=Sunday

    IF p_recurrence = 'daily' THEN
        IF v_now < v_today_alert THEN
            RETURN v_today_alert;
        ELSE
            RETURN v_today_alert + INTERVAL '1 day';
        END IF;

    ELSIF p_recurrence = 'weekdays' THEN
        -- Monday to Friday
        p_days_of_week := '{1,2,3,4,5}';
    END IF;

    -- For weekly/custom, find next valid day
    FOR v_days_ahead IN 0..7 LOOP
        v_check_dow := ((v_current_dow + v_days_ahead - 1) % 7) + 1;
        IF v_check_dow = ANY(p_days_of_week) THEN
            v_next_alert := v_today_alert + (v_days_ahead || ' days')::INTERVAL;
            IF v_days_ahead = 0 AND v_now >= v_today_alert THEN
                CONTINUE;  -- Skip today if time has passed
            END IF;
            RETURN v_next_alert;
        END IF;
    END LOOP;

    -- Fallback: next day
    RETURN v_today_alert + INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql;

-- Function to get pending alerts
CREATE OR REPLACE FUNCTION shadow_get_pending_alerts()
RETURNS TABLE (
    id UUID,
    owner_id TEXT,
    alert_type TEXT,
    custom_message TEXT,
    include_tasks BOOLEAN,
    include_appointments BOOLEAN,
    include_reminders BOOLEAN,
    include_overdue BOOLEAN,
    timezone TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id,
        a.owner_id,
        a.alert_type,
        a.custom_message,
        a.include_tasks,
        a.include_appointments,
        a.include_reminders,
        a.include_overdue,
        a.timezone
    FROM shadow_scheduled_alerts a
    WHERE a.is_active = TRUE
      AND a.next_scheduled_at <= NOW()
    ORDER BY a.next_scheduled_at;
END;
$$ LANGUAGE plpgsql;

-- Comments
COMMENT ON TABLE shadow_scheduled_alerts IS 'Alertas programáveis pelo usuário';
COMMENT ON COLUMN shadow_scheduled_alerts.recurrence IS 'daily, weekly, weekdays, custom';
COMMENT ON COLUMN shadow_scheduled_alerts.alert_type IS 'summary (resumo), reminder (lembrete fixo), custom (personalizado)';
COMMENT ON COLUMN shadow_scheduled_alerts.days_of_week IS '1=Segunda, 2=Terça, ..., 7=Domingo';
