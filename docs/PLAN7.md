# PLAN7: Job Drafts and Confirmation

**Status:** not started
**Depends on:** [PLAN6](PLAN6.md)
**Shippable outcome:** chat and a form in the right panel edit one object, and nothing is submitted
without a human confirming the exact version they were shown.

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

Say "run somatic calling on the specimens that came in yesterday for patient NGC-0041872". A
submission form appears in the right panel, pre-filled from the request, with a validation notice
that a matched normal is missing.

Say "min VAF 0.03". The form field updates live, in place.

Change a field in the form by hand. The chat acknowledges it on the next turn, because both are
reading the same object.

Press Confirm. A job card replaces the form.

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

---

## Definition of done

- [ ] A natural-language request produces a pre-filled form with correct field values.
- [ ] A chat correction updates the form live, without a refresh.
- [ ] A form edit is visible to the agent on the next turn.
- [ ] A missing matched normal is flagged by the validator and explained by the agent.
- [ ] Confirm submits and renders a job card.
- [ ] Confirm with a stale version hash is rejected, and the user sees what changed.
- [ ] No submit capability exists in the tool registry. Property test.
- [ ] An injected instruction in a tool result cannot cause a submission. Case in the suite.
- [ ] Simulated users reach the target draft, reported with an interval.
- [ ] Chaos mode: interrupting a turn mid-draft-update leaves a consistent draft.

---

## Evidence added

**REQ-JOB-01 (invariant).** No job transitions out of `draft` without a confirmation carrying a
matching version hash. Asserted at the state machine level, over every path.

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