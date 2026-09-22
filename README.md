# Zagent

**An auditable LLM agent for clinical genomics operations.**

[![evals](https://img.shields.io/badge/evals-see%20report-blue)](https://w9.github.io/zagent/evals/)
[![replay CI](https://img.shields.io/badge/CI-replay%20mode-green)](#running-the-evidence-suite)
[![license](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

Most agent demos show a happy path. Zagent is built to answer the question a stakeholder
actually asks after the demo: **how do you know it behaves that way every time?**

It is a working agent over a synthetic pediatric genomics platform. You can ask it about
samples, start analysis jobs, and watch them run. It refuses off-topic requests. Patient
identifiers never reach the model provider. And every one of those claims ships with
machine-checked evidence, regenerated on every commit.

> **Synthetic data only.** Every hospital, patient, sample and result in this repository is
> invented. See [Scope and disclaimers](#scope-and-disclaimers).

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
| Streams survive refresh, tab close and reconnect | Invariant | Server-side runs over an append-only event log | Chaos suite with transcript diffing |
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
  transcript against an uninterrupted run of the same case.

---

## Quick start

Replay mode is the default. It needs no API key, makes no network calls, and is deterministic,
so the demo and the full evidence suite run identically on your laptop and in CI.

```bash
git clone https://github.com/w9/zagent && cd zagent
make up            # Postgres, agent, web. Seeds the synthetic cohort.
open http://localhost:5173
```

```bash
make evals         # the full suite in replay mode. No key, no cost.
make chaos         # 50 interrupted runs, diffed against goldens.
make report        # regenerate docs/evals/index.html
```

To run against a live provider:

```bash
cp .env.example .env    # set ZAGENT_LLM_PROVIDER and the matching key
make up MODE=live
make evals MODE=live    # records new cassettes as it goes
```

---

## Things to try

Each of these exercises a specific row in the guarantee table.

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

The suite is the point of the project, so it is a first-class artifact rather than a test
directory.

Every requirement in [ARCHITECTURE.md](ARCHITECTURE.md) has an ID, a tier, a threshold, and
linked cases. The report is a traceability matrix: requirement, tier, how it is enforced, the
cases that cover it, and the measured result.

```
$ make evals

REQ-STREAM-01  invariant   stream resume            120/120   ✓
REQ-JOB-01     invariant   confirmation required     48/48    ✓
REQ-PHI-01     invariant   no identifier egress     310/310   ✓  (0 tripwire hits)
REQ-SCOPE-01   measured    off-topic refused        147/150   98.0%  [94.3, 99.4]
REQ-SCOPE-02   measured    in-scope not refused     286/300   95.3%  [92.3, 97.3]
REQ-SLOT-01    measured    slot filling converges    88/100   88.0%  [80.2, 93.0]
REQ-GROUND-01  measured    no unsupported claims    194/200   97.0%  [93.6, 98.6]
```

Three properties of this output are deliberate.

**Measured rows report intervals, and gates use the lower bound.** A run of 300 trials at 99%
observed supports roughly 97% at the 95% lower bound. Reporting the point estimate alone
overstates what the evidence can carry.

**Invariant rows count trials too.** Zero tripwire hits in 310 calls bounds the violation rate
below about 1% at 95% confidence. That is the honest reading, and it is why the invariants also
get property tests and network policy tests rather than resting on trial counts.

**The suite is tested against itself.** `make evals MUTATE=all` flips a set of fault-injection
flags one at a time (tokenizer off, submit tool exposed, events dropped on reconnect, scope
guard disabled) and asserts the suite goes red for each. A green suite that cannot detect a
broken build is not evidence. See [PLAN10.md](PLAN10.md).

Replay mode makes all of this free and deterministic. Pull requests run the full suite with no
provider key. Nightly runs go live across a model matrix so provider drift shows up as a diff
instead of a surprise.

---

## Architecture in one paragraph

An append-only per-session event log in Postgres is the spine. Agent runs execute server-side
and append to it. Clients tail it over SSE and resume with `Last-Event-ID`, which is why a
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
| [PLAN1](docs/PLAN1.md) | The spine: event log, SSE resume, scripted agent | ☐ |
| [PLAN2](docs/PLAN2.md) | The evidence harness: golden transcripts, chaos suite | ☐ |
| [PLAN3](docs/PLAN3.md) | The working surface: view specs and the view stack | ☐ |
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