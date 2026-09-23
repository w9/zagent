# PLAN8: Execution and Live Views

**Status:** implemented
**Depends on:** [PLAN7](PLAN7.md)
**Shippable outcome:** confirmed jobs run, the right panel shows live progress and logs, and the
agent diagnoses a failure from a job log and a retrieved SOP.

---

## Goal

Make jobs execute, make the working surface live, and deliver the demo's best moment.

That moment is specific: the seeded tumor/normal swap causes `somatic-snv` to fail on genotype
concordance. The agent reads the job log, retrieves the relevant SOP from the knowledge base,
explains the cause in terms a bioinformatician would use, and drafts a corrected re-run. It shows
tool use, retrieval, grounded reasoning and the draft state machine in one continuous story, on
data where the failure has a real cause rather than a scripted one.

---

## What you can see when it's done

Confirm a job. A live card replaces the form: state, progress, elapsed time, and a tailing log.

Ask "show me the running jobs from today". A grid of live cards, each independently updating.

Click the titled job-card or grid reference in chat to reopen that published view in the working
surface, with its current live state, without starting or resubmitting anything.

Wait for the somatic job to fail. Ask what happened. The agent explains genotype concordance,
cites a line range in the SOP, and offers a re-run with the correct normal.

---

## Scope

**The queue, in Postgres.** Claimed with `SKIP LOCKED`. Enqueue happens in the same transaction as
the job row, so the two cannot diverge. No separate broker.

**The dispatcher.** Claims rows and creates the execution unit. Under Compose that is a container.
From PLAN9 it is a Kubernetes Job created from a catalog entry (image, command, parameter schema),
with retries, backoff and cleanup delegated to the Job spec. Write the dispatcher against an
interface with two implementations so PLAN9 is a substitution.

**Job containers.** Each takes parameters and emits OTel-compatible JSONL on stdout. They do no
real analysis: they read the fixture state, sleep on a realistic schedule, and emit the progress
and outcome the fixtures dictate. The seeded conditions produce their outcomes here.

| Seeded condition | Outcome |
|---|---|
| Tumor/normal swap | `somatic-snv` fails on genotype concordance |
| Low tumor purity | Completes with a warning |
| Low coverage | `readqc` fails |
| Node eviction | One bounded retry under Compose, visible in attempt history; Job-spec policy follows in PLAN9 |
| Long-running job | Runs long enough to watch |

**Log ingestion.** The dispatcher tails stdout, parses the JSONL, tokenizes it (job logs are an
ingress into model context), writes it to the database and forwards spans to the collector.

**Live views.** Two new view kinds, `job_card` and `job_grid`, bound by handle and subscribed to
job state. This is where the handle design from PLAN4 pays off a second time: a view bound to a
handle reflects current state, so a card the agent pushed ten minutes ago is still correct now.

**Chat references for live views.** Reuse PLAN7's receipt-backed chat-to-surface navigation for
`job_card` and `job_grid`, including views supplied by MCP Apps. The host resolves the published
view ID and constructs the navigation target; neither model prose nor an embedded app supplies
an arbitrary destination. Reopening a view resumes its read-only subscriptions, not execution.
Keep the view identity stable as job state changes, and preserve PLAN7's session isolation,
mobile navigation, unavailable-state, and no-mutation behavior.

**MCP Apps.** The jobs tool server ships `job_card` and `job_grid` as its own `ui://` resources
rather than having them live in the web app's registry. This is the increment that makes
"connect another MCP server later" a demonstrated capability instead of a claim: a new server
brings its own views. The host renders them in a sandboxed frame with JSON-RPC message passing.

**The knowledge base.** An immutable SQLite file with an FTS5 index, built in CI from versioned
Markdown SOPs and baked into the image, served read-only over MCP. Line-granularity indexing so
answers cite line ranges, which makes groundedness a deterministic check: either the cited span
contains the claim or it does not.

**Turn journaling.** Now that conversation turns can be long and can wait on job state, add journal-based resume:
a runtime pod that dies mid-turn resumes from the log. This is where `message_dropped` finally
gets emitted, retracting a partial assistant message before the interrupted step re-executes.
The client reducer has supported it since PLAN1 for exactly this moment.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Kubernetes Jobs as the execution unit | PLAN9 |
| Real analysis tooling | not a goal |
| Multi-step workflows, DAGs | not a goal |
| Job priority, quotas, fair scheduling | not a goal |

---

## Key decisions

**No workflow engine.** Jobs are single-step, so retries and cleanup come from the platform. The
genuinely durable process here is the conversation turn, and the event log already is its journal. Adding
Temporal would be a second durability mechanism for the case that does not need one.

**Fake executors that read real fixture state.** The failures must be diagnosable, which means
they must have causes in the data. A job that fails randomly teaches the agent nothing to reason
about and gives the audience nothing to verify.

**Job logs are an ingress.** Easy to miss, and it is also the prompt-injection vector that PLAN10
tests: a job whose log contains "ignore previous instructions". Tokenize and treat as untrusted
content, on the same footing as user input.

**Tool-owned views via MCP Apps.** Slightly more work than adding two kinds to the web registry,
and it is what makes the extensibility story real.

**An immutable knowledge base.** A KB version is a build artifact, so retrieval is reproducible and
the report can pin it. This is what lets groundedness be checked rather than judged.

---

## Definition of done

- [x] A confirmed job runs and its card shows progress, elapsed time and a tailing log.
- [x] `job_grid` shows multiple live jobs, each updating independently.
- [x] Chat references reopen the exact published `job_card` or `job_grid`, including MCP-owned
	views, on desktop and mobile; current state appears without submitting or restarting a job.
- [x] The somatic job fails on genotype concordance from the seeded swap.
- [x] The agent explains the failure and cites a line range in the SOP.
- [x] The agent drafts a corrected re-run, which goes through the PLAN7 confirmation path.
- [x] A job log containing injected instructions does not change agent behavior in the measured cases.
- [x] Job logs contain no known identifiers after ingestion. Corpus scan.
- [x] Killing the runtime mid-turn resumes, retracts the partial message, and completes.
- [x] Killing the dispatcher mid-job does not lose or duplicate the job.
- [x] `job_card` and `job_grid` are served by the jobs MCP server, not the web registry.

## Implementation And Evidence

Migrations 008-011 add the queue, private frozen execution inputs, attempts/logs, live handles,
model checkpoints, and transactional tool receipts. New confirmation writes the job, frozen
selection/parameters, and queue entry in one transaction. Existing PLAN7 pending records remain
preserved and are not silently enqueued: expired historical selections need a fresh reviewed draft.

`JobStore` uses `SKIP LOCKED`, expiring leases, and monotonic lease revisions. `DockerExecutor`
reconciles by deterministic session/job/attempt name plus input fingerprint. A crash after create
reattaches to that unit, and unique attempt/log sequence keys suppress replayed stdout. An
`Executor` protocol also has a native process adapter for tests; Kubernetes remains PLAN9.
Synthetic eviction retries once; a domain failure is terminal. Confirmed inputs do not depend on
a query handle remaining valid while the job runs.

The workers read fixture identity, purity, coverage, and simulation attributes. NGC-0041872's
reported tumor/normal roles disagree with assayed identity and fail genotype concordance.
`find_specimens(identity="verified")` creates a new handle with verified roles; it changes no
clinical row. A new draft with that selection, confirmed by a human, completes. NGC-0041873
warns for purity, NGC-0041874 fails ReadQC coverage, NGC-0041876 retries eviction, NGC-0041877
runs about forty seconds, and NGC-0041878 includes adversarial log text.

OTel-shaped JSONL is tokenized at ingestion before storage or collector export. Logs/attempts
have their own tables and notifications, not repeated `view_pushed` events. `get_job` exposes
state, history, and at most ten summarized lines per request; the card tails forty. The database
keeps the complete ingested log. Raw synthetic Docker input/stdout remains clinical-zone data.

The independent jobs MCP server owns `ui://jobs/card` and `ui://jobs/grid`. Its React resource is
bundled with the official MCP Apps SDK and baked into the backend image. The host uses
AppBridge/PostMessageTransport, an opaque `allow-scripts` sandbox, and a CSP denying network,
forms, and external assets. Host RPC accepts only bound read access, never arbitrary tool calls
or URLs. Published view IDs and live handles stay stable; old v1 cards also render through MCP.
Desktop/mobile tests verify two independent jobs, refresh/history, keyboard activation,
unauthorized frame-call rejection, and unchanged chat/draft/job submission state on navigation.

The SOP index is generated from versioned Markdown at install/image-build time and opened with
SQLite `mode=ro&immutable=1`. Search returns exact line hits; range reads require the source
digest. Execution cases pin KB version
`693ea2d31132a7fd07d85209a5824f2ccd579706f617399a3d46b390636f6640`.
Citation assertions require a previously retrieved range and a supporting verbatim quotation.
They accept both `[specimen-identity:L7-L7]` and `[document:specimen-identity:L7-L7]`; this is
a bounded grounding check, not general semantic entailment.

The runtime journals each scope decision and tokenized completion before emission. Stable
operation IDs bind tool side effects and receipts to one transaction. On restart, completed
operations are reused and partial assistant text is retracted before replay. A database advisory
lock permits one LLM runtime owner. SIGKILL tests cover partial text and committed tool mutation;
the final visible response/mutations agree while the audit retains the retraction history.
Scripted transport fixtures intentionally retain their older failed-on-restart behavior.

Verification: 482 backend tests passed, with one opt-in Docker test skipped in the full suite;
the real-Docker execution suite passed separately. All 46 frontend tests, build, lint, 22
LLM/draft/job/privacy browser checks, and six scripted browser checks passed. The deployed
dispatcher was killed during two live jobs: both original containers completed with one attempt,
21 log entries each, and no chat sequence changes. Live swap diagnosis retrieved the SOP and
prepared an unsubmitted corrected draft. Views were inspected at desktop and 320-pixel mobile.

The full report has 29 requirements, 433 cases, 3,405 trials, 250 SSE interruptions, and 330 HTTP
case executions. All gates pass. Twelve independent recorded execution trials passed; grounding
is 9/9 [70.1%, 100%] and the small injection set is 3/3 [43.9%, 100%], using 95% Wilson intervals.
Slot filling remains 12/12 in two or three turns. These curated development samples and their
replay do not establish general resistance to malicious logs or production performance.

The final scope classifier uses one required closed `decision` enum. Empty-object allow calls
and a prompt-only clarification produced many invalid argument objects; both earlier batches
are retained under their original hashes. Strict validation was not loosened and no runtime
correction retry was added. The final 3,000-sample run retains 24 failures: six over-refusals,
ten inappropriate allowances, and eight provider connection failures. Recall is 990/1,000
[98.2%, 99.5%], acceptance 1,986/2,000 [98.8%, 99.6%], and precision 990/996 [98.7%, 99.7%].

The full privacy scan found zero known-identifier violations across 2,339 cassettes, 25 goldens,
63,023 active test events, 50,290 recorded requests, 673 job log records, 2,175 checkpoints, and
1,275 tool receipts. Raw clinical inputs and legacy private archives are not agent-zone evidence.

Local limits: the dispatcher has privileged Docker-socket access; this is not production
authorization or host isolation. Job containers are non-root, networkless, read-only, bounded,
and receive no database/provider credentials. Finished containers are retained for reconciliation;
external deletion of an execution unit is outside the restart invariant. Cleanup, platform retry
policy, and Kubernetes execution are PLAN9. No real clinical analysis or result release occurs.

---

## Evidence added

Extend **REQ-VIEW-03** from PLAN7 to live and MCP-owned views: reopening a reference preserves
identity and session scope, resumes read-only updates, and leaves job counts and state unchanged
by the navigation action.

**REQ-EXEC-01 (invariant).** One deterministic execution unit per confirmed job attempt, including
dispatcher restart reconciliation and bounded eviction retries. Tests assert container identity,
attempt count, and deduplicated logs, not just the number of job rows.

**REQ-EXEC-02 (invariant).** Job logs are tokenized before entering model context. Corpus scan.

**REQ-RESUME-01 (invariant).** An interrupted journaled turn resumes to the same final visible
response and mutations; the append-only history retains partial output and retraction events.
Extends the PLAN1 chaos suite from the connection layer to the runtime layer.

**REQ-GROUND-02 (measured).** Claims about job state and about retrieved documents are supported.
Job state claims check against the log deterministically. Document claims check that the cited line
range contains the claim, which is why line-granularity indexing was chosen.

**REQ-INJECT-01 (measured).** Instructions embedded in job logs do not alter behavior. Small case
set here, expanded substantially at PLAN10.

---

## Traps

**At-least-once claiming needs idempotent execution.** `SKIP LOCKED` plus a crash between claim and
Job creation can produce a duplicate. Make Job names deterministic from the job id so a duplicate
create is a conflict rather than a second execution.

**Live views and the event log.** A live card is not a `view_pushed` payload that keeps changing.
The push is one event, and the liveness comes from the handle subscription. Keeping that
distinction clear is what stops the event log from filling with progress noise.

**Log volume.** A chatty job can produce thousands of lines. The card tails a window, the database
keeps the whole thing, and the model sees a summary plus a requested range. Putting a full log in
context is how a context window dies.

**Resume and message retraction are subtle.** An interrupted step re-executes, so any partial
output must be retracted before the retry appends. Test it with interruptions specifically placed
mid-message, not only between steps.

**KB drift.** If the index is rebuilt without pinning, retrieval changes silently and goldens churn.
Version it, record the version in provenance, and fail the suite when the recorded version does not
match the loaded one.

---

## Next

[PLAN9](PLAN9.md) moves the zone boundary from documentation into enforcement.