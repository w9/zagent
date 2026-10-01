# AGENTS.md

Guidance for coding agents in this repository. Product overview and full configuration:
[README.md](README.md). System design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

- `services/agent/zagent/`: Python 3.12 backend (runtime, BFF, gateway, MCP servers, privacy,
  dispatcher). Tests in `services/agent/tests/`.
- `apps/web/`: React 19, Vite, Tailwind v4 client. Playwright specs in `apps/web/e2e/`.
- `deploy/compose/`: the Compose stack and its network zones.
- `evals/`: eval cases, goldens and fixtures.

## Commands

- `make up` / `make down`: start or stop the full stack (replay mode, no API key needed).
- `make db`: only Postgres and the loopback ingress, for host-side tests.
- `make test`: install, pytest, vitest, web build, then `make lint`.
- `make lint`: ruff and oxlint.
- `make browser`: Playwright against `ZAGENT_WEB_URL` (default `http://127.0.0.1:5173`).

## Web UI

- Follow [docs/DESIGN.md](docs/DESIGN.md) for all work in `apps/web` and
  `services/agent/zagent/job_ui`. Cite rule IDs (for example `COLOR-02`) when a rule shapes a
  change.
- Raw design values live only in `apps/web/src/design/tokens.css`. The Tailwind theme is reset, so
  only token utilities exist; a class that compiles to nothing is a bug.
- Tailwind only sees complete class strings; never build class names with `${}`.
- Design checks live in `apps/web/scripts/design/`: `npm --prefix apps/web run lint:design` for
  the lexical rules, `npm --prefix apps/web test` for tokens and contrast. New UI code must lint
  clean; legacy files fail until the UI rewrite replaces them.
- Storybook: `npm --prefix apps/web run storybook` (port 6006). The token overview is the
  `Design system/Tokens` story; check token changes there in both themes.
- Confirm UI changes with `npm --prefix apps/web run test:design`, which checks every story at
  every viewport in both themes and compares screenshots. Look at the screenshots, not just the
  result. Details in DESIGN.md section 9.

## Running several clones side by side

`deploy/compose/compose.yaml` sets `name: zagent`, so without an override every clone shares one
Compose project and `make up` in one clone replaces another clone's containers. Give each extra
clone a gitignored `.env` with its own project name and ports, for example:

```sh
COMPOSE_PROJECT_NAME=zagent-ui
ZAGENT_WEB_PORT=5273
ZAGENT_AGENT_PORT=8100
ZAGENT_DB_PORT=5532
ZAGENT_GRAFANA_PORT=3100
DATABASE_URL=postgresql://zagent:zagent@localhost:5532/zagent
ZAGENT_TEST_DATABASE_URL=postgresql://zagent:zagent@localhost:5532/zagent_test
ZAGENT_WEB_URL=http://127.0.0.1:5273
```

- Check with `docker compose --project-directory . -f deploy/compose/compose.yaml config` before
  `make up`, and run Make with an explicit directory (`make -C <clone> up`).
- The job image tag `zagent-job:plan8` is hardcoded, so clones share it; the last build wins.
- The Vite dev server pins port 5173 with `strictPort`. When that port is taken, run
  `AGENT_URL=http://127.0.0.1:<agent port> npm --prefix apps/web run dev -- --port <free port>`.
