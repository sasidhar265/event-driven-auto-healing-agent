#!/usr/bin/env bash
set -euo pipefail

PGADMIN_APP="${PGADMIN_APP:-/Applications/pgAdmin 4.app}"
PGADMIN_PYTHON="${PGADMIN_APP}/Contents/Frameworks/Python.framework/Versions/3.13/bin/python3"
PGADMIN_SETUP="${PGADMIN_APP}/Contents/Resources/web/setup.py"
PGADMIN_DATABASE="${PGADMIN_DATABASE:-${HOME}/.pgadmin/pgadmin4.db}"
SERVER_FILE="${SERVER_FILE:-$(pwd)/examples/pgadmin-servers.json}"

if [[ ! -f "${PGADMIN_DATABASE}" ]]; then
  echo "pgAdmin configuration database not found: ${PGADMIN_DATABASE}" >&2
  echo "Launch pgAdmin 4 once, close it, and rerun this script." >&2
  exit 1
fi

"${PGADMIN_PYTHON}" "${PGADMIN_SETUP}" load-servers "${SERVER_FILE}" \
  --sqlite-path "${PGADMIN_DATABASE}"

echo "Registered ART - Postgres.app in pgAdmin 4."
echo "Passwords are not imported; enter the ART database password on first connection."
