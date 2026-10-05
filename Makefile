-include .env

ZAGENT_WEB_PORT ?= 5173
ZAGENT_AGENT_PORT ?= 8000
ZAGENT_DB_PORT ?= 5432
DATABASE_URL ?= postgresql://zagent:zagent@localhost:$(ZAGENT_DB_PORT)/zagent
ZAGENT_TEST_DATABASE_URL ?= postgresql://zagent:zagent@localhost:$(ZAGENT_DB_PORT)/zagent_test
ZAGENT_SCRIPT ?=
ZAGENT_AGENT ?= llm
ZAGENT_LLM_MODE ?= replay
ZAGENT_MODEL ?= openai/gpt-6-luna
MODE ?= replay
EVAL_ARGS ?=
MUTATE ?=

COMPOSE = docker compose --project-directory . -f deploy/compose/compose.yaml
export UV_LINK_MODE = copy
export DATABASE_URL ZAGENT_TEST_DATABASE_URL ZAGENT_WEB_PORT ZAGENT_AGENT_PORT ZAGENT_DB_PORT ZAGENT_SCRIPT
export ZAGENT_AGENT ZAGENT_LLM_MODE ZAGENT_MODEL

.PHONY: up live down db install test evals chaos report lint browser transcript logs matrix zones

up:
	$(COMPOSE) up --build -d --wait
	@printf '\nZagent: http://localhost:%s\n' '$(ZAGENT_WEB_PORT)'

live:
	$(COMPOSE) -f deploy/compose/live.yaml up --build -d --wait
	@printf '\nZagent (live): http://localhost:%s\n' '$(ZAGENT_WEB_PORT)'

down:
	$(COMPOSE) down

db:
	$(COMPOSE) up -d --wait --no-recreate postgres ingress

install:
	uv sync --frozen
	npm --prefix apps/web ci
	npm --prefix apps/web run build:mcp

test: install db
	uv run --frozen pytest
	npm --prefix apps/web test
	npm --prefix apps/web run build
	$(MAKE) lint

evals: db
	uv run --frozen zagent evals --mode $(MODE) $(if $(MUTATE),--mutate $(MUTATE)) $(EVAL_ARGS)

matrix: db
	uv run --frozen zagent matrix --mode $(MODE) $(EVAL_ARGS)

chaos: db
	uv run --frozen zagent evals --chaos --mode $(MODE) $(EVAL_ARGS)

docs/evals/results.json:
	$(MAKE) evals

report: docs/evals/results.json
	uv run --frozen zagent report $(EVAL_ARGS)

lint:
	uv run --frozen ruff check services/agent services/knowledge evals deploy/compose conftest.py
	uv run --frozen ruff format --check services/agent services/knowledge evals deploy/compose conftest.py
	npm --prefix apps/web run lint
	npm --prefix apps/web run lint:design

browser:
	npm --prefix apps/web run test:e2e

transcript:
	uv run --frozen zagent transcript $(SESSION)

logs:
	$(COMPOSE) logs -f

zones:
	uv run --frozen python deploy/compose/zones.py verify