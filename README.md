# Zagent

**An auditable LLM agent for clinical genomics operations.**

[![evals](https://img.shields.io/badge/evals-see%20report-blue)](https://w9.github.io/zagent/evals/)
[![replay CI](https://github.com/w9/zagent/actions/workflows/plan1.yml/badge.svg)](https://github.com/w9/zagent/actions/workflows/plan1.yml)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

Most agent demos show a happy path. Zagent is built to answer the question a stakeholder
actually asks after the demo: **how do you know it behaves that way every time?**

It is a working agent over a synthetic pediatric genomics platform. You can ask it about
samples, start analysis jobs, and watch them run. It refuses off-topic requests. Patient
identifiers never reach the model provider. And every one of those claims ships with
machine-checked evidence, regenerated on every commit.

> **Synthetic data only.** Every hospital, patient, sample and result in this repository is
> invented. See [Scope and disclaimers](#scope-and-disclaimers).

**Implemented: [PLAN1](docs/PLAN1.md), [PLAN2](docs/PLAN2.md), and [PLAN3](docs/PLAN3.md).**
The app has a Postgres event log, a scripted background agent, and a resumable three-panel
client with schema-validated tables, view history, and collapsible step markers. A public-HTTP
evidence harness adds golden transcripts, 90 seeded chaos trials, statistics, and a traceability
report. Domain workflows, LLMs, and the privacy boundary remain roadmap capabilities. No model
or clinical system is called in these increments.

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

| Property | Tier | Enforced by | Evidence |
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

Prerequisites: Docker with Docker Compose v2. PLAN1 runs a deterministic YAML script, needs
no API key, and makes no external calls at runtime. Images and dependencies download on the
first build. For local tests and the CLI, install uv, Python 3.12, and Node.js 24 or newer.

```bash
git clone https://github.com/w9/zagent && cd zagent
make up            # Postgres 16, agent, web; migrates and seeds an empty session.
# Open http://localhost:5173
```

Send any message: text streams while the working surface receives two synthetic tables.
Previous/next controls and the history menu let you revisit earlier views. Navigating back pins
that view while new ones arrive; selecting the latest resumes following. Refresh keeps the
chosen view through the session URL. On smaller screens, tabs switch between chat and the surface.

Step markers start collapsed and expand to show their detail. `/fail` exercises an agent failure;
`/invalid-view` rejects a malformed table, fails the conversation turn, and leaves the existing
surface unchanged. Reopening `/` restores the last session in that browser.

```bash
make test          # Python tests, 90 seeded trials, client/component tests, build, lint.
make evals         # The shared evidence harness; writes docs/evals/index.html.
make chaos         # 90 interruptions across all cases; checks normal references too.
make report        # Render stored results; evaluates first if none exist.
make install       # Local Python and JavaScript dependencies.
cd apps/web && npx playwright install chromium && cd ../..
make browser       # Browser acceptance tests against the running app.
uv run zagent transcript <session_id>
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
port for host-side commands. Browser tests accept `ZAGENT_WEB_URL`.

For hot-reload development, run `make db`, `uv run uvicorn zagent.app:app --reload`, and
`npm --prefix apps/web run dev` in separate terminals, with the Compose agent and web stopped.
The Vite proxy uses `AGENT_URL` (default `http://127.0.0.1:8000`).

The runtime is deliberately single-process in PLAN1. Browser disconnections never cancel a
conversation turn. A service restart marks interrupted conversation turns as failed;
resuming execution after a process crash belongs to PLAN8. This local stack has no
authentication and must not be exposed publicly. Bindings are loopback-only.

Existing PLAN1 databases migrate automatically without rewriting stored event history.
The API now returns `conversation_turn_id`, snapshots expose `conversation_turn`, and lifecycle
events are `conversation_turn_started`, `conversation_turn_finished`, and
`conversation_turn_failed` in event schema v2. Historical v1 events are translated on read.
PLAN3 adds `views` and `steps` to the snapshot projection without a database migration.
View payloads have their own `{kind, version, props}` schema; table v1 supports inline rows
or a future handle source. No handle-fetching backend is implemented yet.

Live providers and clinical cohort seeding belong to later plans. The harness uses a separate
test database and an ephemeral HTTP server, so `make evals` needs Postgres but not the web app.
Commands, golden review, seed reproduction, and statistics are in [evals/README.md](evals/README.md).

---

## Things to try

The table below is the planned full demo. Stream durability and scripted tables are available;
the domain queries, live jobs, privacy features, and model behavior remain deferred.
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

Fixtures are generated relative to the current time and a background simulator keeps samples
arriving, so "yesterday" and "running today" always return something. The clock is frozen for
evals.

---

## Running the evidence suite

The suite covers two stream requirements and two view requirements with nine cases: the five
original conversation scenarios plus two-table views, empty data, invalid views after a valid
surface, and invalid views on a fresh session. The same evaluator serves pytest and `zagent evals`.

The suite is the point of the project, so it is a first-class artifact rather than a test
directory.

The implemented requirements are registered in [evals/requirements.yaml](evals/requirements.yaml),
following [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The report links requirements, enforcement
sites, cases, outcomes, confidence intervals, per-trial provenance, and readable failure diffs.

```
$ make evals

Requirement          Tier       Gate          Trials     95% Wilson CI
REQ-STREAM-01        invariant  PASS          5/5        [56.6%, 100.0%]
REQ-VIEW-01          invariant  PASS          9/9        [70.1%, 100.0%]
REQ-VIEW-02          invariant  PASS          40/40      [91.2%, 100.0%]
REQ-STREAM-02        invariant  PASS          50/50      [92.9%, 100.0%]

4 requirements, 99 trials, 0 failed trials; 108 HTTP case executions.
Report: docs/evals/index.html
```

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

Replay mode makes all of this free and deterministic. Pull requests run the full suite with no
provider key. Live-provider and model-matrix evaluation remains deferred. Execution-layer chaos
currently pauses and resumes scripted turns; process-crash recovery belongs to PLAN8.

---

## Architecture in one paragraph

An append-only per-session event log in Postgres is the spine. Conversation turns execute
server-side and append to it. Clients tail it over SSE and resume with `Last-Event-ID`, which is why a
refresh cannot lose a stream. The same log is the eval trace, so behavioral assertions run
against the exact bytes the UI rendered. Everything crossing into model context is tokenized
first, and the model works with query handles rather than rows, so the agent zone holds no
identifiers at all. Services are split along that boundary and the split is enforced by
NetworkPolicy, not convention.

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
| [PLAN4](docs/PLAN4.md) | The real agent: LLM gateway, record/replay, tool loop | ☐ |
| [PLAN5](docs/PLAN5.md) | Scope control: the guard and its labeled case set | ☐ |
| [PLAN6](docs/PLAN6.md) | The privacy boundary: tokenization, tripwire, X-ray | ☐ |
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
- **Privacy claims are scoped.** The invariants hold for identifiers the rule set matches.
  Detector recall on free text is a measured quantity, reported as such. Nothing here is a
  compliance certification.

## License

Apache 2.0. See [LICENSE](LICENSE).