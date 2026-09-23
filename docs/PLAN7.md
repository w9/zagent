# PLAN7: Job Drafts and Confirmation

**Status:** implemented
**Depends on:** [PLAN6](PLAN6.md)
**Shippable outcome:** chat and a form in the right panel edit one object, and nothing is submitted
without a human confirming the exact version they were shown. Titled references in chat open the
corresponding working-surface views. Sessions appear newest first with persistent topic titles.

---

## Goal

Build the draft state machine, and with it the confirmation invariant.

The original concept described two alternative interaction styles for starting a job: a
conversational slot-filling dialogue, and a form that appears pre-filled from a natural-language
request. Both are here, and they are the same thing. A draft is a persisted versioned object, chat
and form are two editors over it, and a natural-language correction and a form edit are the same
mutation.

---

## What you can see when it's done

Say "Prepare somatic calling on specimens received in the last day for NGC-0041875." A
submission form appears in the right panel, pre-filled from the request, with a validation notice
that a matched normal is missing.

Say "min VAF 0.03". The form field updates live, in place.

Change a field in the form by hand. The chat acknowledges it on the next turn, because both are
reading the same object.

After selecting valid specimens and resolving validation, press Confirm. A pending job card
replaces the form. NGC-0041875 is the missing-normal fixture; NGC-0041872 has a matched normal
and the tumor/normal swap reserved for PLAN8 execution.

Click a table, chart, or draft reference in chat to return to that exact view, even after newer
views have arrived. On mobile, the same action opens the working-surface tab. Opening a draft
does not edit or confirm it.

Create a session and it appears at the top of the sidebar. After its first meaningful exchange,
its fallback name becomes a short topic title such as "Specimen intake review". Rename it by
hand and that title stays yours, including after refresh or later conversation turns.

---

## What makes the invariant hold

Two mechanisms, and both are needed.

**The model has no submit tool.** Its only job-related capability is draft mutation. Submission is
an endpoint reachable from the UI's confirm action and nowhere else. No prompt, no injected
instruction and no tool-result content can cause a submission, because the capability does not
exist in the model's schema.

**Confirmation carries a version hash.** The confirm action posts the hash of the draft version
that was rendered. If the agent mutated the draft between render and click, the submission is
rejected and the user is shown the diff.

The second mechanism is the one usually missing. A confirmation button alone leaves a race in
which the agent alters parameters after the card renders, and the user confirms something they
never saw. Binding the confirmation to a version closes it, and the resulting property is
stronger and more precisely stateable: the user confirmed exactly this.

---

## Scope

**Session organization.** List sessions newest-created first, using descending `created_at` with
a stable ID tie-breaker. Use the same ordering for the API response and immediate client insertion;
new activity or a title change must not reorder older sessions. Selection remains keyed by session
ID, so inserting a new session does not change which existing conversation is open.

Persist a short title and its origin (fallback, automatic, or manual) with the session. Every
session gets a stable fallback independent of its position in the list. Backfill existing sessions
with stable fallbacks; reversing the list must not renumber their names. Sidebar and conversation
heading use the same persisted title and reflect changes across refreshes and browser tabs.

After the first completed in-scope exchange, generate one concise topic title through the existing
LLM gateway. Use only the tokenized conversation, preserve the PLAN6 boundary for generated and
manually entered titles, and prefer a topic description over patient-identifying details. This
is a bounded background operation: it does not delay the answer, block the next turn, or perform
clinical tool calls. Failure or an unavailable recording leaves the fallback intact without
failing the conversation or silently calling a live provider in replay mode. Do not regenerate
the title on every turn.

Manual rename takes precedence. An automatic result is applied only if the title is still
eligible for automatic naming; a user rename while generation is in flight wins atomically.
Later turns, refresh, and replay must never overwrite that manual choice.

**Draft objects.** Persisted rows with a version counter and a content hash. Fields: app id,
sample selection (by handle), parameters, validation state. Every mutation emits `draft_updated`
carrying the new version and hash, so the draft's history is in the event log like everything
else.

**Two editors, one object.** The model mutates through `update_draft`. The form mutates through an
HTTP endpoint. Both emit `draft_updated`. Both are subject to the same schema validation. The form
renders from the event stream, so a model-side change appears without a refresh.

**The form view kind.** A new registry entry, generated from the app's parameter JSON Schema plus
a layout hint. Generated rather than hand-built, so adding an app to the catalog does not mean
writing a form.

**Chat-to-surface references.** The host renders titled links alongside the originating assistant
turn from successful published-view receipts (`view_id`, kind, title). It resolves each reference
against the session's persisted view history, rather than parsing prose or asking the model to
invent a URL. The mechanism works for existing tables and charts as well as draft forms, and
PLAN8 reuses it for live job views.

Activation selects the exact view using the existing `view` URL parameter and opens
`panel=surface` on mobile. Preserve that explicit selection across refresh, replay, browser
back/forward, and subsequent view pushes; it must not silently switch to the latest view.
References are keyboard-accessible, have meaningful titles, and move focus to the selected
surface when appropriate. Missing or inaccessible targets show an explicit unavailable state;
an expired data handle keeps its existing expiry error rather than silently rerunning the query.

Reference activation is navigation only. Reading an existing view or its data is permitted; it
must not create another view, start a model turn, rerun a query, edit a draft, or submit a job.
View identity identifies a destination, not the draft version authorized for confirmation.

**Deterministic validation.** A validator, not the model, enforces app constraints:

| App | Constraint |
|---|---|
| `somatic-snv` | Requires a tumor and a matched normal from the same patient |
| `rna-fusion` | RNA libraries only |
| `germline-panel` | Library prep must match the panel |
| all | Parameters must satisfy the app's JSON Schema |

The model explains violations and proposes fixes. It does not decide whether a submission is
valid. This keeps a correctness property deterministic while leaving the model the part it is
actually good at.

**Simulated users.** The slot-filling flow is multi-turn, which is where a simulated user with a
hidden goal is the only practical way to measure convergence. Give the simulator a target draft,
let it converse, and score the final draft against the target. Pin the simulator's model
separately so its drift is not misread as agent drift.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Actual execution, queue, workers | PLAN8 |
| Live job monitoring | PLAN8 |
| Job cancellation and re-run | PLAN8 |
| Session deletion, search, and bulk organization | later usability work |
| Multi-step or dependent workflows | not a goal |

Confirm in this increment writes a job row in `pending` and renders a static card. Execution is
the next increment, which keeps this one focused on the state machine and the invariant.

---

## Key decisions

**One draft object, not two flows.** Building the conversational and form paths separately would
mean two state machines to keep consistent, and their inconsistency would be a permanent source of
bugs. Collapsing them is the central insight of this increment.

**Version-hashed confirmation.** See above. This is the decision that makes the invariant precise.

**No submit tool, ever.** Enforced by a property test over the tool registry, so it cannot be
reintroduced by accident during a later refactor.

**Validation is deterministic and lives outside the model.** The model's contribution is
explanation and proposal.

**Forms are generated from schemas.** Adding an app to the catalog should be a data change.

**References are host-owned navigation.** Published-view identity and session scope determine
the target. Labels and routes come from validated receipt/history metadata, not model-written
URLs. One mechanism serves every view kind without constraining the agent's explanatory prose.

**Session identity is independent of ordering and naming.** Creation time determines list order;
session ID determines selection; persisted metadata determines the title. Model-generated naming
is optional assistance, never a dependency of answering or a replacement for an explicit user edit.

---

## Definition of done

- [x] New sessions appear first immediately and after reload, with deterministic ordering when
  creation timestamps tie; title changes and new turns do not reorder the list.
- [x] Existing and new sessions have stable persisted fallback names independent of list index;
  sidebar, conversation heading, selected session, and multiple tabs remain consistent.
- [x] The first completed in-scope exchange triggers one bounded, privacy-aware topic-title
  generation through the record/replay gateway, without delaying the answer or next turn.
- [x] Manual rename persists and wins over an in-flight automatic title; subsequent turns and
  refresh never overwrite it. A concurrency test covers the delayed-generation race.
- [x] Title generation failure or replay cassette miss leaves the fallback and conversation
  usable, with no silent live fallback; empty or refused-only sessions keep their fallback.
- [x] Topic-title cases cover different conversation subjects, while privacy tests verify that
  title generation and manual renaming introduce no raw-identifier path into model context.
- [x] A natural-language request produces a pre-filled form with correct field values.
- [x] A chat correction updates the form live, without a refresh.
- [x] A form edit is visible to the agent on the next turn.
- [x] Chat renders titled references for successfully published tables, charts, and draft forms.
- [x] Clicking or keyboard-activating a reference selects its exact view and opens the surface
  on mobile, with accessible focus handling.
- [x] Reference targets remain stable after refresh, replay, back/forward navigation, and newer
  view pushes; failed publications do not create links.
- [x] Missing, expired, or cross-session targets fail visibly without falling back to another
  view or leaking another session's data.
- [x] Activating a reference never reruns a query, starts a model turn, changes a draft version,
  or submits a job. Browser tests cover these no-side-effect guarantees.
- [x] A missing matched normal is flagged by the validator and explained by the agent.
- [x] Confirm submits and renders a job card.
- [x] Confirm with a stale version hash is rejected, and the user sees what changed.
- [x] No submit capability exists in the tool registry. Property test.
- [x] An injected instruction in a tool result cannot cause a submission. Case in the suite.
- [x] Simulated users reach the target draft, reported with an interval.
- [x] Chaos mode: interrupting a turn mid-draft-update leaves a consistent draft.

## Implementation And Verification

Migrations 006/007 add drafts, immutable revisions, pending jobs, and persisted session titles.
`DraftStore` serializes edits and confirmation with the session/draft locks. The semantic hash
covers app, specimen handle, and parameters, normalizing integral numbers; validation and display
metadata do not change it. Confirmation revalidates the selection and parameters, creates one
job and its view transactionally, and is idempotent for repeat clicks. The runtime database
role cannot write draft/job tables, and the model registry contains only draft mutation.

The four catalog apps share a generated scalar-schema form. Both editors use the same validator;
unsupported parameters can be removed with a null patch. Somatic selection uses one specimen
query containing both tumor and normal records for one patient. RNA requires prepared RNA-seq
libraries and RNA specimens; germline requires a library for each specimen and compatible prep.
Unsupported form schema features fail at catalog load rather than in the browser.

The display API provides `/catalog`, `GET/PATCH /sessions/{id}/drafts/{draft_id}`,
`POST /sessions/{id}/drafts/{draft_id}/confirm`, and `PATCH /sessions/{id}` for rename. Confirm
and edit require the displayed `content_hash`; a 409 includes current state and a field diff.
The form preserves its edit-base hash while the model updates in the background. Manual edits
enter the next model turn through the latest persisted draft state. There is no execution queue.

Session ordering is `created_at DESC, id DESC`. UUID-derived fallback titles survive migration,
reload, and reordering. A separate metadata SSE feed updates names across tabs. Automatic naming
runs at most once after a meaningful in-scope exchange, with an 80-token cap and 15-second
timeout. A guarded write makes manual rename win even if the title request is still in flight.
The tokenization boundary applies to both paths; replay misses keep the fallback.

Published history supplies host-owned links for every view kind. Explicit targets stay pinned
through later pushes, refresh, and browser history; unknown targets remain unavailable. Navigation
does not invoke mutation tools or confirmation. Browser checks cover desktop and mobile, including
320-pixel form/chart framing and unchanged event sequence, drafts, and jobs after navigation.

Verification includes 449 passing keyless backend/evaluation tests, frontend build and 46 component
tests, 20 LLM/draft/privacy browser checks, six retained scripted browser checks, and focused
catalog, title-concurrency, injection, session-isolation, and RNA-library tests. The report has
24 requirements, 428 cases, 3,382 trials, 240 interrupted workflows, and 306 HTTP case executions.
All gates pass. The final full-run privacy scan found zero known identifiers in 1,108 cassettes,
24 goldens, 49,383 active test events, and 32,899 recorded gateway requests.

Live verification also exposed a stale-answer risk: the model repeated an older tool receipt
despite receiving the newer form edit. Latest persisted draft state is now appended as an
explicit authoritative context message. DRAFT-CONFIRM includes a form edit followed by model
readback before confirmation, and the same live session correctly acknowledged the saved value
without mutation. The earlier answer remains in its history. Correct narration is still model
behavior, not a guarantee implied by the deterministic confirmation invariant.

Each app converged in 3/3 independent recorded simulated-user conversations, taking three turns
and submitting no job. Per-app 95% Wilson intervals are [43.9%, 100%]; pooled convergence is
12/12 [75.8%, 100%]. The earlier contract reached 8/12 and exposed missing selection binding
and an inability to remove invented parameters. Those recordings remain; the corrected contract
produced different request hashes. Agent and simulator models/prompts are pinned separately.
Replay checks regressions, not fresh convergence, and these small development samples do not
establish production performance.

The refreshed scope measurement retains 77 failed trials: 54 over-refusals, seven inappropriate
allowances, and 16 provider errors. Recall is 993/1,000 and in-scope acceptance is 1,930/2,000;
both lower-bound gates pass. No failed response was rerolled to make the report green. See the
[harness guide](../evals/README.md) and generated [report](evals/index.html) for details.

---

## Evidence added

**REQ-SESSION-01 (invariant).** Session ordering is newest-created first and deterministic;
selection and persisted titles do not depend on list position. API and desktop/mobile browser
tests cover insertion, timestamp ties, reload, existing-session fallback migration, and stable
selection when the list changes.

**REQ-SESSION-02 (invariant).** Automatic naming cannot overwrite a manual title or block a
conversation. Tests cover concurrent rename/generation, failed or missing recordings, one-time
generation, and cross-tab consistency. Title ingress and gateway requests remain subject to
PLAN6's privacy assertions. Whether a generated title describes the topic well is model behavior,
covered by representative recorded cases rather than claimed as an invariant.

**REQ-VIEW-03 (invariant).** A chat reference resolves only to its published view in the current
session, and activation performs navigation without workflow mutations. Replay/projection tests
verify receipt-to-view identity; desktop/mobile browser tests cover keyboard access, history,
refresh, unavailable targets, and unchanged query, draft, and job state after activation.

**REQ-JOB-01 (invariant).** No pending job is created without a confirmation carrying the
matching draft content hash. Asserted at the state machine level, over every path.

**REQ-JOB-02 (invariant).** The model has no tool capable of submitting. Property test over the
registry.

**REQ-JOB-03 (invariant).** Submission of a stale version is rejected. Tested by mutating the
draft between render and confirm.

**REQ-VALID-01 (invariant).** App constraints are enforced by the validator regardless of model
output. Tested by driving the submission endpoint directly with invalid drafts.

**REQ-SLOT-01 (measured).** Simulated users converge on their hidden target draft. Report per-app,
since convergence on `somatic-snv` with its matched-normal constraint is a harder problem than on
`readqc`.

New assertion kind:

```yaml
expect:
  draft:
    app: somatic-snv
    params_match: {min_vaf: 0.03}
    validation: [missing_matched_normal]
  submitted: false
```

---

## Traps

**Reversing the list while keeping index-based names.** The current generated labels depend on
list position. Persist stable fallbacks before changing ordering, and never use the display title
as session identity. Protect manual naming at write time, not only by checking before a model call.

**A reference that means "latest" instead of "this view".** Even a reference to the current head
must retain its explicit identity when later views arrive. Do not reuse an auto-follow shortcut
that discards the selected ID. A missing target is unavailable, not permission to show another view.

**Version hash churn.** If the hash covers fields that change for cosmetic reasons, users get
spurious rejections and learn to ignore the warning. Hash the semantic content of the draft:
app, samples, parameters. Not timestamps, not validation state, not display hints.

**Rejection that is useless.** A rejected confirmation must show the diff between what was rendered
and what is current. A bare error makes the mechanism feel like a bug rather than a protection.

**Form generation hitting schema features it cannot render.** Constrain the parameter schemas to a
supported subset, and fail at catalog-load time rather than at render time.

**The simulator being too easy.** A simulator that states its whole goal in the first turn measures
nothing. Give it partial information and a tendency to answer only what was asked, which is how
people actually behave.

**Draft updates during a turn.** A draft mutated by the model while the user is typing in the form
needs a resolution rule. Last write wins on a field basis, with the version hash catching the
dangerous case, is sufficient and understandable.

---

## Next

[PLAN8](PLAN8.md) makes the jobs actually run, and the right panel come alive.