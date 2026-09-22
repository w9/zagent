# PLAN1: The Spine

**Status:** complete
**Depends on:** nothing
**Shippable outcome:** tokens stream into a chat panel, and refreshing the browser mid-stream
picks up exactly where it left off.

---

## Goal

Establish the one part of the architecture that is expensive to reverse: an append-only event
log, conversation turns that are decoupled from connections, and a client that tails the log
and can resume.

There is no LLM in this increment. The agent is a script that emits a fixed sequence of events
with sleeps between them. That is deliberate. Everything built on top of the spine can be
proven correct before a nondeterministic component is introduced, and the fake agent remains
useful forever as the fastest deterministic fixture in the suite.

---

## What you can see when it's done

A three-panel layout in the browser. Left and right panels are present but empty, with the
right shape and no content. The middle panel is chat.

Type a message. Text streams in word by word with visible latency. Refresh the page halfway
through. The stream continues from where it was, with no duplicated and no missing text. Open a
second tab on the same session and watch both stream together.

That last behavior is the demo for this increment. It is also the first row of the guarantee
table, provable on day one.

---

## Scope

**Data model.** Sessions, conversation turns, events. Per-session monotonic sequence, allocated by
incrementing a counter on the session row so appends within a session serialize. Events carry
`{session_id, seq, conversation_turn_id, schema_version, type, payload, created_at}` with the primary key on
`(session_id, seq)`.

One conversation turn covers a user message and the agent's processing and response, not an
analysis job run. At most one conversation turn is active per session.

**Event types, v2.** Define the whole vocabulary now, even though this increment emits only a
few. Later plans fill in the rest without schema churn. Version 2 makes conversation-turn
naming explicit; historical v1 events remain readable without rewriting the log.

| Type | Emitted from | First used |
|---|---|---|
| `user_message` | Web BFF on POST | PLAN1 |
| `conversation_turn_started`, `conversation_turn_finished`, `conversation_turn_failed` | Runtime | PLAN1 |
| `text_delta`, `message_done` | Runtime | PLAN1 |
| `message_dropped` | Runtime | PLAN8 (reducer support required now) |
| `step_started`, `step_finished` | Runtime | PLAN3 (scripted markers) |
| `tool_call`, `tool_result` | Runtime | PLAN4 |
| `view_pushed` | Runtime | PLAN3 |
| `refused` | Scope guard | PLAN5 |
| `draft_updated` | Runtime and Web BFF | PLAN7 |

**HTTP surface.**

```
POST   /sessions                          -> create
GET    /sessions                          -> list
POST   /sessions/:id/messages             -> 202, starts a background conversation turn
GET    /sessions/:id/events?from=<seq>    -> SSE, id = seq, honors Last-Event-ID
GET    /sessions/:id/snapshot             -> projected state at current seq
```

The POST response carries `{session_id, conversation_turn_id}`. The snapshot contains
`{session_id, seq, messages, conversation_turn}`, with the latest conversation turn's state.

**The append path.** Conversation turns execute as background tasks and append to the log.
A Postgres NOTIFY per append wakes subscribers, which then read forward from their last seen sequence. Token
deltas are coalesced on a short timer, so a streamed sentence is a handful of rows rather than
one per token.

**The client.** An event reducer that projects the log into render state, and an SSE subscriber
that opens with `from`, reconnects with `Last-Event-ID`, and reconciles. The reducer must
support removing an assistant message by id from the start, even though nothing emits
`message_dropped` until PLAN8. Retrofitting removal into an append-only reducer is a rewrite.

**The agent interface.** `Agent.run_turn(session, emit)`. One implementation, `ScriptedAgent`,
which reads a small YAML script of events and delays.

**Layout.** `apps/web`, `services/agent`, `evals/`, `deploy/compose`. Extraction into more
services happens at PLAN9 and should stay mechanical, so keep module boundaries honest even
inside one process.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Any LLM, any tool call | PLAN4 |
| The general eval harness and case-driven goldens | PLAN2 |
| Right-panel views | PLAN3 |
| Session titles, rename, delete, search | PLAN3 or later, as polish |
| Authentication, multi-user | not a goal (see ARCHITECTURE section 16) |
| Kubernetes | PLAN9 |
| Journal-based conversation turn resume after a runtime crash | PLAN8 |

Sessions in the left panel can be a plain list with generated names. Resist building session
management here. It is the most familiar feature in the project and therefore the biggest
time sink for the least new information.

---

## Key decisions

**POST does not return the stream.** It returns 202. The client is already subscribed. If this
is built the other way, conversation turn lifetime is bound to connection lifetime and every
durability property becomes a special case. This is the decision the whole plan exists to lock in.

**The sequence is per session, from a counter row.** A shared sequence allows a reader to
observe seq 7 before seq 6 is committed, which for a tailing reader means silently skipping an
event. The row lock on the session is the correct serialization point and matches the
model of one active conversation turn per session anyway.

**Coalesce deltas, keep the reducer append-plus-remove.** Coalescing is a write-side
optimization the client should not have to know about. Removal support is a client-side
requirement the write side does not yet exercise.

**Normalize early.** Write the transcript normalizer in this increment, even before PLAN2 uses
it: event types plus significant payload fields, with ids, timestamps and durations redacted.
It is fifteen lines and it is the foundation of every later assertion.

---

## Definition of done

- [x] `make up` brings up Postgres, the agent service and the web app, seeded and migrated.
- [x] Sending a message streams visible text into the chat panel with realistic pacing.
- [x] Refreshing mid-stream resumes with no gap and no duplication.
- [x] Closing the tab mid-stream and reopening shows the completed conversation turn.
- [x] Two tabs on one session stream simultaneously and agree.
- [x] A conversation turn that raises emits `conversation_turn_failed` and the UI shows a failed state rather than hanging.
- [x] `zagent transcript <session_id>` prints the normalized transcript.
- [x] The two tests below pass.

## Implementation notes

- Backend: [services/agent/zagent](../services/agent/zagent), with separate store, runtime,
	agent, stream, and HTTP modules. Startup runs versioned SQL migrations and seeds one empty
	session. Event updates and deletes are rejected by a database trigger.
- Client: [apps/web](../apps/web), using a snapshot cursor followed by native `EventSource`.
	Duplicate sequences are ignored, gaps trigger a fresh snapshot, and `message_dropped`
	removes a message in both the browser and server projections.
- `/events` defaults to a finite feed once a nonempty session is caught up and its conversation
	turn is terminal. `follow=true` keeps a live session subscription open for future conversation
	turns and other tabs. A `caught_up` control frame reports the current cursor and active
	conversation turn state without allocating an event sequence. The UI's completion state
	comes from terminal log events.
- Deltas flush every 180 ms. NOTIFY wakes readers; a two-second poll is the backstop.
	Normalization merges consecutive deltas for the same message before comparing goldens,
	making timer boundaries irrelevant to transcript evidence.
- Send `/fail` to exercise an agent exception. Runtime restarts fail abandoned conversation
	turns; journal recovery remains out of scope. Deploy exactly one agent runtime process in
	this increment.
- Verification: `make test`, `make chaos`, and `make browser`. Browser tests cover refresh,
	two tabs, physical SSE socket interruption with native `Last-Event-ID`, tab closure,
	failed conversation turns, and desktop/mobile layouts. See [evals/README.md](../evals/README.md).
- Migration 002 renames the original table and identifier column to `conversation_turns` and
	`conversation_turn_id`. Stored event types, payloads, timestamps, and sequences are unchanged;
	the server translates legacy v1 lifecycle events to schema v2 when reading them.

---

## Evidence added

**REQ-STREAM-01 (invariant), golden transcript.** Execute one `ScriptedAgent` conversation turn
on a fixed script, read the log, normalize, diff against a checked-in golden file.

**REQ-STREAM-02 (invariant), chaos resume.** For each of 50 seeded trials, drop the SSE
connection at a pseudo-random point during a conversation turn, reconnect with `Last-Event-ID`,
and assert the reassembled client-side transcript is identical to an uninterrupted conversation
turn using the same script.
Parameterize the interruption point so failures are reproducible from the seed.

The chaos test is written by hand here and folded into the harness at PLAN2. Writing it now
matters because it is what proves the architecture, and because it is much easier to get the
resume logic right while the event vocabulary is four types wide.

---

## Traps

**Coalescing and resume interact.** If the coalescing buffer is flushed on a timer but the
sequence is allocated at flush time, an interruption between two flushes is safe. If sequence
allocation and flush are separated, they can reorder. Allocate at append.

**NOTIFY payloads have a size limit and NOTIFY is not a delivery guarantee.** Use it purely as a
doorbell. The subscriber's actual read is always "give me everything after seq N", so a dropped
notification costs latency and never correctness. Add a slow poll as a backstop.

**`EventSource` cannot set headers.** Fine now, since there is no auth. Note it, because it
decides the auth approach later.

**A reconnect after a completed conversation turn must terminate.** The subscriber needs to
distinguish "no events yet" from "the conversation turn is over", or the client hangs on a
finished session. `conversation_turn_finished` in the log is the signal, not connection state.

---

## Next

[PLAN2](PLAN2.md) turns the two hand-written tests into the harness that every later increment
reports through.

PLAN2 is now implemented: [evals/test_streams.py](../evals/test_streams.py) delegates to the shared
HTTP evaluator. Five case-driven goldens replace the original single scripted golden, and all
five cases participate in the 50 seeded chaos trials. See [evals/README.md](../evals/README.md).