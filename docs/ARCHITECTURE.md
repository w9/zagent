# Architecture

This document records the decisions that are expensive to reverse and the reasoning behind
them. It deliberately stops short of implementation detail: where a choice is local to one
module and cheap to change later, it is the implementer's call, not this document's.

**Implementation status:** PLAN1 through PLAN6 are implemented. The local stack tokenizes at
ingress, resolves only at clinical tool/display edges, restricts runtime database credentials,
and checks outbound requests with a keyed-hash tripwire. X-ray shows actual recorded model
requests. Jobs, knowledge retrieval, and Kubernetes NetworkPolicy remain later plans; this local
development deployment is not a production security certification.

**Contents**

1. [Guiding constraints](#1-guiding-constraints)
2. [The two-tier guarantee model](#2-the-two-tier-guarantee-model)
3. [The event log is the spine](#3-the-event-log-is-the-spine)
4. [Conversation turns are decoupled from connections](#4-conversation-turns-are-decoupled-from-connections)
5. [The agent is an interface](#5-the-agent-is-an-interface)
6. [Zones and the privacy boundary](#6-zones-and-the-privacy-boundary)
7. [Handles, not rows](#7-handles-not-rows)
8. [Views are declarative specs](#8-views-are-declarative-specs)
9. [Drafts and confirmation](#9-drafts-and-confirmation)
10. [Job execution](#10-job-execution)
11. [Gateways](#11-gateways)
12. [Knowledge base](#12-knowledge-base)
13. [Evidence architecture](#13-evidence-architecture)
14. [Service topology](#14-service-topology)
15. [Stack](#15-stack)
16. [Non-goals](#16-non-goals)
17. [Requirement register](#17-requirement-register)
18. [Decision log](#18-decision-log)

---

## 1. Guiding constraints

Three constraints shaped nearly every decision below.

**Push guarantees out of the model and into infrastructure.** Anything a deterministic
mechanism can enforce should be enforced there, because a closed door beats a high pass rate.
What remains model-dependent gets measured honestly rather than asserted.

**Correctness must be visible at every increment.** The project is built as a sequence of
shippable steps, each ending with something rendered on screen and a suite that goes green.
This ruled out several architectures that are only testable once fully assembled.

**Evidence must be cheap to produce.** If regenerating the report costs money or flakes, it
stops happening. Determinism and replay are therefore architectural requirements, not testing
conveniences.

---

## 2. The two-tier guarantee model

Every behavioral requirement is classified as an **invariant** or a **measured property**, and
the classification drives both the implementation and the reporting.

An **invariant** is enforced by construction. The mechanism is a type boundary, an absent
capability, a database policy, or a network rule. Its evidence is a property test plus, where
applicable, a fault-injection test proving the mechanism is actually load-bearing. Invariants
are reported as pass/fail.

A **measured property** depends on model judgment. Its evidence is a pass rate over k trials on
a labeled case set, reported with a Wilson confidence interval, gated on the lower bound.

The distinction is not cosmetic. Two examples of where it bites:

- Removing the job-submission tool from the model's schema makes unauthorized submission
  impossible. But nothing prevents the model from *claiming* it submitted a job. The first is
  an invariant, the second is a measured groundedness property, and a system that reports only
  the first is misleading.
- Tokenizing identifiers before the LLM gateway is an invariant for identifiers the rule set
  matches. Whether the rule set matches a given obfuscated mention is a measured detector
  recall property. Collapsing these into "PHI is protected" is the kind of overclaim this
  architecture exists to avoid.

The [requirement register](#17-requirement-register) is the authoritative classification.

---

## 3. The event log is the spine

A single append-only, per-session event log in Postgres is the system's source of truth for
everything a session did.

A **conversation turn** begins with one user message and includes the agent's processing,
model/tool steps, and response until completion or failure. A session contains many conversation
turns, with at most one active at a time. A **job run** is a separate analysis execution: it can
outlive the conversation turn that prepared its draft and is not the unit of chat streaming.

```
events(session_id, seq, conversation_turn_id, schema_version, type, payload, created_at)
  primary key (session_id, seq)
```

Lifecycle events are `conversation_turn_started`, `conversation_turn_finished`, and
`conversation_turn_failed`. The current event schema is v2. Original v1 events remain immutable
in storage and are translated to the current vocabulary on read; the identifier column is
renamed by a migration, with sequence numbers and payloads preserved.

`seq` is monotonic per session, allocated by incrementing a counter column on the session row.
That row lock serializes appends within a session, which is the desired behavior anyway, and it
avoids the gap and out-of-order-visibility problems a shared sequence introduces for a reader
that must not skip.

Everything else is a projection of this log: the rendered transcript, the right panel's view
stack, the session list, and the eval trace. Three consequences follow, and they are the reason
for the design.

**Stream resume is a read.** A reconnecting client asks for events after a sequence number.
There is no special recovery path to get subtly wrong.

**View history is free.** Back and forward navigation on the working surface is movement
through a filtered projection, not separately managed UI state.

**Behavioral assertions run against the bytes the UI rendered.** The eval harness reads the
same log the client reads. There is no separate instrumentation path that can drift from
production behavior, which is the failure mode that makes most agent test suites decorative.

Two design rules protect this. First, anything worth asserting about must be a structured
event: refusals go through a `refuse(reason)` tool rather than improvised prose, drafts are
state, views are specs. This converts most behavioral checks from fuzzy judgment into
deterministic assertion. Second, the event schema is versioned, and the client reducer must
support removal (`message_dropped`) from the start, even before anything emits it. A resumed
conversation turn that re-executes an interrupted model call needs to retract a partial
message, and an append-only reducer is a rewrite at that point.

Token deltas are coalesced on a short timer before being appended, so streaming does not mean
one row per token.

---

## 4. Conversation turns are decoupled from connections

Posting a message starts a background conversation turn and returns immediately. It does not
return the stream. The client is separately subscribed to the session's event feed and sees
the conversation turn's output arrive there.

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Web BFF
    participant R as Agent runtime
    participant L as Event log
    C->>W: GET /sessions/:id/events?from=N (SSE, held open)
    C->>W: POST /sessions/:id/messages
    W->>L: append user_message
    W->>R: start conversation turn (background)
    W-->>C: 202 Accepted
    loop while conversation turn is active
        R->>L: append events
        L-->>W: NOTIFY
        W-->>C: SSE frames (id = seq)
    end
    Note over C,W: connection drops
    C->>W: GET /sessions/:id/events (Last-Event-ID: seq)
    W-->>C: replay from seq+1, then continue tailing
```

This is the single most important structural decision in the project, and the one most
expensive to retrofit. An architecture where the POST response *is* the stream ties
conversation turn lifetime to connection lifetime, which means a refresh kills work in progress and every
durability guarantee becomes a special case. Building it the other way costs almost nothing on
day one.

It also makes multi-tab and multi-device viewing fall out for free, since every viewer uses the
same tail-the-log code path.

SSE was chosen over WebSockets because `Last-Event-ID` is exactly the resume primitive needed
and the protocol is otherwise plain HTTP. The known cost is that `EventSource` cannot set
request headers, so authentication rides a cookie or the client moves to a streaming `fetch`.

---

## 5. The agent is an interface

```
Agent.run_turn(session, emit) -> None
```

Two implementations share this interface, and nothing else in the runtime knows which
one is running:

| Implementation | Purpose |
|---|---|
| `ScriptedAgent` | A canned event sequence. Deterministic, no provider, no key. |
| `LlmAgent` | The real loop, with replay, record, or live selected inside the model gateway. |

This is what makes the build order possible. The event log, the streaming layer, the entire
front end and the whole evidence harness are built and proven against `ScriptedAgent`, before
an LLM is in the picture. When the real loop arrives, the existing goldens are the regression
test for it.

It is also what makes CI free and deterministic. Pull requests run `LlmAgent` with gateway
replay, alongside retained scripted transport fixtures. There is no separate replay loop or
harness-level provider mock. Nightly evaluations will use the same agent across configured
model routes, and the resulting drift is a reviewable diff.

---

## 6. Zones and the privacy boundary

The system is split into two zones, and the split is the primary security control.

```mermaid
graph TB
    subgraph clinical["Clinical zone (holds identifiers)"]
        WEB[Web BFF]
        PRIV[Privacy service<br/>token vault]
        TOOLS[Tools gateway<br/>MCP client + PEP]
        DB[(Postgres<br/>clinical tables, RLS)]
        DISP[Dispatcher]
        JOBS[Job pods]
    end
    subgraph agent["Agent zone (holds no identifiers)"]
        RT[Agent runtime]
        LLM[LLM gateway<br/>+ egress tripwire]
        EV[Eval runner]
        LOG[(Postgres<br/>event log)]
    end
    KB[Knowledge base<br/>read-only index]
    EXT((Model provider))
    WEB <--> RT
    WEB <--> PRIV
    RT <--> LLM
    RT <--> TOOLS
    TOOLS <--> PRIV
    TOOLS <--> DB
    TOOLS <--> KB
    DISP --> JOBS
    DISP <--> DB
    LLM --> EXT
```

**Identifiers are tokenized at ingress and resolved only at the edges that need real values:**
the tools gateway, which must execute against real data, and the web stream, which must display
real values to an authorized human. Everything between, including the agent runtime, the event
log and the LLM gateway, holds tokens only.

This is deliberately the PCI tokenization pattern rather than a filter in front of the model
call. The difference matters: a filter protects one call site, while tokenization at ingress
takes the entire agent zone out of scope, which means the invariant can be verified by scanning
everything the agent zone ever stored rather than by auditing every call path.

Every path into model context counts as an ingress. That includes user text, tool results, job
logs, retrieved documents and interaction events coming back from rendered views. Missing one
of these is the most likely way to break the invariant, which is why the boundary is a typed
one: values are `Raw<T>` or `Tokenized<T>`, and only an explicit tokenize step converts.

Three layers back the invariant up:

1. **The type boundary** prevents it at compile or validation time.
2. **NetworkPolicy** denies the agent zone any route to clinical data, and grants internet
   egress to the LLM gateway alone. This is why the project moves to Kubernetes at all
   ([PLAN9](PLAN9.md)): the boundary should be enforced, not documented.
3. **An egress tripwire** in the LLM gateway matches keyed hashes of every known identifier on
   every outbound request and fails the request loudly. The gateway holds hashes, never
   identifiers, so the tripwire itself is not a leak.

Detokenization on the display path needs a small holdback buffer, because a token can straddle
two streamed chunks.

Two supporting decisions reduce how often identifiers are needed at all. Tools accept relative
time windows rather than dates, because dates are quasi-identifiers and a relative window is
what the user meant anyway. And cross-site isolation is enforced by Postgres row-level security
rather than by query construction, so it holds regardless of what the agent asks for.

---

## 7. Handles, not rows

Data-returning tools return a query handle, a row count and a schema. They do not return rows.
View-pushing tools take a handle. The model composes a view over data it never sees.

This began as a privacy measure and turned out to be the better design regardless.

- It bounds context growth. A thousand-row result costs the same context as a ten-row one.
- It keeps views live. A view bound to a handle re-reads on render, so a job monitor reflects
  current state instead of a snapshot from when the model spoke.
- It removes the largest class of hallucination. The model cannot misreport a value it was
  never given.

The cost is that the model cannot reason over result contents. Where that is genuinely needed,
a tool returns an explicit aggregate (a count, a distribution, a named summary) rather than the
underlying rows. In practice this has been sufficient, and it is a useful forcing function: it
surfaces which questions actually require data in context and which were only convenient.

---

## 8. Views are declarative specs

The working surface renders views described by `{kind, version, props}`, validated against a
JSON Schema at the boundary. The model never emits markup or code.

There are two sources of views, and they have different owners.

**Tool-owned views** are shipped by the tool that produces them: a job card, a submission form,
a log tail. These follow the MCP Apps extension, where a tool declares a `ui://` resource and
the host renders it in a sandboxed frame with JSON-RPC message passing. The jobs MCP server
carries its own job card. This is what makes "connect another MCP server later" a real
capability rather than a slide: a new server brings its own views with it.

**Agent-composed views** are ad hoc tables and charts assembled by the model from a small
registry of kinds. Charts use a Vega-Lite subset, so the spec is portable and validatable
rather than bespoke.

The registry is intentionally small and grows one kind at a time. A large view vocabulary
introduced early is untestable surface area.

PLAN3 implements only table v1. One JSON Schema under `services/agent/zagent/view_schemas/`
is used on both sides of the HTTP boundary, with cell/column consistency checks alongside it.
`view_pushed` carries a stable `view_id` and a validated spec. Invalid specs fail the conversation
turn before append; earlier views remain intact. Rows are text/scalars, never executable markup.

View and step stacks are event projections in both Python and TypeScript. The browser stores
only a selected view ID in the URL; it never stores a separate copy of the stack. No selected
ID means follow the newest view. Navigation to an older ID pins it across refresh and future
pushes; selecting the head resumes following. Compact screens expose chat and surface as tabs.

The renderer registry discovers versioned components independently of the panel and reducer.
Table props allow inline rows or an injected handle source, but live handle resolution remains
PLAN4. Schema, prefix-replay, component-snapshot, and seeded reconnect evidence cover the current
table contract. Step markers are collapsed disclosures over started/finished step events.

---

## 9. Drafts and confirmation

A job draft is a persisted, versioned object. Chat and the form in the right panel are two
editors over the same object, which is what collapses the two interaction styles in the
original concept into one state machine: a natural-language correction and a form edit are the
same mutation.

Confirmation carries the version hash of the draft the user was looking at. If the agent
mutated the draft after the card rendered, the confirmation is rejected and the user is shown
what changed.

This is the mechanism behind the confirmation invariant, and it is stronger than the obvious
implementation. Simply requiring a button click leaves a race in which the agent alters
parameters between render and click. Binding the confirmation to a specific version means the
user always confirms exactly the thing they saw. The model has no submit tool at all, only
draft mutation, so submission is structurally a human action.

---

## 10. Job execution

The queue lives in Postgres. Rows are claimed with `SKIP LOCKED`, and enqueueing happens in the
same transaction as the job row so the two cannot diverge. A dedicated queue broker would add
an operational component and a consistency boundary for no benefit at this scale.

A dispatcher claims queue rows and creates Kubernetes Jobs from a catalog entry: image,
command, and a JSON Schema for parameters. Retries, backoff and cleanup come from the Job spec
rather than from application code. Jobs emit progress as OTel-compatible JSONL on stdout, which
the dispatcher tails into the database and the observability pipeline.

Job runs are single-step and have no sub-workflow, so they need no workflow engine. Durable
execution also matters within a *conversation turn*, which can contain multiple model and tool
steps. That is served by journaling the conversation turn into the same event log rather than
by adding Temporal. Workflows that wait on a human span conversation turns; the wait between
turns lives in persisted session and draft state.

---

## 11. Gateways

**The LLM gateway** is a thin in-house service rather than an off-the-shelf proxy, for one
reason: record and replay keyed on a normalized request hash is a hard requirement of the
evidence architecture, and it is easier to own than to bolt on. It also holds per-request model
routing for the nightly matrix, and the egress tripwire. It is the only component with internet
egress.

**The tools gateway** is an MCP client and, at the same time, the policy enforcement point. All
of the following happen there and nowhere else: tool allowlisting, argument schema validation,
token resolution, result tokenization, and audit logging. Concentrating policy in one place is
what makes it auditable.

Results from third-party MCP servers are treated as untrusted content on the same footing as
user input. They are tokenized, and they are never interpreted as instructions.

---

## 12. Knowledge base

An immutable SQLite file with an FTS5 index, built in CI from versioned Markdown sources and
baked into the image. It is served read-only over MCP.

Immutability buys determinism: a KB version is a build artifact, so a retrieval result is
reproducible and the eval report can pin it. Indexing at line granularity lets answers cite
line ranges, which turns groundedness from a judgment call into a deterministic check: either
the cited span contains the claim or it does not.

---

## 13. Evidence architecture

**Requirements are code.** Each has an ID, a tier, a threshold and linked cases. The report is
a traceability matrix. When a requirement turns out to be ambiguous, the resolution is a new
labeled case, which makes the case set the executable specification.

**Golden transcripts are the primary regression mechanism.** Each case writes a normalized
event log (types plus significant payload fields, with ids and timestamps redacted) to a
checked-in golden file. A behavior change is a reviewable diff. This is the cheapest and
highest-leverage piece of the whole system, which is why it is built second rather than last.

**Cases drive the real HTTP API**, not internals. One runner serves both the test suite and the
`zagent evals` CLI, so there is no second code path that can pass while production fails.

PLAN2 implements this through a local instance of the production HTTP application on an
ephemeral loopback port and a dedicated test database. Each case starts with `POST /sessions`;
evidence comes from SSE plus `GET /snapshot`. Case groups, requirement links, and expected
transcripts live under `evals/`. Golden references execute twice to reject hidden nondeterminism.
Goldens cover projected chat state as well as normalized events, so reducer regressions are
visible. Unknown assertions are configuration errors, not ignored extensions.

**Statistics are reported honestly.** k trials per case at production settings. Wilson intervals
on pass rates, gated on the lower bound. `pass^k` reported separately for properties that must
hold on every attempt. Version comparisons use paired tests, so "regression" is a claim with
support rather than a difference in two numbers.

The PLAN2 scripted fixture accelerates timing and records that exception in provenance; it
does not measure model quality or latency. Its report uses per-case distinct-trial `pass^k`
estimates and exact paired McNemar comparisons. Measured gates require their registered sample
minimum as well as a sufficient Wilson lower bound. Uncovered requirements fail the gate.

**Simulated users** carry hidden goals for multi-turn slot filling, and are scored on whether
the final draft matches the goal. The simulator's model is pinned independently so its drift is
not misread as agent drift.

**The suite is tested against itself.** Fault-injection flags disable each mechanism in turn,
and CI asserts the suite goes red for each. A green suite that cannot detect a broken build is
not evidence.

**Provenance is recorded per result**: model, prompt hash, tool schema hash, KB version, seed,
and commit. Determinism is maintained through an injectable clock, seeded fixtures and a seeded
simulator.

---

## 14. Service topology

| Service | Zone | Responsibility |
|---|---|---|
| Web BFF | Clinical | HTTP and SSE to the browser, display-path detokenization |
| Agent runtime | Agent | Conversation turn execution, the scope guard, conversation turn journaling |
| LLM gateway | Agent | Provider routing, record and replay, egress tripwire. Sole internet egress |
| Tools gateway | Clinical | MCP client and policy enforcement point |
| Privacy service | Clinical | Token vault, detector rule set, tokenize and resolve |
| Dispatcher | Clinical | Claims queue rows, creates Job objects, tails logs |
| Job pods | Clinical | Single-step analysis containers |
| Knowledge base | Neutral | Read-only FTS5 index over versioned docs |
| Eval runner | Agent | Case execution, reporting, publishing |
| Postgres | Split by role | Event log and clinical tables, separated by role and RLS |
| OTel collector plus Tempo | Neutral | Traces, using GenAI semantic conventions |

The web BFF sits in the clinical zone because it performs display detokenization. The agent
runtime sits in the agent zone and never holds a real identifier.

---

## 15. Stack

Choices favor what is already fluent over what is novel, because the interesting parts of this
project are the boundary and the evidence, and neither benefits from stack learning curves.

| Layer | Choice | Reasoning |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, uv | Pydantic gives schema validation at every boundary, which the view specs, tool arguments and event payloads all need |
| Database | Postgres 16 | Event log, queue, clinical tables and RLS in one component |
| Streaming | SSE | `Last-Event-ID` is the exact resume primitive required |
| Frontend | React 19, TypeScript, Vite, TanStack Router, Tailwind, shadcn/ui | Typed view-spec rendering and a small component surface |
| Local dev | Docker Compose, then k3d and Tilt at PLAN9 | Compose keeps early iteration fast. The cluster arrives when there are zones worth separating |
| Evidence | pytest plus an `zagent evals` CLI | One runner, two entry points |
| Tracing | OpenTelemetry, Tempo | Job logs already arrive as OTel JSONL |
| Tools and views | MCP, MCP Apps | Extensibility that is real rather than claimed |

**On Rust:** the one component where a type system materially strengthens a guarantee is the
privacy service, where `Raw<T>` and `Tokenized<T>` can make a boundary violation a compile
error. It is an optional substitution at [PLAN6](PLAN6.md), not a prerequisite.

---

## 16. Non-goals

Stated explicitly, because each was considered and declined.

- **Multi-tenancy and real authentication.** Single-user, with RLS demonstrating the isolation
  mechanism. Auth is orthogonal and adds no architectural insight here.
- **Real analysis pipelines.** Jobs emit realistic telemetry against synthetic inputs. Running
  actual aligners would add hours of compute and nothing to the demonstration.
- **A workflow engine.** Jobs are single-step. See [section 10](#10-job-execution).
- **Model training or fine-tuning.** The subject is agent system design and evaluation.
- **Horizontal scale.** Correct under concurrency, not tuned for throughput. Where the design
  would not scale, the document says so rather than pretending.
- **Compliance certification.** The privacy boundary is a demonstrated architecture, not an
  attested control.

---

## 17. Requirement register

The authoritative list lives in `evals/requirements.yaml` and is the source for the report. The
shape of an entry:

```yaml
- id: REQ-PHI-01
  tier: invariant
  statement: >
    No identifier matched by the detector rule set appears in any request
    leaving the LLM gateway.
  enforced_by:
    - privacy/tokenize.py           # ingress tokenization
    - gateway_llm/tripwire.py       # keyed-hash egress check
    - deploy/policy/agent-zone.yaml # NetworkPolicy
  cases: [PHI-001 .. PHI-062]
  mutations: [tokenizer_off, tripwire_off]

- id: REQ-SCOPE-01
  tier: measured
  statement: Off-topic requests are refused with a structured refusal event.
  threshold: {metric: recall, min_lower_bound: 0.95, trials: 10}
  cases: [SCOPE-001 .. SCOPE-050]
```

Invariants name their enforcement sites and the mutations that must break them. Measured
properties name a metric, a lower-bound gate and a trial count. Both name their cases, which is
how the traceability matrix is generated rather than maintained.

---

## 18. Decision log

| # | Decision | Alternative rejected | Because |
|---|---|---|---|
| 1 | Append-only per-session event log as the single source of truth | Conventional message table plus separate telemetry | One spine gives resume, view history and eval traces from the same bytes |
| 2 | Conversation turns decoupled from connections | POST returns the stream | Connection lifetime must not bound work lifetime |
| 3 | SSE with `Last-Event-ID` | WebSockets | Resume is the primitive needed, and the rest is plain HTTP |
| 4 | Per-session sequence via a session counter row | Global sequence | Readers must not skip, and gaps make that unsafe |
| 5 | Agent as an interface, scripted first | Build against a real provider | Enables the entire front end and harness to be proven before any LLM |
| 6 | Tokenization at ingress | Filter in front of the model call | Removes the whole agent zone from scope, so the invariant is verifiable by scanning storage |
| 7 | Typed raw/tokenized boundary | Runtime checks only | Every ingress path must be covered, and types cover them structurally |
| 8 | Handles instead of rows | Rows in tool results | Bounds context, keeps views live, removes a hallucination class |
| 9 | Declarative view specs | Model-generated markup or code | Validatable, snapshot-testable, safe to render |
| 10 | MCP Apps for tool-owned views | Bespoke view registry only | Third-party servers bring their own views, so extensibility is real |
| 11 | Version-hashed confirmation | Plain confirmation button | Closes the race between render and click |
| 12 | No submit tool exposed to the model | Submit tool plus policy prompt | Makes unauthorized submission structurally impossible |
| 13 | Postgres queue with `SKIP LOCKED` | Dedicated broker | One fewer component, and transactional enqueue with the job row |
| 14 | Kubernetes Jobs for execution | In-process worker pool | Retries, backoff and cleanup come from the platform |
| 15 | Conversation turn journaling in the event log | Temporal or similar | Multi-step conversation turns need durable progress, and the log already is a journal |
| 16 | In-house LLM gateway | Off-the-shelf proxy | Record and replay keyed on request hash is a hard requirement |
| 17 | Immutable SQLite FTS5 knowledge base | Vector database service | Deterministic, pinnable, and line-level citations make groundedness checkable |
| 18 | Golden transcripts as the regression mechanism | Assertion-only tests | Behavior changes become reviewable diffs |
| 19 | Cases drive the public HTTP API | Test internals directly | No second code path that can pass while production fails |
| 20 | Lower-bound gates on measured properties | Point estimates | A point estimate overstates what the trials support |
| 21 | Fault injection as a CI requirement | Trust the suite | A suite that cannot detect a broken build is not evidence |
| 22 | RLS for cross-site isolation | Query-level filtering | Holds regardless of what the agent asks for |
| 23 | Compose first, Kubernetes at PLAN9 | Kubernetes from day one | Early iteration speed, and zones only become real once there are two |