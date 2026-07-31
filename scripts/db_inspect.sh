#!/usr/bin/env bash
set -euo pipefail

ART_DATABASE="${ART_DATABASE:-healing}"
ART_DATABASE_USER="${ART_DATABASE_USER:-healing}"
ART_DATABASE_PASSWORD="${ART_DATABASE_PASSWORD:-healing}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
PSQL="${PSQL:-psql}"

PGPASSWORD="${ART_DATABASE_PASSWORD}" "${PSQL}" \
  -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${ART_DATABASE_USER}" -d "${ART_DATABASE}" -P pager=off \
  -c "SELECT version();" \
  -c "SELECT version_num AS migration FROM alembic_version;" \
  -c "SELECT * FROM art_reporting.tenant_summary ORDER BY latest_event_at DESC NULLS LAST;" \
  -c "SELECT event_type, outcome, active, use_count, decided_by, decided_at FROM art_reporting.reference_library ORDER BY decided_at DESC LIMIT 20;" \
  -c "SELECT * FROM art.v_agent_run_summary ORDER BY started_at DESC NULLS LAST LIMIT 20;" \
  -c "SELECT * FROM art.v_correlation_trace LIMIT 20;"
