PYTHON ?= python3.12
VENV ?= .venv

.PHONY: setup test coverage migrate api api-integration api-admin api-full worker \
	backbone validate-integration verify-art \
	db-setup db-inspect pgadmin-register

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

test:
	PYTHONPATH=. $(VENV)/bin/pytest -q

coverage:
	$(VENV)/bin/coverage run --source=app -m pytest -q
	$(VENV)/bin/coverage report -m

migrate:
	$(VENV)/bin/alembic upgrade head

api:
	$(VENV)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

api-integration:
	API_PROFILE=integration $(VENV)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

api-admin:
	API_PROFILE=admin $(VENV)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

api-full:
	API_PROFILE=full $(VENV)/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

worker:
	$(VENV)/bin/python -m app.worker

backbone:
	$(VENV)/bin/python -m app.backbone

validate-integration:
	$(VENV)/bin/python -m app.integrations.postgres_bridge_cli

verify-art:
	$(VENV)/bin/python scripts/verify_art_lifecycle.py

db-setup:
	./scripts/db_setup.sh

db-inspect:
	./scripts/db_inspect.sh

pgadmin-register:
	./scripts/pgadmin_register.sh
