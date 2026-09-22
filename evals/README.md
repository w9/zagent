# PLAN1 evidence

These are the two hand-written invariant tests required by PLAN1, not the PLAN2 eval harness.
They exercise a real Postgres 16 event log and a real HTTP server on an ephemeral loopback
port. Each tested conversation turn gets a fresh session; tests use the separate
`zagent_test` database.

| Requirement | Check | Evidence |
|---|---|---|
| REQ-STREAM-01 | Fixed ScriptedAgent conversation turn matches the checked-in normalized transcript | [test_streams.py](test_streams.py), [goldens/scripted.json](goldens/scripted.json) |
| REQ-STREAM-02 | 50 seeded disconnects resume with Last-Event-ID and match an uninterrupted conversation turn | [test_streams.py](test_streams.py) |

```bash
make test
make chaos
uv run pytest evals/test_streams.py -k seed-17 -v
```

Each chaos seed selects an event boundary within a conversation turn and a disconnected
interval. The test drops the HTTP stream, leaves the background conversation turn executing,
reconnects from the last received SSE id, and checks contiguous sequences, normalized events,
and the projected client transcript.
No provider or API key is involved. Timing is accelerated, but persistence and HTTP transport
are the same code paths used by the app. Golden files are reviewed fixtures, never regenerated
automatically by a test.

The normalizer retains event types and significant payload fields, strips ids/timestamps/
durations, and joins adjacent text deltas for the same message. This makes the assertion
independent of the coalescing timer's scheduling without masking text loss or duplication.

The current event contract uses schema v2 and `conversation_turn_*` lifecycle types. A migration
regression test also loads a v1 database, upgrades it, and verifies unchanged historical event
rows, sequence continuity, append-only protection, and continued conversation turns.

Other focused checks live in [services/agent/tests](../services/agent/tests) and
[apps/web/src/lib/events.test.ts](../apps/web/src/lib/events.test.ts). Browser acceptance tests
in [apps/web/e2e/spine.spec.ts](../apps/web/e2e/spine.spec.ts) run with `make browser` after
`make up`. They use a test-only forwarding proxy to drop physical SSE connections and inspect
the native resume header at the server boundary. Desktop and mobile screenshots are written
under `apps/web/test-results/` and retained as CI artifacts.

Set `ZAGENT_TEST_DATABASE_URL` to use another Postgres test database. Migrations run
automatically; tests do not truncate an existing database or delete sessions.