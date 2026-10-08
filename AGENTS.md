# AGENTS.md

Guidance for coding agents in this repository. Product overview and full configuration:
[README.md](README.md). System design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Shorthand

- **AQ**: ask the user questions (for clarification or confirmation, in rounds if needed) using
  the ask-questions tool before acting.

## Layout

- `services/agent/zagent/`: Python 3.12 backend (runtime, BFF, gateway, MCP servers, privacy,
  dispatcher). Tests in `services/agent/tests/`.
- `services/knowledge/zknowledge/`: the separately owned knowledge service and its intranet
  (`site/`). It must not import `zagent`. Tests in `services/knowledge/tests/`.
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
  change. The intranet (`services/knowledge/zknowledge/site`) imitates other products and does
  not use the design system; it only has to stay accessible.
- Raw design values live only in `apps/web/src/design/tokens.css`. The Tailwind theme is reset, so
  only token utilities exist; a class that compiles to nothing is a bug.
- Tailwind only sees complete class strings; never build class names with `${}`.
- Components live in `apps/web/src/components/` by area: `ui/` (primitives), `shell/`, `chat/`,
  `surface/`, `xray/`. Data fetching stays in `App.tsx` and `lib/`; components take data as props
  so stories can render every state.
- There are no semantic CSS class names. Tests select by role, label, `data-testid` or data
  attributes such as `data-view-id`, `data-session-id` and `data-token`.
- Design checks live in `apps/web/scripts/design/`: `npm --prefix apps/web run lint:design` for
  the lexical rules (part of `make lint`), `npm --prefix apps/web test` for tokens and contrast.
- Storybook: `npm --prefix apps/web run storybook` (port 6006). The token overview is the
  `Design system/Tokens` story; check token changes there in both themes.
- Confirm UI changes with `npm --prefix apps/web run test:design`, which checks every story at
  every viewport in both themes and compares screenshots. Look at the screenshots, not just the
  result. Details in DESIGN.md section 9.
- To run the e2e specs against uncommitted UI code, start a dev server on a free port (see below)
  and set `ZAGENT_WEB_URL` to it; the Compose `web` container serves the code it was built from.

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
ZAGENT_INTRANET_PORT=5280
DATABASE_URL=postgresql://zagent:zagent@localhost:5532/zagent
ZAGENT_TEST_DATABASE_URL=postgresql://zagent:zagent@localhost:5532/zagent_test
ZAGENT_WEB_URL=http://127.0.0.1:5273
```

- Check with `docker compose --project-directory . -f deploy/compose/compose.yaml config` before
  `make up`, and run Make with an explicit directory (`make -C <clone> up`).
- The job image tag `zagent-job:plan8` is hardcoded, so clones share it; the last build wins.
- Host-side tests and evals in every clone write `~/.local/state/zagent/gateway-audit.sqlite3`.
  Running two at once can fail with `database is locked`; set `ZAGENT_GATEWAY_AUDIT` per clone.
- The Vite dev server pins port 5173 with `strictPort`. When that port is taken, run
  `AGENT_URL=http://127.0.0.1:<agent port> npm --prefix apps/web run dev -- --port <free port>`.
- To try backend changes without rebuilding the stack, run `make db`, then serve the app on the
  host: `DATABASE_URL=postgresql://zagent:zagent@localhost:<db port>/zagent ZAGENT_AGENT=scripted
  uv run --frozen uvicorn zagent.app:app --port <free port>`, and point `AGENT_URL` at it.
