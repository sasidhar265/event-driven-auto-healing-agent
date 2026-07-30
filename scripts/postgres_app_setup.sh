#!/usr/bin/env bash
set -euo pipefail

POSTGRES_APP_BIN="${POSTGRES_APP_BIN:-/Applications/Postgres.app/Contents/Versions/latest/bin}"
ART_DATABASE="${ART_DATABASE:-healing}"
ART_DATABASE_USER="${ART_DATABASE_USER:-healing}"
ART_DATABASE_PASSWORD="${ART_DATABASE_PASSWORD:-healing}"
ART_ADMIN_USER="${ART_ADMIN_USER:-postgres}"

if [[ ! "${ART_DATABASE}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
   [[ ! "${ART_DATABASE_USER}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
   [[ "${ART_DATABASE_PASSWORD}" == *"'"* ]]; then
  echo "Database/user must be PostgreSQL identifiers and password cannot contain a single quote." >&2
  exit 1
fi

"${POSTGRES_APP_BIN}/pg_isready" -h 127.0.0.1 -p 5432

if ! "${POSTGRES_APP_BIN}/psql" -U "${ART_ADMIN_USER}" -d postgres -Atc \
  "SELECT 1 FROM pg_roles WHERE rolname='${ART_DATABASE_USER}'" | grep -qx 1; then
  "${POSTGRES_APP_BIN}/psql" -U "${ART_ADMIN_USER}" -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE ${ART_DATABASE_USER} WITH LOGIN PASSWORD '${ART_DATABASE_PASSWORD}';"
fi

if ! "${POSTGRES_APP_BIN}/psql" -U "${ART_ADMIN_USER}" -d postgres -Atc \
  "SELECT 1 FROM pg_database WHERE datname='${ART_DATABASE}'" | grep -qx 1; then
  "${POSTGRES_APP_BIN}/createdb" -U "${ART_ADMIN_USER}" -O "${ART_DATABASE_USER}" \
    "${ART_DATABASE}"
fi

.venv/bin/alembic upgrade head

if [[ "${CREATE_EXAMPLE_INTEGRATION_TABLES:-false}" == "true" ]]; then
  PGPASSWORD="${ART_DATABASE_PASSWORD}" "${POSTGRES_APP_BIN}/psql" \
    -h 127.0.0.1 -U "${ART_DATABASE_USER}" -d "${ART_DATABASE}" \
    -v ON_ERROR_STOP=1 -f examples/external_postgres_tables.sql
fi

echo "Postgres.app ART database is ready: ${ART_DATABASE_USER}@127.0.0.1:5432/${ART_DATABASE}"
