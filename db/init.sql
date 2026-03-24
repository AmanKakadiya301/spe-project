-- db/init.sql
-- Auto-runs when PostgreSQL container starts for the first time.
-- Creates all tables needed by the FinTech stock app.
-- Safe to re-run: uses IF NOT EXISTS everywhere.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(80)  NOT NULL UNIQUE,
    email         VARCHAR(120) UNIQUE,                  -- filled in after Google OAuth
    google_id     VARCHAR(120) UNIQUE,                  -- set after Option B (Google OAuth)
    password_hash VARCHAR(256),                         -- NULL for OAuth-only users
    role          VARCHAR(20)  NOT NULL DEFAULT 'user', -- 'user' | 'admin'
    avatar_url    TEXT,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role     ON users(role);

-- ── Portfolio Items ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS portfolio_items (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     VARCHAR(20) NOT NULL,
    shares     NUMERIC(12, 4) DEFAULT 0,           -- number of shares owned
    avg_price  NUMERIC(12, 4) DEFAULT 0,           -- average buy price
    added_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_user ON portfolio_items(user_id);

-- ── Alerts ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol       VARCHAR(20)  NOT NULL,
    target_price NUMERIC(12,4) NOT NULL,
    direction    VARCHAR(10)  NOT NULL CHECK (direction IN ('above', 'below')),
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    triggered    BOOLEAN      NOT NULL DEFAULT FALSE,
    triggered_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_user      ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol    ON alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_alerts_active    ON alerts(is_active) WHERE is_active = TRUE;

-- ── Audit Log ──────────────────────────────────────────────────────────────────
-- Tracks every important action for the admin panel
CREATE TABLE IF NOT EXISTS audit_log (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    username   VARCHAR(80),                        -- denormalised for deleted users
    action     VARCHAR(100) NOT NULL,              -- e.g. 'login', 'add_symbol', 'delete_alert'
    target     VARCHAR(200),                       -- e.g. 'AAPL', 'alert#42'
    ip_address VARCHAR(45),
    metadata   JSONB,                              -- any extra data
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user      ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_action    ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_created   ON audit_log(created_at DESC);

-- ── Tracked Symbols ───────────────────────────────────────────────────────────
-- Persists the admin-managed symbol list across restarts
CREATE TABLE IF NOT EXISTS tracked_symbols (
    id         SERIAL PRIMARY KEY,
    symbol     VARCHAR(20)  NOT NULL UNIQUE,
    name       VARCHAR(200),
    sector     VARCHAR(100),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    added_by   INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    added_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Seed with default 12 symbols
INSERT INTO tracked_symbols (symbol, name, sector) VALUES
    ('AAPL',  'Apple Inc.',           'Technology'),
    ('GOOGL', 'Alphabet Inc.',        'Technology'),
    ('MSFT',  'Microsoft Corp.',      'Technology'),
    ('AMZN',  'Amazon.com Inc.',      'Consumer Cyclical'),
    ('TSLA',  'Tesla Inc.',           'Consumer Cyclical'),
    ('META',  'Meta Platforms Inc.',  'Technology'),
    ('NVDA',  'NVIDIA Corp.',         'Technology'),
    ('AMD',   'Advanced Micro Devices','Technology'),
    ('INTC',  'Intel Corp.',          'Technology'),
    ('NFLX',  'Netflix Inc.',         'Communication'),
    ('IBM',   'IBM Corp.',            'Technology'),
    ('ORCL',  'Oracle Corp.',         'Technology')
ON CONFLICT (symbol) DO NOTHING;

-- ── Price History Cache (optional — use InfluxDB later for large scale) ────────
CREATE TABLE IF NOT EXISTS price_snapshots (
    id         BIGSERIAL PRIMARY KEY,
    symbol     VARCHAR(20)  NOT NULL,
    price      NUMERIC(12,4) NOT NULL,
    change     NUMERIC(12,4),
    change_pct NUMERIC(8,4),
    volume     BIGINT,
    source     VARCHAR(20),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_symbol  ON price_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshots_time    ON price_snapshots(captured_at DESC);

-- Keep only 7 days of snapshots (run via cron or pg_cron later)
-- DELETE FROM price_snapshots WHERE captured_at < NOW() - INTERVAL '7 days';

-- ── Seed Admin User ───────────────────────────────────────────────────────────
-- Default admin: username=admin, password=admin123 (change immediately!)
-- Password hash below = bcrypt hash of 'admin123'
INSERT INTO users (username, role, password_hash) VALUES (
    'admin',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBP36K8J.9gOuO'
) ON CONFLICT (username) DO NOTHING;
