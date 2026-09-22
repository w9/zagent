-include .env

ZAGENT_WEB_PORT ?= 5173
ZAGENT_AGENT_PORT ?= 8000
ZAGENT_DB_PORT ?= 5432
DATABASE_URL ?= postgresql://zagent:zagent@localhost:$(ZAGENT_DB_PORT)/zagent
ZAGENT_TEST_DATABASE_URL ?= postgresql://zagent:zagent@localhost:$(ZAGENT_DB_PORT)/zagent_test
ZAGENT_SCRIPT ?=

COMPOSE = docker compose --project-directory . -f deploy/compose/compose.yaml
export UV_LINK_MODE = copy
export DATABASE_URL ZAGENT_TEST_DATABASE_URL ZAGENT_WEB_PORT ZAGENT_AGENT_PORT ZAGENT_DB_PORT ZAGENT_SCRIPT

.PHONY: up down db install test chaos lint browser transcript logs

up:
	$(COMPOSE) up --build -d --wait
	@printf '\nZagent: http://localhost:%s\n' '$(ZAGENT_WEB_PORT)'

down:
	$(COMPOSE) down

db:
	$(COMPOSE) up -d --wait postgres

install:
	uv sync --frozen
	npm --prefix apps/web ci

test: install db
	uv run --frozen pytest
	npm --prefix apps/web test
	npm --prefix apps/web run build
	$(MAKE) lint

chaos: db
	uv run --frozen pytest evals/test_streams.py -m chaos -v

lint:
	uv run --frozen ruff check services/agent evals conftest.py
	uv run --frozen ruff format --check services/agent evals conftest.py
	npm --prefix apps/web run lint

browser:
	npm --prefix apps/web run test:e2e

transcript:
	uv run --frozen zagent transcript $(SESSION)

logs:
	$(COMPOSE) logs -f