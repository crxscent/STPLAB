-- PostgreSQL schema: validated incidents, monitoring rules, aggregated metrics
CREATE TABLE IF NOT EXISTS monitoring_rules (
    id          SERIAL PRIMARY KEY,
    rule_type   TEXT NOT NULL UNIQUE CHECK (rule_type IN ('WHALE','VOLATILITY','VOLUME_SPIKE')),
    threshold   NUMERIC NOT NULL,
    window_sec  INTEGER NOT NULL DEFAULT 0,
    cooldown_sec INTEGER NOT NULL DEFAULT 30,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO monitoring_rules (rule_type, threshold, window_sec, cooldown_sec, description) VALUES
 ('WHALE',        50000, 0,   0,   'Single trade above threshold, USD'),
 ('VOLATILITY',   1.5,   60,  30,  'Deviation of price from 60s moving average, %'),
 ('VOLUME_SPIKE', 3.0,   600, 120, 'Rolling 10-min volume vs baseline, multiplier')
ON CONFLICT (rule_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS anomalies (
    id            BIGSERIAL PRIMARY KEY,
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    trade_time    TIMESTAMPTZ NOT NULL,
    symbol        TEXT NOT NULL,
    signal_type   TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'MEDIUM',
    price         NUMERIC NOT NULL,
    volume        NUMERIC NOT NULL,
    total_usd     NUMERIC NOT NULL,
    side          TEXT,
    trade_id      TEXT,
    metric_value  NUMERIC,
    threshold     NUMERIC,
    message       TEXT NOT NULL,
    notify_status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING / SENT / FAILED / SKIPPED
    notified_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_anomalies_time ON anomalies (detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_symbol ON anomalies (symbol, detected_at DESC);

-- 10-second aggregates per asset for the dashboard (VWAP, volatility, volume deviation)
CREATE TABLE IF NOT EXISTS market_metrics (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    last_price      NUMERIC NOT NULL,
    vwap            NUMERIC NOT NULL,
    volatility_pct  NUMERIC NOT NULL,
    trades          INTEGER NOT NULL,
    volume_usd      NUMERIC NOT NULL,
    volume_dev_pct  NUMERIC NOT NULL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON market_metrics (ts DESC);

-- Notify listeners (API / notification service) on each new anomaly
CREATE OR REPLACE FUNCTION notify_anomaly() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('anomalies', NEW.id::text);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_anomaly ON anomalies;
CREATE TRIGGER trg_notify_anomaly AFTER INSERT ON anomalies
FOR EACH ROW EXECUTE FUNCTION notify_anomaly();
