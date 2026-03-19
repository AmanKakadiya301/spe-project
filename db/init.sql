-- db/init.sql — CREATE at db/init.sql
-- Auto-runs when PostgreSQL container first starts.
-- Safe to re-run: uses IF NOT EXISTS everywhere.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(80)  NOT NULL UNIQUE,
    email         VARCHAR(120) UNIQUE,
    google_id     VARCHAR(120) UNIQUE,
    password_hash VARCHAR(256),
    role          VARCHAR(20)  NOT NULL DEFAULT 'user',
    avatar_url    TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS portfolio_items (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     VARCHAR(20)    NOT NULL,
    shares     NUMERIC(12,4)  DEFAULT 0,
    avg_price  NUMERIC(12,4)  DEFAULT 0,
    added_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol       VARCHAR(20)    NOT NULL,
    target_price NUMERIC(12,4)  NOT NULL,
    direction    VARCHAR(10)    NOT NULL CHECK (direction IN ('above','below')),
    is_active    BOOLEAN        NOT NULL DEFAULT TRUE,
    triggered    BOOLEAN        NOT NULL DEFAULT FALSE,
    triggered_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    username   VARCHAR(80),
    action     VARCHAR(100) NOT NULL,
    target     VARCHAR(200),
    ip_address VARCHAR(45),
    meta       JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tracked_symbols (
    id        SERIAL PRIMARY KEY,
    symbol    VARCHAR(20)   NOT NULL UNIQUE,
    name      VARCHAR(200),
    sector    VARCHAR(100),
    is_active BOOLEAN       NOT NULL DEFAULT TRUE,
    added_by  INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    added_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id          BIGSERIAL PRIMARY KEY,
    symbol      VARCHAR(20)    NOT NULL,
    price       NUMERIC(12,4)  NOT NULL,
    change      NUMERIC(12,4),
    change_pct  NUMERIC(8,4),
    source      VARCHAR(20),
    captured_at TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_symbol ON price_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshots_time   ON price_snapshots(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created    ON audit_log(created_at DESC);

INSERT INTO tracked_symbols (symbol, name, sector) VALUES
    ('AAPL','Apple Inc.','Technology'),('GOOGL','Alphabet Inc.','Technology'),
    ('MSFT','Microsoft Corp.','Technology'),('AMZN','Amazon.com Inc.','Consumer Cyclical'),
    ('TSLA','Tesla Inc.','Consumer Cyclical'),('META','Meta Platforms Inc.','Technology'),
    ('NVDA','NVIDIA Corp.','Technology'),('AMD','Advanced Micro Devices','Technology'),
    ('INTC','Intel Corp.','Technology'),('NFLX','Netflix Inc.','Communication'),
    ('IBM','IBM Corp.','Technology'),('ORCL','Oracle Corp.','Technology')
ON CONFLICT (symbol) DO NOTHING;

-- Default admin user (password: admin123 — CHANGE IMMEDIATELY)
INSERT INTO users (username, role, password_hash) VALUES
    ('admin','admin','$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBP36K8J.9gOuO')
ON CONFLICT (username) DO NOTHING;
