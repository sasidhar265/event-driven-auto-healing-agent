#!/usr/bin/env bash
set -euo pipefail

POSTGRES_APP_BIN="${POSTGRES_APP_BIN:-/Applications/Postgres.app/Contents/Versions/latest/bin}"
ART_DATABASE="${ART_DATABASE:-healing}"
ART_DATABASE_USER="${ART_DATABASE_USER:-healing}"
ART_DATABASE_PASSWORD="${ART_DATABASE_PASSWORD:-healing}"

PGPASSWORD="${ART_DATABASE_PASSWORD}" "${POSTGRES_APP_BIN}/psql" \
  -h 127.0.0.1 -U "${ART_DATABASE_USER}" -d "${ART_DATABASE}" -P pager=off \
  -c "SELECT version();" \
  -c "SELECT version_num AS migration FROM alembic_version;" \
  -c "SELECT * FROM art_reporting.tenant_summary ORDER BY latest_event_at DESC NULLS LAST;" \
  -c "SELECT event_type, outcome, active, use_count, decided_by, decided_at FROM art_reporting.reference_library ORDER BY decided_at DESC LIMIT 20;"
