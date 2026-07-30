-- Example only. Existing tables may use different names; map those names using
-- .env.integration.example rather than changing ART code.

CREATE SCHEMA IF NOT EXISTS operations;

CREATE TABLE IF NOT EXISTS operations.failure_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  source TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
  correlation_key TEXT NOT NULL,
  payload JSONB NOT NULL,
  tenant_id TEXT NOT NULL,
  actor TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  art_ingested_at TIMESTAMPTZ,
  art_status TEXT,
  art_suggestion JSONB
);

CREATE TABLE IF NOT EXISTS operations.art_suggestions (
  suggestion_id UUID PRIMARY KEY,
  event_id TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  agent_type TEXT NOT NULL,
  suggestion JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_failure_events_art_pending
  ON operations.failure_events (created_at)
  WHERE art_ingested_at IS NULL;
