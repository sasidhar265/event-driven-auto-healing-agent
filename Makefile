PYTHON ?= python3.12
VENV ?= .venv

.PHONY: setup test migrate api worker backbone validate-integration \
	postgres-app-setup postgres-app-inspect pgadmin-register

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

test:
	PYTHONPATH=. $(VENV)/bin/pytest -q

migrate:
	$(VENV)/bin/alembic upgrade head

api:
	$(VENV)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

worker:
	$(VENV)/bin/python -m app.worker

backbone:
	$(VENV)/bin/python -m app.backbone

validate-integration:
	$(VENV)/bin/python -m app.integrations.postgres_bridge_cli

postgres-app-setup:
	./scripts/postgres_app_setup.sh

postgres-app-inspect:
	./scripts/postgres_app_inspect.sh

pgadmin-register:
	./scripts/pgadmin_register.sh
