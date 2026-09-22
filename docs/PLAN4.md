# PLAN4: The Real Agent

**Status:** implemented
**Depends on:** [PLAN3](PLAN3.md)
**Shippable outcome:** a real model answers real questions about a seeded genomics cohort, and
the existing suite still passes in replay mode with no provider key.

---

## Goal

Substitute `LlmAgent` for `ScriptedAgent` without changing anything else, and add the fixture
cohort the rest of the project reasons about.

The test of this increment is that the goldens written in PLAN1 through PLAN3 still pass. They
were written against scripted output, so wherever they now fail, either the substitution changed
behavior that should not have changed, or the golden was asserting something accidental. Both are
useful findings.

---

## What you can see when it's done

Ask "what specimens came in yesterday for patient NGC-0041872" and get a real answer with a real
table. Expand the step markers and see the tool call, its arguments and its result. Ask a
follow-up and watch it use context.

Run `make evals` with no API key set and watch the same conversations replay deterministically in
seconds.

---

## Scope

**The LLM gateway.** A thin service, the only component with internet egress. Three
responsibilities:

- Provider routing, so the nightly model matrix at PLAN10 is configuration.
- Record and replay, keyed on a hash of the normalized request. Replay is the default. A cassette
  miss in replay mode is a loud failure, never a silent fallthrough to live.
- A slot for the egress tripwire, which arrives at PLAN6.

Cassettes are checked in. They are the reason CI is free, deterministic and keyless, and they are
reviewable: a diff in a cassette is a visible change in what the model was asked.

**The tool loop.** `step_started`, `tool_call`, `tool_result`, `step_finished` around each
iteration, with a hard cap on iterations per turn. Tool arguments are validated against a schema
before dispatch, and a validation failure is returned to the model as a result rather than raised,
so the model can correct itself and the correction is visible in the log.

**The tools gateway.** An MCP client and the single policy enforcement point. In this increment it
does allowlisting, argument validation and audit logging. Tokenization joins at PLAN6, which is
why the boundary exists now even though it is thin.

**Four tools.**

| Tool | Returns |
|---|---|
| `find_patients` | Handles and a count |
| `find_specimens` | A query handle, a count and a schema |
| `find_libraries` | A query handle, a count and a schema |
| `push_view` | Acknowledgement. Takes a spec, with data bound by handle |

**Handles, not rows.** This is the increment that establishes it, and it is not optional.
Data-returning tools return `{handle, count, schema}`. `push_view` takes a handle. The renderer
resolves it. The model composes views over data it never receives.

The cost is real: the model cannot reason over result contents. Where a question genuinely needs
that, the answer is an explicit aggregate tool, not a relaxation of the rule. Relaxing it here
makes PLAN6 a rewrite rather than an addition.

**Relative time windows.** Tools accept `received_within: P1D` rather than date ranges. Dates are
quasi-identifiers, and a relative window is what the user meant. This removes the single most
awkward case from PLAN6 before it exists.

**The fixture cohort.** Deterministic generation from a seed, timed relative to now.

- Five invented hospitals across four regions, each with its own MRN format. Differing formats
  are not decoration: they are what makes detector recall at PLAN6 a real measurement.
- Patients, specimens (tumor, normal, RNA, with purity and collection times) and libraries (prep,
  coverage, QC status).
- Four seeded conditions the rest of the project depends on: a tumor/normal swap, a low-purity
  tumor, a low-coverage library, and a matched normal that is simply missing.
- A background simulator so "yesterday" and "today" always return something. The clock is frozen
  and the simulator paused for evals.

**Cross-site isolation.** Postgres row-level security on the clinical tables, with the demo
scoped to one site. Enforcing it in the database rather than in query construction means it holds
regardless of what the agent asks for.

**Charts.** A second view kind, using a Vega-Lite subset, now that there is data worth charting.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Scope guard and refusal | PLAN5 |
| Tokenization and the tripwire | PLAN6 |
| Job drafts, submission, execution | PLAN7, PLAN8 |
| Knowledge base retrieval | PLAN8, where the SOP lookup is needed |
| Model matrix, judges, adversarial cases | PLAN10 |

This increment has no guard of any kind. It will happily answer "what's 2+2". That is fine and it
is the correct order: PLAN5 is much easier to measure against an agent that is known to work than
against one being built at the same time.

---

## Key decisions

**Record and replay is in the gateway, not the test harness.** Anything above the gateway,
including the runtime's own retry and error handling, is then exercised identically in replay and
live mode. A harness-level mock would skip all of it.

**A cassette miss fails.** Falling back to a live call on a miss makes CI non-deterministic and
occasionally expensive, and it hides prompt changes.

**Handles instead of rows, adopted before the privacy work.** Introducing the pattern for its own
merits, one plan before it becomes load-bearing, means PLAN6 adds a boundary to an architecture
that already suits it.

**RLS rather than query-level filtering.** Isolation that depends on every query being written
correctly is not isolation.

**Fixtures are generated, not fixed.** A seeded generator with relative timing keeps the demo
alive without a data refresh ritual, and the seed keeps it reproducible.

---

## Definition of done

- [x] Every PLAN1 through PLAN3 golden passes with `LlmAgent` in replay mode, or the difference is
      explained in the commit.
- [x] `make evals` needs no provider key and completes in under a minute.
- [x] A cassette miss in replay mode fails with the request hash and a hint to re-record.
- [x] Multi-turn context works: a follow-up referring to "those" resolves correctly.
- [x] Step markers show tool names, arguments and results, and expand cleanly.
- [x] No tool returns rows. Asserted as a property test over every tool's response schema.
- [x] A cross-site query returns nothing, with RLS as the reason, proven by a test that queries
      as the wrong role.
- [x] The iteration cap is enforced and produces a clean `conversation_turn_failed`.

### Implementation Evidence

- `LlmAgent` uses the existing runtime and event contract. The gateway supports OpenRouter and
  OpenAI routes, defaults to replay, hashes normalized requests with an explicit prompt hash,
  and exposes an egress-check hook for PLAN6. The configured cheap model is
  `deepseek/deepseek-v4.1-flash`; 18 real provider cassettes cover two multi-turn/count cases.
- Legacy PLAN1-3 goldens are unchanged and still run as scripted transport fixtures. This is
  the intentional substitution exception: literal canned prose, inline fake rows, and scripted
  failure commands are not valid expectations of a handle-only real agent. `REAL-001/002`
  exercise the same stream, view, snapshot, golden, and chaos assertions through `LlmAgent`.
- The full keyless replay suite passed 125 trials / 136 HTTP executions in 45 seconds locally.
  Repeated replay trials test runtime behavior, not independent model samples. Grounding is
  deliberately limited to explicit integer clinical entity counts supported by earlier results.
- Query handles persist in Postgres, are session/site bound, expire visibly after 24 hours, and
  hold at most 200 rows. MCP responses are schema-checked and capped at 8 KiB. Rejected arguments
  are audited and returned to the model for correction. Eight model iterations is the default cap.
- Seed 41872 generates five invented sites with distinct MRN formats and all four required
  conditions. Live fixtures refresh relative times every minute. Evals freeze the clock at
  `2026-01-15T12:00:00Z` and disable simulation. Wrong-role tests query clinical tables directly.
- Browser tests verify handle-backed tables, tool details, multi-turn library lookups, chart
  pixels, refresh/history, and missing-cassette errors at desktop and narrow mobile widths.
- Only the gateway joins the Compose egress network. Fixed loopback TCP ingress also lives there
  so web, API, and Postgres can stay internal-only. Live credentials are mounted from an
  owner-only external file; replay Compose and CI do not require that file or a provider key.

---

## Evidence added

**REQ-TOOL-01 (invariant).** No data-returning tool's response schema permits row data. Property
test over the registry.

**REQ-ISO-01 (invariant).** A session scoped to one site cannot read another site's rows. Tested
directly against the database roles, not through the agent.

**REQ-GROUND-01 (measured).** The agent does not assert facts absent from the event log. Checked
by extracting factual claims from assistant messages and requiring support in a preceding
`tool_result`. Start with a narrow, deterministic version: numeric claims must match a count or
an aggregate in the log. Broaden at PLAN10.

**REQ-CTX-01 (measured).** Multi-turn reference resolution. Small case set, expanded at PLAN7 by
the simulated users.

This is where multiple trials per case begin to matter, and where the statistics module built at
PLAN2 starts doing real work.

---

## Traps

**Request hashing is subtle.** Normalize away anything that varies without meaning: key order,
whitespace, injected timestamps, request ids. Get this wrong and cassettes miss constantly.
Get it too loose and a real prompt change silently replays the old response. Include the prompt
hash in the cassette key explicitly rather than relying on the request text to carry it.

**Handles need a lifetime.** A handle referenced after its query result expires must fail
visibly rather than render empty. Decide the expiry policy now, even if it is generous.

**Tool result size still matters.** Handles bound row data, but a schema with two hundred columns
or a tool that returns a long free-text field puts the context back where it was. Cap result
sizes at the gateway.

**Fixture realism is load-bearing for later plans.** The seeded failure conditions are not
flavor. PLAN8's best moment depends on the tumor/normal swap being diagnosable from a job log, and
PLAN7's clarification flow depends on the missing matched normal. Generate them deliberately and
assert on their presence in a fixture test.

---

## Next

[PLAN5](PLAN5.md) adds the first behavioral guard, and the first requirement whose honest answer
is a number rather than a checkmark.