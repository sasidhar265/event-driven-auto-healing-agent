#!/usr/bin/env bash
set -euo pipefail

ART_DATABASE="${ART_DATABASE:-healing}"
ART_DATABASE_USER="${ART_DATABASE_USER:-healing}"
ART_DATABASE_PASSWORD="${ART_DATABASE_PASSWORD:-healing}"
ART_ADMIN_USER="${ART_ADMIN_USER:-postgres}"
ART_ADMIN_PASSWORD="${ART_ADMIN_PASSWORD:-}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
PSQL="${PSQL:-psql}"
CREATEDB="${CREATEDB:-createdb}"

if [[ ! "${ART_DATABASE}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
   [[ ! "${ART_DATABASE_USER}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] ||
   [[ "${ART_DATABASE_PASSWORD}" == *"'"* ]]; then
  echo "Database/user must be PostgreSQL identifiers and password cannot contain a single quote." >&2
  exit 1
fi

if [[ -n "${ART_ADMIN_PASSWORD}" ]]; then
  export PGPASSWORD="${ART_ADMIN_PASSWORD}"
fi

if ! "${PSQL}" -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${ART_ADMIN_USER}" -d postgres -Atc \
  "SELECT 1 FROM pg_roles WHERE rolname='${ART_DATABASE_USER}'" | grep -qx 1; then
  "${PSQL}" -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${ART_ADMIN_USER}" -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE ROLE ${ART_DATABASE_USER} WITH LOGIN PASSWORD '${ART_DATABASE_PASSWORD}';"
fi

if ! "${PSQL}" -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
  -U "${ART_ADMIN_USER}" -d postgres -Atc \
  "SELECT 1 FROM pg_database WHERE datname='${ART_DATABASE}'" | grep -qx 1; then
  "${CREATEDB}" -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
    -U "${ART_ADMIN_USER}" -O "${ART_DATABASE_USER}" "${ART_DATABASE}"
fi

echo "PostgreSQL database is ready: ${ART_DATABASE_USER}@${POSTGRES_HOST}:${POSTGRES_PORT}/${ART_DATABASE}"
echo "Run 'make migrate' to create or update the application schema."
