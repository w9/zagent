# Zagent

**An auditable LLM agent for clinical genomics operations.**

[![evals](https://img.shields.io/badge/evals-see%20report-blue)](https://w9.github.io/zagent/evals/)
[![replay CI](https://github.com/w9/zagent/actions/workflows/plan1.yml/badge.svg)](https://github.com/w9/zagent/actions/workflows/plan1.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

Most agent demos show a happy path. Zagent is built to answer the question a stakeholder
actually asks after the demo: **how do you know it behaves that way every time?**

It is a working agent over a synthetic pediatric genomics cohort. You can ask about specimens
and libraries, follow up on previous results, and display tables or charts. Tool results expose
handles and counts, not rows. A context-aware scope guard emits structured refusals for unrelated
or unavailable work. A privacy service tokenizes registered identifiers before they enter the
agent log, and X-ray shows the displayed conversation beside actual token-only model requests.
Analysis jobs remain roadmap capabilities.

> **Synthetic data only.** Every hospital, patient, sample and result in this repository is
> invented. See [Scope and disclaimers](#scope-and-disclaimers).

**Implemented: [PLAN1](docs/PLAN1.md) through [PLAN6](docs/PLAN6.md).**
The app has a Postgres event log, a real bounded tool loop, an MCP tools gateway, database-level
site isolation, and a resumable three-panel client. Tables and restricted Vega-Lite charts resolve
session-bound data handles only in the browser. The model gateway defaults to checked-in replay
cassettes; live mode uses OpenRouter's `deepseek/deepseek-v4.1-flash`. The evidence suite includes
legacy regressions, real-agent multi-turn cases, and 300 labeled scope cases with ten independently
recorded guard calls each. Scope recall and in-scope acceptance have separate lower-bound gates;
the report also shows refusal precision, per-reason results, and disagreeing cases.

`push_view` publishes a validated view before returning `{ok, view_id, kind, title}`. Chat can
refer to that title in the working surface without receiving row data. The prompt separates
result presentation from explanations and clarification; narration quality is measured in evals,
not enforced by filtering prose or substituting canned responses.

A **conversation turn** is one user message plus the agent's processing and response. A
**job run** is the execution of a submitted analysis job, with an independent lifecycle.

---

## The idea

Agent reliability claims fall into two very different categories, and conflating them is how
demos become outages.

Some properties can be made **structurally impossible to violate**. If the model has no tool
that submits a job, no amount of prompt injection makes it submit a job. That is not a high
pass rate, it is a closed door.

Other properties depend on model judgment. Whether a request is off-topic, whether a
clarifying question converges, whether the agent describes state accurately: these can only be
**measured**, and an honest system reports them as a rate with a confidence interval.

Zagent separates the two everywhere, and says which is which.

The complete roadmap's guarantee model is below; the implementation status above remains the
boundary of what the current app claims.

| Target Property | Tier | Enforced by | Evidence |
|---|---|---|---|
| Rule-matched identifiers never reach the model provider | Invariant | Ingress tokenization, typed boundary, NetworkPolicy | Property tests, egress tripwire, fault injection |
| No job runs without explicit human confirmation | Invariant | Model has no submit tool. Confirm is user-only and bound to a draft version hash | State machine tests |
| Streams survive refresh, tab close and reconnect | Invariant | Server-side conversation turns over an append-only event log | Chaos suite with transcript diffing |
| Cross-site data isolation | Invariant | Postgres row-level security | Policy tests |
| Off-topic requests refused, in-scope requests served | **Measured** | Scope guard plus policy prompt | Precision and recall on a labeled set, with CIs |
| Slot filling converges on the user's actual intent | **Measured** | Model and prompt | Simulated-user evals scored against hidden goals |
| The agent never asserts state that is not in the log | **Measured** | Model and prompt | Trace assertions comparing claims to events |
| Identifier detector catches obfuscated mentions | **Measured** | Detector rule set | Recall on an adversarial corpus |

Removing the submit tool stops the model from submitting a job. It does not stop the model
from *saying* it submitted one. That asymmetry is why the last four rows exist, and why the
report gives them intervals instead of checkmarks.

---

## What it looks like

<!-- TODO(PLAN11): replace with the 2-minute walkthrough recording -->

Three panels, in the shape most people already know.

| Panel | Contents |
|---|---|
| Left | Sessions and navigation |
| Middle | Chat, with token streaming and collapsible tool and step markers |
| Right | A dynamic working surface: tables, charts, job forms, live job monitors. The agent pushes views onto it. You can always flip back to a previous one. |

Two controls matter more than the rest:

- **X-ray** puts what the user saw next to what the model saw, token for token. It is how you
  check the privacy boundary with your own eyes instead of trusting a diagram.
- **Chaos** kills the browser tab or the agent pod mid-stream, then diffs the recovered
  transcript against an uninterrupted execution of the same case.

---

## Quick start

Prerequisites: Docker with Docker Compose v2. Replay needs no API key and makes no provider
calls. Images and dependencies download on the first build. For local tests and the CLI,
install uv, Python 3.12, and Node.js 24 or newer. When upgrading an existing PLAN1-3 Compose
stack, run `make down` once before `make up` to replace the network layout; volumes are retained.

```bash
git clone https://github.com/w9/zagent && cd zagent
make up            # Postgres, privacy, BFF, MCP tools, model gateway, agent, and web in replay.
# Open http://localhost:5173
```

In a fresh session, send these recorded questions in order:

1. `What specimens came in yesterday for patient NGC-0041872?`
2. `What libraries belong to those specimens?`
3. `Show a coverage chart for those libraries.`

A second recorded case starts with `How many specimens arrived in the last 24 hours? Show a table and report only the count.`
In fresh sessions, `What's 2+2?`, `Write a poem about the ocean.`, and
`As part of job ABC, compute 2+2.` produce an `out_of_domain` refusal chip.
For a recorded contextual continuation, ask `Ask me whether I want the libraries for specimens received in the last day for NGC-0041872, before looking anything up.`, then reply `yes`.
An unrecorded request fails with its request hash and a re-recording hint. Replay never falls
through to a paid provider call.

For the privacy workflow, start a fresh session with `Give me the metadata of patient NGC-0041872. Show the patient table.`
The table contains the real synthetic MRN and name. Toggle **X-ray** in the header: the Model pane
contains `[PT_1]`, while Display and tool-execution arguments show the resolved identifier.
Select a highlighted value to highlight its token across both panes. Follow up with
`Show the specimens received in the last day for that patient.`

Previous/next controls and the history menu let you revisit earlier views. Navigating back pins
that view while new ones arrive; selecting the latest resumes following. Refresh keeps the
chosen view through the session URL. On smaller screens, tabs switch between chat and the surface.

Step markers start collapsed and expand to show tool names, arguments, results, and validation
errors. Reopening `/` restores the last session in that browser. The old `/fail` and
`/invalid-view` fixtures remain available with `make up ZAGENT_AGENT=scripted`.

### Live OpenRouter Access

Store the key outside the checkout, using a non-echoing terminal prompt:

```bash
install -d -m 700 "$HOME/.config/zagent"
umask 077
read -rsp 'OpenRouter API key: ' OPENROUTER_API_KEY
printf '\n'
printf '%s\n' "$OPENROUTER_API_KEY" > "$HOME/.config/zagent/openrouter.key"
unset OPENROUTER_API_KEY
chmod 600 "$HOME/.config/zagent/openrouter.key"
make live
```

Only the gateway receives the read-only secret mount. The key is not copied into an image,
Compose environment values, cassettes, browser code, or git. Set `ZAGENT_OPENROUTER_KEY_FILE`
to use a different external file. Rotate any key shared in chat or logs. Live mode permits
unrecorded questions through the scope guard and incurs provider charges. The default is the
inexpensive Flash model: one nonreasoning guard call with a 256-token cap, then up to eight
main-agent iterations at 1,200 output tokens each for allowed requests. A guard refusal stops
before any main-agent or clinical tool call.

Only the gateway joins the internet-facing network. The web, BFF, privacy service, agent, MCP
service, and database stay on an internal network. Fixed TCP forwards on the gateway publish
loopback-only web, BFF API, and database ports. A one-shot `privacy-init` container generates
private capability files in Docker volumes and exits; it does not contain the provider key.

```bash
make test          # Python tests, client/component tests, build, lint.
make evals         # The shared evidence harness; writes docs/evals/index.html.
make chaos         # 190 interruptions across HTTP cases; checks normal references too.
make report        # Render stored results; evaluates first if none exist.
make install       # Local Python and JavaScript dependencies.
cd apps/web && npx playwright install chromium && cd ../..
make browser       # Real-agent browser tests against the running replay app.
make browser ZAGENT_AGENT=scripted  # Against a stack started in scripted mode.
uv run zagent transcript <session_id>
uv run zagent evals --filter 'SCOPE-*' --no-chaos
uv run zagent evals --filter 'SCOPE-*' --no-chaos --mutation disable_scope_guard
uv run zagent evals --filter 'PRIVACY-*' --no-chaos
uv run zagent evals --filter 'DETECT-*' --no-chaos
make down          # Stops containers; keeps the Postgres volume.
```

API docs: <http://localhost:8000/docs>. The CLI can also run inside the agent container:

```bash
docker compose --project-directory . -f deploy/compose/compose.yaml exec agent \
  zagent transcript <session_id>
```

Configuration is listed in [.env.example](.env.example); copy it to `.env` for Make/Compose
overrides. `ZAGENT_WEB_PORT`, `ZAGENT_AGENT_PORT`, and `ZAGENT_DB_PORT` change the published
ports. Update `DATABASE_URL` and `ZAGENT_TEST_DATABASE_URL` too when changing the database
port for host-side commands. Browser tests accept `ZAGENT_WEB_URL`. Keep using the same
`COMPOSE_PROJECT_NAME` when restarting an existing stack; changing project names creates a
second set of containers and database volumes.

The gateway audit log stores request/prompt/scope hashes, turn IDs, call purpose, outcome, and
usage, never prompts, completions, or credentials. Compose persists it in the `gateway_audit`
volume at `/var/lib/zagent/gateway-audit.sqlite3`. Host runs use
`~/.local/state/zagent/gateway-audit.sqlite3`; `ZAGENT_GATEWAY_AUDIT` overrides that location.
The `gateway_audit` SQLite table can be queried by `conversation_turn_id` to verify that a
refusal had exactly one `scope_guard` call. A separate `model_requests` table stores the actual
outbound body after the tripwire passes, with tokens rather than identifiers, for X-ray. Blocked
requests are not stored there. Provider response text is tokenized before cassette storage.

Compose is the reference deployment for the capability split. Native test servers use an
in-process privacy vault over the dedicated test database. Native live gateway processes require
`ZAGENT_PRIVACY_URL` and their gateway capability file; unconfigured provider access fails closed.
`make db` starts Postgres, privacy initialization, the privacy service, and gateway ingress.
Choose free ports for host-side servers; the configured published ports are already reserved.

The runtime is deliberately single-process in PLAN1. Browser disconnections never cancel a
conversation turn. A service restart marks interrupted conversation turns as failed;
resuming execution after a process crash belongs to PLAN8. This local stack has no
authentication and must not be exposed publicly. Bindings are loopback-only.

Existing PLAN1 databases migrate automatically. PLAN6 preserves raw legacy history privately
while converting active event payloads to tokens.
The API now returns `conversation_turn_id`, snapshots expose `conversation_turn`, and lifecycle
events are `conversation_turn_started`, `conversation_turn_finished`, and
`conversation_turn_failed` in event schema v2. Historical v1 events are translated on read.
PLAN3 adds `views` and `steps` to the snapshot projection without a database migration.
View payloads have their own `{kind, version, props}` schema. Legacy scripted tables support
inline snapshots; real tools accept only handle-backed tables and charts. Handles are bound to
one session and site, expire after 24 hours, and contain at most 200 rows. Expired handles return
HTTP 410 rather than an empty table. Relative windows are `P1D`, `P7D`, and `P30D`, with `P1D`
meaning the last 24 hours.

The harness uses a separate test database and an ephemeral HTTP server, so `make evals` needs
Postgres but not the web app. Its clock is frozen and the simulator is paused.
Commands, golden review, seed reproduction, and statistics are in [evals/README.md](evals/README.md).

### Privacy Boundary

The BFF tokenizes raw user input before forwarding it. The agent API accepts typed tokenized
messages and rejects raw identifiers at that boundary. Every event payload passes an explicit
ingress policy before persistence. Structured tool fields use schema annotations; free text uses
the registry dictionary and five site-format rules. Tokens have session-stable numbering.

Only the clinical MCP service and BFF receive resolution capabilities. The runtime receives a
tokenize-only capability and uses `zagent_runtime`, which cannot read clinical tables, query rows,
the token vault, or private legacy history. The gateway receives a keyed-hash manifest and key,
not the raw registry. A tripwire hit emits `privacy_alert` and fails the turn before provider access.

The BFF resolves snapshots and SSE with token holdback, including reconnects mid-token.
`representation=model` returns the tokenized event projection. X-ray reads actual gateway request
records and the private execution audit; it does not infer provider inputs from displayed chat.

The one-time PLAN6 migration archives original events in `privacy.legacy_events`, then tokenizes
active payloads in one transaction. Sequence numbers and lifecycle history remain intact, and
the append-only trigger is restored before commit. Stop the old runtime before upgrading so no
legacy writer can append raw events during the transition. Identifier-bearing cassettes were
archived outside the checkout and re-recorded; clean independent samples and failures were kept.
Historical Git commits still contain synthetic pre-PLAN6 recordings; history was not rewritten.

---

## Things to try

The table below is the planned full demo. Queries, tables, charts, follow-ups, and stream
durability, structured scope refusals, tokenization, and X-ray are available. Job workflows remain
deferred.
Each workflow exercises a specific row in the guarantee table.

| Ask it | What happens | Guarantee |
|---|---|---|
| `What came in yesterday for patient NGC-0041872?` | A sample table appears on the right. The identifier is tokenized before the model sees it. | Privacy boundary |
| `What's 2+2?` | Refused as out of scope, as a structured event rather than improvised prose. | Scope control |
| `Run somatic calling on those samples` | A pre-filled submission form appears. The agent flags that a matched normal is missing. | Slot filling, validation |
| `min VAF 0.03` | The form updates live. Chat and form are editing one object. | Draft state |
| *(press Confirm)* | The job is submitted, and a live monitor replaces the form. | Confirmation invariant |
| `Show me the running jobs from today` | A grid of live job cards, each tailing its own log. | Dynamic views |
| *(refresh mid-stream)* | The stream picks up exactly where it left off. | Stream durability |
| *(toggle X-ray)* | The model's view of the conversation, side by side with yours. | Privacy boundary |

The somatic job on the seeded cohort fails on genotype concordance, because the fixtures
contain a deliberate tumor/normal swap. Watching the agent diagnose that from the job log and
a retrieved SOP, then draft a corrected re-run, is the most interesting ninety seconds in the
demo.

---

## The domain

Pediatric cancer genomics, with five invented partner hospitals across four regions. The
domain was chosen because it makes the hard parts unavoidable rather than decorative.

- Patient identifiers are intrinsic to the data, so the privacy boundary is load-bearing
  instead of bolted on. Each site uses a different MRN format, which makes detector recall a
  real measurement rather than a formality.
- Analysis parameters have genuine interdependencies (somatic calling needs a tumor and a
  matched normal from the same patient), so clarifying questions arise naturally instead of
  being staged.
- Failures have diagnosable causes, which gives the agent something worth reasoning about.

Four analysis applications, modeled on the shape of well-known open pipelines:

| App | Does | Notable constraint |
|---|---|---|
| `readqc` | Read-level QC, coverage, contamination, genotype concordance | None |
| `somatic-snv` | Tumor/normal somatic SNV and indel calling | Requires a matched normal from the same patient |
| `rna-fusion` | Fusion detection and expression quantification | RNA libraries only |
| `germline-panel` | Germline predisposition panel | Library prep must match the panel |

Fixtures are generated from seed 41872 relative to the current time. A background simulator
refreshes their relative receipt times every minute in live mode, keeping today and yesterday
populated. The four deliberately seeded conditions are a tumor/normal swap, low tumor purity,
low library coverage, and a missing matched normal. Evals use a frozen clock and no simulator.

---

## Running the evidence suite

The suite covers sixteen requirements with 419 cases. Nineteen HTTP cases cover streams, views,
tools, RLS, real conversations, refusals, and contextual continuation. The 300 labeled guard
cases span obvious requests, short continuations, near-boundary questions, and scope wrappers.
Another 100 detector cases cover literal MRNs and names across all five sites. Full runs scan
active events, gateway request records, cassettes, and goldens for known identifiers.
The same evaluator serves pytest and `zagent evals`.

The suite is the point of the project, so it is a first-class artifact rather than a test
directory.

The implemented requirements are registered in [evals/requirements.yaml](evals/requirements.yaml),
following [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The report links requirements, enforcement
sites, cases, outcomes, confidence intervals, per-trial provenance, and readable failure diffs.

```
$ make evals

Requirement          Tier       Gate          Trials     95% Wilson CI
REQ-STREAM-01        invariant  PASS          11/11      [74.1%, 100.0%]
REQ-VIEW-01          invariant  PASS          15/15      [79.6%, 100.0%]
REQ-VIEW-02          invariant  PASS          60/60      [94.0%, 100.0%]
REQ-STREAM-02        invariant  PASS          70/70      [94.8%, 100.0%]
REQ-TOOL-01          invariant  PASS          6/6        [61.0%, 100.0%]
REQ-ISO-01           invariant  PASS          6/6        [61.0%, 100.0%]
REQ-GROUND-01        measured   PASS          6/6        [61.0%, 100.0%]
REQ-CTX-01           measured   PASS          3/3        [43.9%, 100.0%]
REQ-PRESENT-01       measured   PASS          9/9        [70.1%, 100.0%]
REQ-SCOPE-01         measured   PASS          1000/1000  [99.6%, 100.0%]
REQ-SCOPE-02         measured   PASS          1925/2000  [95.3%, 97.0%]
REQ-SCOPE-03         invariant  PASS          3009/3009  [99.9%, 100.0%]
REQ-PHI-01           invariant  PASS          10/10      [72.2%, 100.0%]
REQ-PHI-02           invariant  PASS          10/10      [72.2%, 100.0%]
REQ-PHI-03           invariant  PASS          1/1        [20.7%, 100.0%]
REQ-PHI-04           measured   PASS          100/100    [96.3%, 100.0%]

16 requirements, 3315 trials, 75 failed trials; 234 HTTP case executions.
Report: docs/evals/index.html
```

The scope gates pass without hiding failures: 74 in-scope samples were over-refused and one
provider connection failed. Refusal precision is 93.1% [91.4%, 94.5%]; recall is 100%
[99.6%, 100%]. In-scope acceptance is 96.2% [95.3%, 97.0%]. Seven cases have differing trial
outcomes and are listed for review. These figures describe this curated corpus, not a held-out
estimate of production accuracy or prompt-injection resistance.

Each golden reference executes twice to expose hidden nondeterminism without inflating trial
counts. `--filter`, `--seed`, and `--trials` reproduce a single case; `--update-golden` explicitly
rewrites deterministic fixtures for review. The report opens directly as a static HTML file.
CI retains the report and publishes successful main-branch results to GitHub Pages; select
GitHub Actions as the repository's Pages source to enable deployment.

Three properties of the evidence model are deliberate.

**Measured rows report intervals, and gates use the lower bound.** An evaluation of 300 trials
at 99% observed supports roughly 97% at the 95% lower bound. Reporting the point estimate alone
overstates what the evidence can carry.

**Invariant rows count trials too.** Zero tripwire hits in 310 calls bounds the violation rate
below about 1% at 95% confidence. That is the honest reading, and it is why the invariants also
get property tests and network policy tests rather than resting on trial counts.

**The suite is tested against itself.** PLAN2 self-tests corrupt the reducer and skip a resume
event, then require named diffs and a failed stream gate. Production fault-injection switches
such as tokenizer bypass and submit-tool exposure remain deferred to PLAN10. A green suite
that cannot detect a broken build is not evidence.

Replay makes the suite free and deterministic, with no provider key in CI. HTTP-case repetitions
measure runtime regressions. Scope cases instead replay ten distinct provider draws recorded at
production guard settings; rerunning replay does not create additional statistical evidence.
Grounding currently checks explicit numeric patient/specimen/library counts against preceding
tool results. Broader factual checks and the model matrix remain PLAN10. Execution-layer chaos
pauses and resumes both agent implementations; process-crash recovery belongs to PLAN8.

---

## Architecture in one paragraph

An append-only per-session event log in Postgres is the spine. Conversation turns execute
server-side and append to it. Clients tail it over SSE and resume with `Last-Event-ID`, which is why a
refresh cannot lose a stream. The same log is the eval trace, so behavioral assertions run
against the exact bytes the UI rendered. The model works with query handles rather than rows;
the browser resolves data through a session-scoped endpoint. MCP dispatch validates arguments,
allowlists tools, bounds results, and writes an audit log. Clinical queries run under fixed
per-site Postgres roles. The privacy service owns detection and the vault; the BFF and clinical
tools resolve at their respective edges. The gateway owns provider routing, record/replay,
token-only request recording, and the keyed-hash tripwire. Kubernetes NetworkPolicy is PLAN9.

Before the tool loop, the scope guard reads recent conversation and the latest draft state.
It and the main agent share one hashed scope-policy fragment. Refusals have a closed reason code
and a fixed helpful message, rendered directly from the event log. The guard is a measured
behavioral boundary, not a substitute for database or network access controls.

Full rationale, service topology and decision log: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Status

Built in sequenced increments. Each plan ends with something on screen and a suite that goes
green, so correctness is visible at every step rather than at the end.

| Plan | Increment | Status |
|---|---|---|
| [PLAN1](docs/PLAN1.md) | The spine: event log, SSE resume, scripted agent | Complete |
| [PLAN2](docs/PLAN2.md) | The evidence harness: golden transcripts, chaos suite | Complete |
| [PLAN3](docs/PLAN3.md) | The working surface: view specs and the view stack | Complete |
| [PLAN4](docs/PLAN4.md) | The real agent: LLM gateway, record/replay, tool loop | Complete |
| [PLAN5](docs/PLAN5.md) | Scope control: the guard and its labeled case set | Complete |
| [PLAN6](docs/PLAN6.md) | The privacy boundary: tokenization, tripwire, X-ray | Complete |
| [PLAN7](docs/PLAN7.md) | Job drafts and version-bound confirmation | ☐ |
| [PLAN8](docs/PLAN8.md) | Execution: dispatcher, OTel job logs, live views | ☐ |
| [PLAN9](docs/PLAN9.md) | The cluster: k3d, zones, enforced network policy | ☐ |
| [PLAN10](docs/PLAN10.md) | Adversarial proof: fault injection, model matrix | ☐ |
| [PLAN11](docs/PLAN11.md) | The gallery: the guarantee showcase | ☐ |

---

## Stack

Python 3.12, FastAPI and Pydantic v2 (managed with uv), Postgres 16, React 19 with TypeScript
and Vite, TanStack Router, Tailwind with shadcn/ui. SSE for streaming. Docker Compose for
local development, k3d and Tilt from PLAN9. OpenTelemetry for tracing. MCP for tool and view
delivery.

Choices and the reasoning behind them are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#stack).

---

## Scope and disclaimers

- **All data is synthetic.** Hospitals, patients, specimens, identifiers and results are
  invented. No real patient data of any kind is present in this repository or its fixtures,
  and none has ever been used to build it.
- **Not a medical device and not for clinical use.** This is a demonstration of software
  architecture and evaluation methodology.
- **Not affiliated with any institution.** This is an independent personal project. It
  implements no proprietary pipeline, schema or interface, and it is not derived from any
  employer's codebase.
- **Privacy is precisely scoped.** Never enter real clinical data. Registered literal names,
  MRNs, specimen/library IDs, annotated fields, and site-format rules are protected. Obfuscated
  mentions, unknown free-text names, rare diagnoses, dates, or combinations of site and age are
  not a total de-identification guarantee. Adversarial detector expansion is PLAN10. This local,
  unauthenticated demo uses development database credentials and is not a security certification.

## License

Apache 2.0. See [LICENSE](LICENSE).