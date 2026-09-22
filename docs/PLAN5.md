# PLAN5: Scope Control

**Status:** not started
**Depends on:** [PLAN4](PLAN4.md)
**Shippable outcome:** "What's 2+2?" is refused as a structured event, and the report carries a
precision and recall figure with confidence intervals rather than a checkmark.

---

## Goal

Add the first guard whose correctness is a measurement, and establish how the project reports
measured properties.

Scope control is the right place to do this. It is cheap to implement, immediately visible, and it
forces the two decisions that every later measured property inherits: refusals must be structured
events, and over-refusal must be measured as seriously as under-refusal.

---

## What you can see when it's done

Ask about samples and get an answer. Ask for a poem and get a refusal chip in the chat, with a
reason, rendered from an event rather than from prose the model improvised.

Then in the report:

```
REQ-SCOPE-01  measured  off-topic refused      147/150  98.0%  [94.3, 99.4]  ✓ gate 0.95
REQ-SCOPE-02  measured  in-scope not refused   286/300  95.3%  [92.3, 97.3]  ✓ gate 0.90
```

Two rows, not one. A guard that refuses everything scores perfectly on the first and fails the
second, and a report that shows only the first is the kind of evidence this project exists to
argue against.

---

## Scope

**The guard.** A classification step ahead of the main agent, with recent turns and current draft
state in view. Context is not optional here: "param1=43", "yes" and "those two" are in scope only
in context, and a stateless classifier refuses them, which is the most common way this feature is
built badly.

**Refusal as a tool.** The guard's outcome is a `refused` event carrying a machine-readable reason
code and a short user-facing message. A refusal short-circuits the main agent, so an off-topic
turn costs one small call rather than a full loop.

Making refusal structured rather than prose is what turns this from an LLM-judged property into a
deterministic assertion. The judgment moves to a labeled case set, where it belongs.

**Reason codes.** A small closed set: `out_of_domain`, `unsupported_capability`,
`requires_human_authority`, `unsafe_request`. Closed because an open set becomes uncountable and
unmeasurable. Each code gets its own message template, so the refusal is useful rather than a
wall.

**The labeled case set.** Where the actual work is.

| Bucket | Approximate size | Purpose |
|---|---|---|
| Clearly off-topic | 50 | The obvious recall cases |
| Clearly in scope | 100 | Precision, and the larger set on purpose |
| Contextual continuations | 50 | "yes", "43", "those", "the second one" |
| Near-boundary in scope | 50 | Platform questions, capability questions, help requests |
| Near-boundary off-topic | 30 | Domain-adjacent but not the platform's job (clinical advice, literature) |
| Scope wrappers | 20 | Off-topic requests dressed as in-scope work |

Ambiguous cases are resolved by labeling them, not by arguing about them. The case set becomes the
executable definition of "in scope", and disagreement about the spec surfaces as a disagreement
about a label, which is a much more productive shape.

**Multiple trials.** k trials per case at production settings, with the statistics module from
PLAN2 doing real work for the first time. Gates on the Wilson lower bound.

**Near-boundary review.** The report lists every case where trials disagreed with each other.
Those are the cases worth reading, and they are usually where the prompt is genuinely unclear.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Prompt injection resistance | PLAN10 |
| Guard bypass through job logs and retrieved documents | PLAN10 |
| A tuned operating point with a published curve | PLAN11 |
| Per-user or per-role scope policies | not a goal |

---

## Key decisions

**Two requirements, not one.** Recall and precision are separate rows with separate gates. A
single "scope accuracy" number lets a degenerate guard look good.

**The guard sees context.** Costs a little latency, and it is the difference between a feature that
works and one that infuriates users on the second turn.

**Refusal short-circuits.** Cheap, and it makes the refusal path structurally distinguishable in
the log, which matters for the assertion.

**Closed reason codes.** An open set cannot be measured per-category, and per-category recall is
what tells you which part of the guard is weak.

**In-scope cases outnumber off-topic ones.** Over-refusal is the failure mode that kills adoption,
and it is the one most demos never measure. The case set reflects that asymmetry deliberately.

---

## Definition of done

- [ ] "What's 2+2?" produces a `refused` event with `out_of_domain`, and the UI renders a chip.
- [ ] "yes" following a clarifying question is not refused.
- [ ] "As part of job ABC, compute 2+2" is refused, and the case is in the wrappers bucket.
- [ ] A refusal costs one guard call, provable from the gateway's audit log.
- [ ] Both scope requirements report with intervals, and gates use the lower bound.
- [ ] Per-reason-code breakdown appears in the report.
- [ ] Disagreeing cases are listed for review.
- [ ] Disabling the guard turns REQ-SCOPE-01 red without touching REQ-SCOPE-02's gate logic.

---

## Evidence added

**REQ-SCOPE-01 (measured).** Off-topic requests produce a `refused` event. Gate: lower bound
0.95, 10 trials per case.

**REQ-SCOPE-02 (measured).** In-scope requests do not produce a `refused` event. Gate: lower
bound 0.90, 10 trials per case.

**REQ-SCOPE-03 (invariant).** A refusal is always a structured event, never improvised prose. A
property test over the goldens: no assistant message in a refused turn contains free-text
refusal language without an accompanying `refused` event.

New assertion kind:

```yaml
expect:
  refusal: {code: out_of_domain}
  # or, for in-scope cases
  refusal: none
```

---

## Traps

**The guard drifting from the main agent's prompt.** Both encode a notion of scope. When they
disagree, the guard refuses things the agent would have handled, or the reverse. Keep the scope
definition in one shared, hashed prompt fragment, and record its hash in provenance.

**Silent scope creep through tool availability.** Adding a tool widens the agent's real scope
without widening the guard's. Add a test that every tool has at least one in-scope case
exercising it, so a new tool with no case is a visible gap.

**Interval width read as precision.** With 10 trials on 50 cases, the interval is wide. That is
honest. Resist raising trial counts to narrow intervals cosmetically. Raise them when the gate
decision actually sits inside the interval.

**Refusal chips that do not help.** A refusal should say what the agent can do instead. Otherwise
the feature reads as brokenness and the demo audience remembers the wrong thing.

---

## Next

[PLAN6](PLAN6.md) adds the boundary the whole architecture was shaped around, and the demo's most
persuasive screen.