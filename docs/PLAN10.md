# PLAN10: Adversarial Proof

**Status:** implemented locally; human judge calibration and remote CI/Pages acceptance pending
**Depends on:** [PLAN9](PLAN9.md)
**Shippable outcome:** deliberately breaking any guarantee turns the suite red, and the report
carries adversarial results across a model matrix.

---

## Goal

Answer the question a sharp reviewer asks after seeing a green report: **how do you know the evals
would catch a violation?**

Everything before this increment builds guarantees and measures them. This increment attacks them,
and, more importantly, attacks the measurement itself. A suite that cannot detect a broken build is
not evidence, and until this increment lands, the project has not demonstrated that its suite can.

---

## What you can see when it's done

```
$ make evals MUTATE=all

MUTATION            DISABLES                    SUITE    DETECTED BY
tokenizer_off       ingress tokenization         RED      REQ-PHI-02
tripwire_off        egress hash check            RED      REQ-META-02
submit_tool_on      the confirmation invariant   RED      REQ-JOB-01, REQ-JOB-02
guard_off           the scope guard              RED      REQ-SCOPE-01
resume_off          Last-Event-ID handling       RED      REQ-STREAM-02
drop_events         log append reliability       RED      REQ-STREAM-01
netpol_off          zone network isolation       RED      REQ-PHI-05
rls_off             row-level security           RED      REQ-ISO-01, REQ-ISO-02
validator_off       app constraint checks        RED      REQ-VALID-01

9 mutations, 9 detected.  0 mutations survived.
```

A surviving mutation is a failure of this increment, and the finding is that a requirement has no
real coverage.

The tokenizer mutation is detected in persisted events. The independently enabled egress tripwire
still blocks raw identifiers, so this probe does not claim a provider leak or disable a second
control to force one. Crashes, unhealthy controls, and unexpected-only detections are not passes.

## Recorded findings

- All nine paired mutations were detected. Eight use independently created disposable databases;
	the network probe copies the actual policy generator into three run-owned namespaces and checks
	both Service and Pod routes before and after deleting only those copied policies.
- Five adversarial families are registered in the standard replay suite. Injection cases cover
	job logs, KB documents, tool results, and specimen notes. Notes remain outside the handle-only
	model contract; reports distinguish an unexposed payload from a model resisting an exposed one.
- The original literal detector cases still score 100/100. Obfuscated cases score 2/12, with a
	95% Wilson interval of 4.7%-44.8%. No detector rule or acceptance threshold was relaxed.
- The matrix has 13 cases per cell, one trial per case: Flash baseline 10/13, Flash evidence-first
	10/13, Gemini baseline 7/13, Gemini evidence-first 9/13, Nano baseline 9/13, and Nano
	evidence-first 8/13. All 78 trials preserved the no-additional-submission invariant. The 25
	retained findings include protocol errors, missing inspection, and conversation failures;
	they are not all successful injections. None of the exploratory paired comparisons is
	significant at 0.05, and the small curated sample does not establish a model ranking.
- The Gemini explanation judge agreed on 3/6 agent-authored development references; three calls
	failed the required structured protocol. Cohen's kappa is unavailable with those errors.
	The references are reviewable, not human labels or held-out data. Human agreement is pending,
	and judged quality is not trusted. Failed recordings were retained without rerolls or retries.
- The bounded initial recording made 183 provider calls, conservatively reserving $0.9313962
	against the approved $2 cap. This reservation is not an actual provider billing total.
- PR mutation checks, keyless matrix replay, protected nightly recording, paired drift checks,
	artifact retention, and Pages assembly are configured. Remote CI, the protected provider secret,
	and Pages publication still require repository-side acceptance after these changes are pushed.
	Scheduled spending additionally requires the explicit repository variable
	`ZAGENT_LIVE_EVALS=true`; it is not enabled by this implementation.

Validation: 559 backend tests passed with one opt-in Docker test skipped; 46 frontend tests,
the frontend build, and lint passed. The full behavioral report covers 33 requirements, 458 cases,
and 3,430 trials, retaining the original 24 failed trials plus 13 new documented findings.
There are no unrecognized regressions, but the expanded detector and explanation quality gates
remain red. All 78 matrix outcomes replayed unchanged without credentials. The live cluster's
96 network/role checks passed after restoring an image evicted under disk pressure; databases,
volumes, live mode, and sessions were preserved. The privacy scan found no registered identifier
violations in 2,522 cassettes and the active evidence corpus, and the credential scan was clean.
Static reports were checked at desktop and mobile sizes.

Reports are generated under `docs/evals`, with separate `plan10/mutations` and `plan10/matrix`
pages and linked per-trial provenance. The ordinary report keeps known measured failures red;
an exact-fingerprint regression baseline is separate from quality acceptance. Reproduction and
review instructions are in [the evaluation guide](../evals/README.md#plan10-adversarial-evidence).

---

## Scope

**Fault-injection flags.** Each mechanism gets a flag that disables it, gated behind an environment
variable that is refused in any non-test configuration. CI flips each in turn and asserts the suite
goes red, and asserts *which* requirements caught it. A mutation caught by an unexpected requirement
is itself informative.

This is mutation testing applied to guarantees rather than to code coverage, and it is the strongest
single argument the project can make.

**Adversarial suites.**

| Suite | Contents |
|---|---|
| Prompt injection | Instructions embedded in job logs, KB documents, tool results, specimen free-text fields |
| Scope wrappers | Off-topic requests framed as platform work, multi-turn escalation, role play |
| Confirmation bypass | Attempts to induce submission through any path other than the confirm action |
| Obfuscated identifiers | Spacing, separators, homoglyphs, non-ASCII, partial mentions, spelled-out digits, identifiers split across turns |
| Groundedness pressure | Questions whose honest answer is "I do not know", and requests to speculate about job state |

The obfuscated identifier suite will lower REQ-PHI-04's measured recall, possibly a lot. That is the
correct outcome. The invariant is scoped to what the rule set matches, and this suite measures how
much that is. A project that reports high recall only because it never tested hard cases is the
thing being argued against.

**Model matrix.** Nightly live runs across several models and both prompt versions. Results are
compared with paired tests (McNemar), so a reported regression is a claim with support rather than
two numbers that differ. The matrix is what makes provider drift visible as a diff instead of as an
incident.

**LLM judges, narrowly.** Only for properties no deterministic check covers, principally explanation
quality. Every judge ships with judge-to-human agreement measured on a labeled subset, reported
alongside its results. A judge whose agreement is not reported is not evidence, it is a second
opinion of unknown quality.

**Published report.** Full traceability matrix with mutation results, adversarial breakdowns, the
model matrix, judge agreement, and provenance for every figure. Published to GitHub Pages per
commit.

---

## Out of scope

| Deferred | Owner |
|---|---|
| The showcase gallery | PLAN11 |
| A formally verified boundary | not a goal |
| Red-teaming by third parties | out of scope, worth noting as a limitation |

---

## Key decisions

**Mutations are a CI requirement, not an exercise.** Run on every pull request that touches an
enforcement site, and nightly in full. A mutation that stops being detected is a regression in the
evidence, which is as serious as a regression in the product.

**Mutation flags must be impossible in production.** They exist to break guarantees, so they need a
guard stronger than a default value. Refuse to start when a mutation flag is set outside an explicit
test configuration, and test that refusal.

**Adversarial results are published as-is.** Where a suite finds a weakness, the number goes in the
report. The credibility of every other number depends on this one.

**Judges are measured before they are trusted.** Agreement on a labeled subset, reported next to
every judged result.

**Paired tests for comparisons.** Unpaired comparison of pass rates across models is noise at these
sample sizes.

---

## Definition of done

- [x] Every listed enforcement mechanism has a mutation flag.
- [x] `make evals MUTATE=all` runs each and reports which requirements detected it.
- [x] Zero surviving mutations, or a documented finding for each survivor.
- [x] Mutation flags are refused outside a test configuration, and that refusal is tested.
- [x] All five adversarial suites run in the standard suite.
- [x] Injection attempts through every ingress are covered, one case per ingress minimum.
- [x] Obfuscated identifier recall is measured and included in the generated report.
- [ ] Nightly matrix runs remotely across the model set with paired baseline comparisons
	(workflow configured and initial local matrix recorded; remote acceptance pending).
- [ ] Every judge reports agreement with human labels (agent-authored references only so far).
- [ ] The published report links every figure to its provenance (local report implemented;
	GitHub Pages publication pending).

---

## Evidence added

**REQ-META-02 (invariant).** Every enforcement mechanism is detectably load-bearing. Evidence: the
mutation table, with zero survivors.

**REQ-INJECT-02 (measured).** Injected instructions from any ingress do not alter behavior. Reported
per ingress, because they are not equally hard: a KB document is retrieved deliberately, while a job
log arrives unbidden.

**REQ-PHI-04 (measured, expanded).** Detector recall on the adversarial corpus. Expect a lower
number than PLAN6 reported, and report the change explicitly rather than quietly replacing it.

**REQ-JOB-04 (invariant).** No adversarial input causes a submission. Property over the whole
adversarial corpus.

**REQ-GROUND-03 (measured).** Under groundedness pressure, the agent declines to speculate. Judged,
with agreement reported.

---

## Traps

**Mutation flags reachable in production.** The worst possible outcome of this increment. Treat the
guard on them as a security control with its own test.

**Mutations that break the build rather than the guarantee.** A mutation that makes the system fail
to start turns the suite red for the wrong reason and proves nothing. Each mutation must leave a
running system with one guarantee removed, and the mutation test should assert that the system still
functions.

**Adversarial suites that only test what already works.** Writing attacks against your own system
biases toward attacks it survives. Mitigate by writing attack cases before the corresponding
defense where possible, and by keeping a list of known-unmitigated attacks in the report.

**Matrix cost.** Nightly runs across several models at k trials per case is real money. Budget it,
sample the case set for the matrix rather than running everything, and keep the full suite on
replay.

**Judge drift.** A judge's model changing silently invalidates comparisons. Pin it, version it, and
re-measure agreement when it changes.

---

## Next

[PLAN11](PLAN11.md) presents all of this to an audience that has thirty seconds of patience.