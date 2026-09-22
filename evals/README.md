# Evidence Harness

PLAN2 folds PLAN1's two handwritten stream checks into one evaluator shared by pytest and the
`zagent evals` CLI. Cases create sessions, post messages, tail SSE, and fetch snapshots through
the **public HTTP API**. The evaluator never seeds sessions or reads evidence directly from
the database. Its local server uses the same application startup, migrations, and seed path as
the app, over real sockets and Postgres 16.

## Commands

```bash
make evals                    # 5 golden trials plus 50 seeded chaos trials.
make chaos                    # Chaos only; uninterrupted references are still checked.
make report                   # Render saved results, evaluating first if none exist.
make test                     # The same harness plus unit/integration/client checks.
uv run zagent evals --filter STREAM-005 --trials 2
uv run zagent evals --chaos --filter STREAM-001 --seed 7 --trials 1
uv run zagent evals --update-golden --filter STREAM-001
```

`make evals EVAL_ARGS='--filter REQ-STREAM-02 --trials 2'` passes options to the CLI.
`--trials` sets the count **per selected case and verification mode**. Defaults are one standard
trial and ten chaos trials per case. Each standard reference executes twice; those duplicate
determinism checks are reported as HTTP executions, not inflated trial counts. `--chaos` selects
only interrupted trials; `--no-chaos` selects only standard trials. Every newly registered case
automatically participates in chaos mode.

The report is [docs/evals/index.html](../docs/evals/index.html), with structured data in
[docs/evals/results.json](../docs/evals/results.json). Both are generated and ignored by Git;
open the HTML directly, with no server, scripts, CDN, or API key. The report shows requirement
gates, linked cases, normalized transcripts, assertion diffs, trial counts, and provenance.

To compare against a stored result:

```bash
cp docs/evals/results.json /tmp/zagent-baseline.json
uv run zagent evals --baseline /tmp/zagent-baseline.json
uv run zagent report --input docs/evals/results.json --baseline /tmp/zagent-baseline.json
```

`--output` selects a different report directory. `zagent report` only renders stored evidence;
it does not contact Postgres. Nonzero exit status means a failed gate, uncovered requirement,
invalid configuration, or execution error. Filtered requirements and unselected verification
modes are labeled explicitly, never shown as passing. `--mode live` is recognized but rejected:
provider evaluation is deferred to PLAN4 and PLAN10.

## Cases And Goldens

[requirements.yaml](requirements.yaml) is the requirement register. Invariants name enforcement
sites, linked cases, and detecting mutations; measured requirements name a lower-bound threshold
and a minimum trial count. Mutation names are traceability entries, not production fault switches.

| Case | Scenario | Requirement Links |
|---|---|---|
| STREAM-001 | One multi-paragraph response | REQ-STREAM-01, REQ-STREAM-02 |
| STREAM-002 | Two conversation turns in one session | REQ-STREAM-01, REQ-STREAM-02 |
| STREAM-003 | Agent exception with partial text | REQ-STREAM-01, REQ-STREAM-02 |
| STREAM-004 | A successful turn after a failed turn | REQ-STREAM-01, REQ-STREAM-02 |
| STREAM-005 | A partial assistant message is removed and replaced | REQ-STREAM-01, REQ-STREAM-02 |

YAML groups in [cases/streams.yaml](cases/streams.yaml) contain a `cases` list. Each case declares
its primary `requirement`, `agent`, `conversation_turns`, and `expect` assertions. Secondary
requirements link the same case in the register. `scripted:default` uses the app's built-in
script; other names load `scripts/<name>.yaml`. Case and script data are validated before execution.

Goldens contain normalized events **and the projected messages and final conversation-turn
state**, so a reducer bug is visible even when event bytes remain correct. IDs, timestamps, and
durations are excluded; adjacent text deltas for the same message are joined so timer scheduling
does not churn fixtures. Both uninterrupted executions must agree; a leaked changing value is a
failure with a `CASE-ID/determinism` diff, not something silently scrubbed away.

Golden updates are opt-in. `--update-golden` only writes after determinism and structural checks
pass, and never writes an interrupted transcript as a golden. Review the diff before committing.
Pytest and CI never update fixtures. Add an assertion with `@assertion("name")` in
[assertions.py](../services/agent/zagent/evals/assertions.py); the runner dispatches it without
needing changes. Unknown assertion names and event types fail validation.

## Chaos And Limits

Each seed selects a conversation turn, a text-progress boundary, a disconnected interval, and
an execution pause duration. The client closes the HTTP response, waits, then reconnects with
`Last-Event-ID`. It verifies contiguous IDs, all terminal events, the public snapshot, the golden,
and the uninterrupted reference. The report records the selected plan and actual sequence at
disconnect, allowing a single seed to reproduce failures.

Execution-layer interruption is a **cooperative pause/resume** wrapper around `ScriptedAgent`,
before its first emission on each turn. It uses the same runtime and coalescer while introducing
different scheduling. It is not a process kill: journal-based crash recovery remains PLAN8.
No production mutation switches are added. Self-tests deliberately corrupt the reducer and skip
a resume event, then require named diffs and a failed REQ-STREAM-02 gate.

Timing is accelerated to keep the full default suite in tens of seconds: 0.04x script delays
and 8 ms coalescing. Provenance records these values, the current UTC clock, commit and dirty
worktree flag, script digest, implementation, and seed. Model, prompt hash, tool-schema hash,
and KB version are explicit null placeholders. No claim of production latency or model quality
is made by these deterministic fixtures.

## Statistics

All requirement rows show trials and a 95% Wilson interval. Invariants require zero failed trials;
measured gates use the lower bound and the registered per-case sample minimum. Requirements with
no linked cases are `UNCOVERED` and fail the gate.

For a case with `c` successful trials out of `n`, `pass^k` estimates the probability that `k`
distinct trials all succeed: the product of `(c-i)/(n-i)` for `i` from zero to `k-1`. It is zero
when fewer than `k` trials succeed, and unavailable when fewer than `k` trials exist. Requirement
rows average available per-case estimates only when every selected case has enough evidence.
It is reported separately from the gating metric; `--pass-k` defaults to 3.

Baseline comparisons pair by case ID, verification mode, and seed, and report improvements,
regressions, unmatched trials, paired rate difference, and an exact two-sided McNemar p-value.
No pairing is fabricated for unmatched cases. These statistics are implemented and unit-tested
now; real nondeterministic measured requirements arrive in later plans.

## Development And CI

Set `ZAGENT_TEST_DATABASE_URL` to a dedicated Postgres database, never the running app database.
The local evaluator owns one runtime at a time; do not run concurrent harness processes against
the same database. It leaves test sessions in place rather than truncating or deleting them.

[test_streams.py](test_streams.py) calls the same `evaluate_suite` as the CLI and checks its result
objects. [test_harness.py](test_harness.py) tests the harness itself, including its negative controls,
statistics, CLI, report escaping, and uncovered-requirement behavior.

The [Evidence workflow](../.github/workflows/plan1.yml) runs the suite and chaos on pull requests,
retains HTML/JSON as artifacts even on failures, and publishes successful main-branch evidence
to `/evals/` on GitHub Pages. In repository Settings > Pages, select **GitHub Actions** as the
source; local development cannot enable that repository setting or perform the hosted deployment.

The existing client reducer tests and `make browser` remain separate frontend acceptance gates.
They prove actual browser refresh, native SSE reconnect, tab closure, and mobile layout; the
Python harness's reducer checks do not replace those browser tests.