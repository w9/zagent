# PLAN2: The Evidence Harness

**Status:** not started
**Depends on:** [PLAN1](PLAN1.md)
**Shippable outcome:** `make evals` prints a traceability report, and any behavior change shows
up as a reviewable diff in a checked-in golden file.

---

## Goal

Build the measurement apparatus second, not last.

This ordering is the single most consequential scheduling decision in the project. A harness
added at the end tests whatever the code happens to expose, which in practice means internals,
which means it can pass while the real path is broken. A harness added now defines the interface
every later increment is built against, and it makes each of those increments verifiable the day
it lands.

There is still no LLM. The harness is proven against `ScriptedAgent`, where expected output is
exactly known.

---

## What you can see when it's done

A terminal report:

```
$ make evals

REQ-STREAM-01  invariant   golden transcripts        12/12   ✓
REQ-STREAM-02  invariant   resume after interrupt    50/50   ✓

2 requirements, 62 trials, 0 failures.  Report: docs/evals/index.html
```

And an HTML report with the same content plus per-case detail: the transcript, the diff when one
fails, and the recorded provenance.

Most importantly: change a prompt or a reducer, run `make evals`, and see a diff of what the
agent now does differently. That is the mechanism that makes every subsequent increment safe.

---

## Scope

**Requirement register.** `evals/requirements.yaml`, in the shape described in
[ARCHITECTURE section 17](ARCHITECTURE.md#17-requirement-register). Each entry: id, tier,
statement, enforcement sites or threshold, linked cases, and for invariants the mutations that
must break them. Two requirements exist at this point, both from PLAN1.

**Case format.** YAML, one file per group. A case names turns and expectations.

```yaml
id: STREAM-004
requirement: REQ-STREAM-01
agent: scripted:multi_paragraph
turns:
  - user: "summarize the samples"
expect:
  golden: goldens/STREAM-004.txt
  events_include: [run_started, text_delta, message_done, run_finished]
  events_exclude: [run_failed]
```

Later plans extend the `expect` vocabulary (`tool_calls`, `views`, `egress`, `refusal`,
`draft`). Adding an assertion kind should mean adding one function to the assertion registry,
not touching the runner.

**The runner.** Drives cases through the **public HTTP API**, the same endpoints the browser
uses. It creates a session, posts turns, tails the event feed, and collects the log. Two entry
points over one implementation:

- `pytest` imports it, so cases run in the normal development loop.
- `zagent evals [--filter] [--trials N] [--update-golden] [--mode replay|live]` runs it as a CLI.

There is no third path. If the runner cannot express a check, the API is missing something and
that is the finding.

**Golden transcripts.** The normalizer from PLAN1 produces a stable text form. `--update-golden`
rewrites the files, and review of that diff is the actual verification step. Normalization must
redact ids, timestamps, durations and any other nondeterminism, and must fail loudly if it
encounters an unredacted value that changes between runs.

**Chaos as a harness mode.** `zagent evals --chaos` reruns any case with seeded interruptions at
the connection layer and at the run layer, then diffs the recovered transcript against the
uninterrupted golden. Every case written from here on gets chaos coverage for free, which is
the payoff for building this now.

**Statistics module.** Wilson interval, `pass^k`, and a paired comparison against a stored
baseline. It handles one trial per case correctly today and multiple trials per case from PLAN5
onward, so nothing about the reporting has to change when nondeterminism arrives.

**Provenance.** Every result records commit, agent implementation, seed, clock value, and
placeholders for the fields that arrive later (model, prompt hash, tool schema hash, KB
version). Provenance fields are cheap to add now and awkward to backfill.

**Reporting.** A terminal table and a static HTML report generated into `docs/evals/`, published
by CI to GitHub Pages. README badges point at it.

**CI.** Pull requests run the full suite plus chaos. Nothing is gated on a live provider, so the
suite stays free and non-flaky.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Multiple trials with real nondeterminism | PLAN5, where the first measured requirement appears |
| Simulated users with hidden goals | PLAN7 |
| Fault-injection mutations | PLAN10 |
| Model matrix and nightly live runs | PLAN10 |
| LLM judges | PLAN10, and only for properties no deterministic check covers |

Build the shape for trials and mutations now. Do not build the mechanisms until there is
something to measure.

---

## Key decisions

**Cases drive the public API.** Slower than calling internals, and worth it. The failure this
prevents is a green suite over a broken product, which is the specific failure the project
exists to argue against.

**Golden files are reviewed, not just compared.** The workflow is: change code, run
`--update-golden`, read the diff, commit it if intended. This makes behavior change a code
review artifact. It also means a golden diff in a pull request that was not discussed is itself
a finding.

**Assertions are structural wherever possible.** Prefer asserting on an event than on prose. The
corollary is a standing design rule for later plans: if a behavior is worth verifying, it needs
a structured event. That rule is why PLAN5 makes refusal a tool rather than a phrasing.

**The report is a traceability matrix, not a test log.** It is organized by requirement, and a
requirement with no cases is a visible gap rather than a silent one.

---

## Definition of done

- [ ] `zagent evals` runs every case through the HTTP API and prints a per-requirement table.
- [ ] `zagent evals --update-golden` rewrites goldens, and the diff is readable.
- [ ] `zagent evals --chaos` reruns every case with seeded interruptions.
- [ ] `pytest` runs the same cases with no separate assertions.
- [ ] `make report` produces `docs/evals/index.html`, published by CI.
- [ ] A requirement with zero linked cases is reported as uncovered, not omitted.
- [ ] Deliberately breaking the reducer produces a readable golden diff naming the case.
- [ ] Deliberately breaking resume turns REQ-STREAM-02 red.

The last two items are the acceptance test for the harness itself.

---

## Evidence added

No new requirements. This increment is what reports on requirements, and the two existing ones
move from hand-written tests into the harness.

One thing to record: the wall-clock duration of a full replay-mode run. It should stay in the
tens of seconds. When it stops being fast, it stops being run, and that is the beginning of the
end for the whole approach.

---

## Traps

**Hidden nondeterminism in normalization.** Ordering of concurrently appended events, map
iteration order in payloads, and locale-dependent formatting all produce flaky goldens, which
destroys trust in the mechanism faster than anything else. Make the normalizer assert on
determinism rather than paper over it: run each golden case twice in CI and require identical
output.

**Golden churn.** If an unrelated change rewrites every golden, the diffs stop being read. Keep
normalized transcripts minimal and semantic. Payload fields go into the golden only when an
assertion depends on them.

**Runner and product diverging on setup.** If the runner seeds state directly in the database
while the product seeds through an API, the two drift. Seed through one path.

**The report overstating coverage.** A requirement with cases is not the same as a requirement
that is covered. Report trial counts next to every pass, including invariants, so a requirement
with three trials cannot be visually mistaken for one with three hundred.

---

## Next

[PLAN3](PLAN3.md) adds the right panel, and is the first increment where the harness earns its
keep on something new.