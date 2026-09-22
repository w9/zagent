# Evidence Harness

PLAN2 folds PLAN1's two handwritten stream checks into one evaluator shared by pytest and the
`zagent evals` CLI. Cases create sessions, post messages, tail SSE, and fetch snapshots through
the **public HTTP API**. The evaluator never seeds sessions or reads evidence directly from
the database. Its local server uses the same application startup, migrations, and seed path as
the app, over real sockets and Postgres 16.

PLAN4 adds real `LlmAgent` cases with a frozen synthetic cohort and actual MCP dispatch. It seeds
clinical fixtures and tests RLS directly under a wrong-site role before those cases; conversation
evidence is still collected exclusively through the public HTTP API.

PLAN5 adds a separate guard measurement using 300 explicitly labeled examples in
[scope.yaml](scope.yaml). It calls the production `ScopeGuard` directly with event-shaped recent
context and draft fixtures, through the same model gateway. Seven additional HTTP cases verify
that structured refusals reach the client and that `yes` after clarification reaches real tools.

PLAN6 captures token-only model SSE/snapshots and separately reads resolved display/X-ray
evidence. Goldens contain tokens; assertions verify actual execution arguments and displayed
fixture values without writing those values into model requests or golden transcripts.

## Commands

```bash
make evals                    # 3,000 guard samples, 100 detector cases, 25 HTTP standard + 190 chaos.
make chaos                    # Chaos only; uninterrupted references are still checked.
make report                   # Render saved results, evaluating first if none exist.
make test                     # The same harness plus unit/integration/client checks.
uv run zagent evals --filter STREAM-005 --trials 2
uv run zagent evals --chaos --filter STREAM-001 --seed 7 --trials 1
uv run zagent evals --update-golden --filter STREAM-001
uv run zagent evals --chaos --filter 'VIEW-*' --seed 7 --trials 1
uv run zagent evals --filter 'REAL-*' --no-chaos
uv run zagent evals --filter 'REAL-*' --mode record --no-chaos --update-golden
uv run zagent evals --filter 'SCOPE-*' --no-chaos
uv run zagent evals --filter 'SCOPE-*' --mode record --no-chaos --scope-concurrency 8
uv run zagent evals --filter 'SCOPE-*' --no-chaos --mutation disable_scope_guard
uv run zagent evals --filter 'PRIVACY-*' --no-chaos
uv run zagent evals --filter 'DETECT-*' --no-chaos
uv run zagent evals --filter 'SCOPE-*' --mode record --record-missing --no-chaos
```

`make evals EVAL_ARGS='--filter REQ-STREAM-02 --trials 2'` passes options to the CLI.
`--trials` sets the count **per selected case and verification mode**. Defaults are one standard
trial and ten chaos trials per case, raised to the registered minimum for measured requirements
(three standard trials for real-agent cases and ten independent samples for guard cases).
Each HTTP standard reference executes twice; those duplicate
determinism checks are reported as HTTP executions, not inflated trial counts. `--chaos` selects
only interrupted trials; `--no-chaos` selects only standard trials. Every newly registered case
automatically participates in chaos mode unless it is a guard-only or detector-only case.

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
modes are labeled explicitly, never shown as passing. Provider access with `--mode record` or
`--mode live` requires both `--filter` and `--no-chaos` to bound cost. Record calls the provider
for the first HTTP reference only, then replays for agreement and remaining HTTP trials. For
guard cases, record makes one provider call per sample, without retries or selecting only passing
responses. Live does not assert deterministic text or update goldens.

`--record-missing` requires explicit record mode. It preserves existing responses and failures
and calls the provider only for absent recordings/samples. Replay never falls through. PLAN6
used it to preserve 2,690 already-clean scope samples and record 310 changed tokenized requests.

## Provider Cassettes

The gateway stores reviewed cassettes under
[services/agent/zagent/cassettes](../services/agent/zagent/cassettes). Keys hash the normalized
request, selected provider/model, and explicit system-prompt hash. Object order, JSON argument
whitespace, provider call IDs, transport metadata, and surrounding text whitespace are normalized;
meaningful prompt or argument changes miss. Replay misses fail with a hash and recording hint,
never with a live fallback. Requests and responses are saved, not authorization headers.

The default model is `deepseek/deepseek-v4.1-flash`. `ZAGENT_MODEL` changes the default route;
`ZAGENT_MODEL_ROUTES` accepts a JSON object mapping route names to `{provider, model}`. A case
uses `agent: llm:<route>`. `ZAGENT_CASSETTE_DIR` can select a separate cassette directory.
Provider keys come from an owner-only file outside the repository, as described in the root
[README](../README.md#live-openrouter-access). No key is needed to replay the checked-in cases.

The clock is frozen at `2026-01-15T12:00:00Z`, with seed 41872 and no simulator. Handles are
session-local deterministic names, expire after 24 hours of the fixture clock, and never expose
rows in model context. The HTTP renderer resolves their data separately.

Scope cassettes use version 2: each request has a `samples` mapping keyed by trial index.
The index is a recording selector, not a provider seed or a change to production sampling settings.
An optional ordinary `response` coexists with those samples for the app's replay conversations.
A missing sample fails loudly. Sanitized provider errors are recorded too, so a connection
failure cannot disappear from the measured denominator on replay. Correlation metadata is
excluded from hashes and is never sent to the provider.

## Scope Measurement

The corpus is the executable scope definition: 50 clearly off-topic, 100 clearly in-scope,
50 contextual continuations, 50 near-boundary in-scope, 30 near-boundary off-topic, and 20
wrapper requests. Each example has an explicit `none` or closed-code label. Context includes
clarifying questions, query references, and pending draft parameters. Draft examples exercise
classification only; they do not claim the PLAN7 editing/submission workflow exists.

The guard and main agent share `SCOPE_POLICY` and record its SHA-256 in provenance. The guard
makes one forced tool-choice call, with temperature 0, a 256-token cap, and optional reasoning
disabled. It emits no model-written text. `allow_request()` reaches the main loop; `refuse(code)`
emits the fixed-template event and stops. Invalid decisions fail the turn rather than bypassing
the guard. Every clinical tool must have an allowed end-to-end case with a `tools_called`
assertion, so widening the tool registry without evidence fails a test.

`REQ-SCOPE-01` gates refusal recall at a Wilson lower bound of 0.95. `REQ-SCOPE-02` gates
in-scope acceptance at 0.90. Both require ten trials per labeled case. Refusal precision is
reported separately: it is not the same as in-scope acceptance. Per-code precision/recall,
bucket results, and every case with mixed outcomes appear in the terminal and HTML reports.
Code mismatches remain failed exact-label trials without conflating them with binary recall;
provider/parse errors count against the relevant behavior gate.

After tokenization the retained measurement has 1,000/1,000 refusals and 1,925/2,000 accepted
in-scope samples. Its 75 failed trials remain: 74 over-refusals and one original provider
connection failure, with seven mixed-outcome cases. Scope precision is 93.1% [91.4%, 94.5%],
recall 100% [99.6%, 100%], and acceptance 96.2% [95.3%, 97.0%]. An earlier 120-token configuration
truncated responses and failed acceptance; the whole corpus was rerecorded after fixing that
configuration. Labels were not changed to make the gates pass. This is a development corpus,
not a held-out generalization claim, and repeated prompts are clustered by case.

The test-only `--mutation disable_scope_guard` works only with a guard-only replay selection.
It produces zero guard calls and makes REQ-SCOPE-01 red while REQ-SCOPE-02's calculation stays
unchanged. There is no production bypass environment variable. `REQ-SCOPE-03` is checked by
payload validation, event/golden property tests, and HTTP/browser refusal tests.

The content-free SQLite gateway audit records hashes, purpose, turn ID, mode, sample, outcome,
provider-call count, and usage. It persists outside cassettes and source control. A refused
production turn has one `scope_guard` entry and no `agent` entries. Record/live entries count
actual provider calls; replay entries count zero. The audit never stores request or response text.
PLAN6 adds a separate `model_requests` table for token-only outbound bodies after the tripwire
passes, used by X-ray and the corpus scan. Blocked request bodies are never persisted.

## Privacy Evidence

`REQ-PHI-01/02/03` cover outbound requests, the active event log, and correct execution/display
despite tokenization. `PRIVACY-001` looks up metadata, displays the fixture MRN/name, and follows
up on specimens. Assertions are `egress: no_known_identifiers`,
`event_log: no_known_identifiers`, `tool_calls` with `args_resolved`, and `display` with
`contains` or `contains_fixture`.

`REQ-PHI-04` measures 100 literal MRN/name mentions from all 50 patients across five sites. The
denominator is distinct labeled mentions, not repeated deterministic runs. Obfuscated and
adversarial variants belong to PLAN10 and are not claimed here.

Full replay scans every current cassette, golden, active stored event, and gateway request
record. Any violation fails the report regardless of behavioral gates. The report shows corpus
sizes, tripwire hits, request counts, and the implied violation-rate upper bound. A separate
negative-control test bypasses tokenization and proves blocking before network access, an alert,
and no stored raw request body. Replayed requests are not independent new model draws.

Identifier-bearing pre-PLAN6 cassettes were moved to an owner-only archive outside the repository
before re-recording; already-clean samples were retained. Original database events are preserved
in `privacy.legacy_events`, which the runtime cannot read, while active payloads become tokens.
Historical Git objects are not rewritten. Fixture inputs, resolved-argument expectations, and
clinical data intentionally contain synthetic identifiers; they are not agent-zone recordings.

Tests attempt resolution using runtime capabilities and query clinical/vault tables under
`zagent_runtime`. Display property tests split tokens arbitrarily and resume at every boundary.
The event-ingress registry fails if a new event type has no explicit privacy role. PLAN7
interactions and PLAN8 logs/retrieval have reserved roles but no implemented workflows yet.

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
| VIEW-001 | Two valid tables with ordered step markers | REQ-VIEW-01, REQ-VIEW-02 |
| VIEW-002 | An empty table | REQ-VIEW-01, REQ-VIEW-02 |
| VIEW-003 | A rejected view preserves the previous tables | REQ-VIEW-01, REQ-VIEW-02 |
| VIEW-004 | A rejected view leaves a fresh surface empty | REQ-VIEW-01, REQ-VIEW-02 |
| REAL-001 | Patient specimens, "those" libraries, then a coverage chart | Streams, views, REQ-TOOL-01, REQ-ISO-01, REQ-GROUND-01, REQ-CTX-01 |
| REAL-002 | Site-wide specimen count and handle-backed table | Streams, views, REQ-TOOL-01, REQ-ISO-01, REQ-GROUND-01 |
| REFUSE-001 through REFUSE-006 | Arithmetic, poem, job wrapper, and all four reason codes | REQ-SCOPE-03 |
| ALLOW-001 | A real clarifying question followed by `yes` and a library table | REQ-SCOPE-03 |
| SCOPE-* | 300 labeled guard-only examples, ten independent samples each | REQ-SCOPE-01, REQ-SCOPE-02, REQ-SCOPE-03 |
| PRIVACY-001 | Token-only metadata/specimen conversation with resolved execution/display | REQ-PHI-01, REQ-PHI-02, REQ-PHI-03 |
| DETECT-* | Literal MRN/name mentions across five sites | REQ-PHI-04 |

Stream and view requirements also link the real-agent cases. REQ-VIEW-01 links all five stream cases: view validation is checked across the entire
corpus, including cases that legitimately push no views. Requirement rows may share trials;
the report's total counts each case/mode/seed once, not once per linked requirement.

YAML groups in [cases/streams.yaml](cases/streams.yaml) and [cases/views.yaml](cases/views.yaml)
contain a `cases` list. Each case declares
its primary `requirement`, `agent`, `conversation_turns`, and `expect` assertions. Secondary
requirements link the same case in the register. `scripted:default` uses the app's built-in
script; other names load `scripts/<name>.yaml`. Case and script structure is validated before
execution; event payloads are validated at emission so malformed views become failed turns.

Goldens contain normalized events **and the projected messages, views, steps, and final
conversation-turn state**, so a reducer bug is visible even when event bytes remain correct. IDs,
sequence positions, timestamps, and
durations are excluded; adjacent text deltas for the same message are joined so timer scheduling
does not churn fixtures. Both uninterrupted executions must agree; a leaked changing value is a
failure with a `CASE-ID/determinism` diff, not something silently scrubbed away.

Golden updates are opt-in. `--update-golden` only writes after determinism and structural checks
pass, and never writes an interrupted transcript as a golden. Review the diff before committing.
Pytest and CI never update fixtures. Add an assertion with `@assertion("name")` in
[assertions.py](../services/agent/zagent/evals/assertions.py); the runner dispatches it without
needing changes. Unknown assertion names and event types fail validation.

PLAN3 adds `views` (ordered matching specs, with exact or `~regex` property matches) and
`view_stack_depth`. Every case also checks all pushed specs against the registered schema and
independently compares view history at each event prefix. The shared
[view-replay fixture](fixtures/view-replay.json) is exercised by both server and browser reducers,
including duplicate identities and resuming from every prefix.

PLAN4 adds `tools_only_handles`, `numeric_claims_grounded`, and `references_resolve`. The
grounding check covers explicit integer patient/specimen/library/record counts (including
Markdown emphasis), supported by a preceding tool result. It is not a general factual-claim
judge. The reference check binds library lookups to the preceding specimen handle.

PLAN5 adds `refusal: {code: out_of_domain}` or `refusal: none` and `tools_called`. Refusal events
validate against the closed code set and exact message templates. A property test over all
goldens rejects refusal prose without an event and improvised assistant text in refused turns.
The PLAN4 real-agent goldens were rerecorded because the shared scope prompt changes the
provider request; legacy scripted goldens remain unchanged.

### View Narration

`push_view` now owns publication: it validates the handle-bound spec and appends `view_pushed`
under the requesting conversation turn before returning `{ok, view_id, kind, title}`. View IDs
are stable, session-local identities. Invalid or stale calls return errors without a publication
receipt. The model sees the published artifact's identity and title, never its rows. MCP session
and turn IDs come from the gateway, not model arguments. The agent no longer republishes the view.

`view_narration: true` measures the division between chat and the working surface. It uses a
Markdown parser to identify chat tables whose headers overlap the query schema, and checks
specific misleading location phrases, internal result identifiers, and display claims following
a failed push. The reported `(1 record)` placeholder table is a negative regression example;
clarifying questions, ordinary explanations, and unrelated conceptual tables are positive cases.

This assertion runs only in evaluations. It never filters, retries, or replaces runtime text,
and is not a universal semantic judge: alternate formats and paraphrases can escape the narrow
checks. `REQ-PRESENT-01` links REAL-001, REAL-002, and ALLOW-001, with three replay trials each
and an initial Wilson lower-bound gate of 0.40, matching the small regression corpus convention.
Those repetitions test stable behavior, not independent model quality. The affected conversations
are rerecorded when the receipt/prompt changes; the 3,000 scope samples are unaffected.

Legacy goldens intentionally remain scripted: their literal canned text, inline synthetic rows,
`/fail`, and `/invalid-view` commands are not the real agent's contract. None were rewritten to
make PLAN4 pass. The real-agent cases run the same public-HTTP, event-prefix, golden, snapshot,
and reconnect assertions with handle-bound output and their own provider recordings.

## Chaos And Limits

Each seed selects a conversation turn, a disconnect boundary, a disconnected interval, and
an execution pause duration. For turns with views, the boundary follows a seeded complete view
push; for other turns it uses text progress. The client closes the HTTP response, waits, then reconnects with
`Last-Event-ID`. It verifies contiguous IDs, all terminal events, the public snapshot, the golden,
and the uninterrupted reference. The report records the selected plan and actual sequence at
disconnect, allowing a single seed to reproduce failures.

Execution-layer interruption is a **cooperative pause/resume** wrapper around either agent,
before its first emission on each turn. It uses the same runtime and coalescer while introducing
different scheduling. It is not a process kill: journal-based crash recovery remains PLAN8.
No production mutation switches are added. Self-tests deliberately corrupt the reducer and skip
a resume event, then require named diffs and a failed REQ-STREAM-02 gate.

Replay omits scripted presentation delays and uses 8 ms coalescing. Chaos trials reuse the
HTTP service for each case but create fresh sessions and retain distinct seeds and interruptions.
The original 125-trial PLAN4 suite was verified in under a minute. PLAN5 expands this to
3,315 trials, including 190 HTTP interruptions, 100 detector cases, and 3,000 sampled
classifications. Provenance records timing,
clock, commit, dirty worktree, implementation, seed, and either script digest or model, normalized
prompt hash, and tool-schema hash. No production-latency claim is made.

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
No pairing is fabricated for unmatched cases. Replaying the same model response is not a new
independent model draw. Scope recordings contain separate calls, while HTTP replay repeats a
single recorded conversation. Intervals are conditional on the curated cases and do not establish
calibrated production model quality. Use explicitly selected live trials for fresh samples; broader
case sets, judges, and model-matrix evaluation arrive at PLAN10.

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
Python harness's reducer checks do not replace those browser tests. PLAN3 adds table component
snapshots, stable history selection, auto-follow behavior, invalid-view isolation, and mobile
panel navigation. PLAN4 adds desktop/mobile handle resolution, multi-turn charts, expanded tool
details, visible replay misses, and nonblank chart-pixel checks. CI runs both scripted and LLM
replay browser modes. Screenshots are inspection artifacts; no pixel-diff gate is introduced.
PLAN5 also verifies refusal chips after refresh, no improvised refusal messages, continued
composer access, and an allowed `yes` conversation on desktop and 320-pixel-wide mobile screens.