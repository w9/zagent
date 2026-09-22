# PLAN9: The Cluster

**Status:** not started
**Depends on:** [PLAN8](PLAN8.md)
**Shippable outcome:** the whole system runs on a local Kubernetes cluster from one command, and
the zone boundary is enforced by network policy rather than described in a document.

---

## Goal

Extract the services and make the privacy boundary physical.

Kubernetes has been deferred to here for a reason. Until this point a cluster would have added
iteration latency and nothing else, because there were no zones to separate. Now there are, and
the boundary described in [ARCHITECTURE section 6](ARCHITECTURE.md#6-zones-and-the-privacy-boundary)
becomes a thing that holds rather than a thing that is claimed.

---

## What you can see when it's done

`make cluster` brings the whole system up on k3d with Tilt, with live reload on code changes.
Everything that worked under Compose still works.

Then: exec into the agent runtime's pod and try to reach the clinical database. It fails at the
network layer. Try to reach the internet from anywhere other than the LLM gateway. It fails. Those
two commands are now tests in the suite.

---

## Scope

**Service extraction.** The module boundaries have been maintained since PLAN1 on the assumption
that this would be mechanical. If it is not mechanical, the boundaries were dishonest and fixing
them is part of this increment.

| Deployment | Zone |
|---|---|
| `web` | Clinical |
| `privacy` | Clinical |
| `tools-gateway` | Clinical |
| `dispatcher` | Clinical |
| `kb` | Neutral |
| `agent-runtime` | Agent |
| `llm-gateway` | Agent |
| `eval-runner` (Job / CronJob) | Agent |
| `postgres` | Split by role |
| `otel-collector`, `tempo` | Neutral |

**Namespaces and NetworkPolicy.** One namespace per zone, default-deny ingress and egress in both,
then explicit allows. The rules that matter:

- The agent zone has no route to the clinical database or to the privacy service's resolve
  endpoint.
- The LLM gateway is the only pod with internet egress.
- Job pods can reach the clinical database and nothing else.

**Postgres roles.** The event log and clinical tables are separated by database role, with row-level
security on the clinical tables. The agent zone's credentials cannot read clinical tables even if
the network allowed it, which is the defense-in-depth pairing.

**Kubernetes Jobs as the execution unit.** The dispatcher's second implementation, substituted for
the Compose container runner behind the interface built at PLAN8. Retries, backoff and TTL move
into the Job spec.

**Tilt for the dev loop.** Live reload, port forwarding, and a single command. If working on the
cluster is slower than working on Compose, people will work on Compose and the cluster will rot.
Keep Compose working as the fast path for front-end work.

**One-command bring-up, and it must stay true.** `make cluster` from a clean clone on a machine
with Docker and nothing else. This is what makes the repository usable by someone evaluating it,
which is a large part of the project's purpose.

---

## Out of scope

| Deferred | Owner |
|---|---|
| Fault injection proving the policies are load-bearing | PLAN10 |
| Cloud deployment, Helm charts for real clusters | not a goal |
| Autoscaling, resource tuning, cost work | not a goal |
| Service mesh, mTLS | not a goal. NetworkPolicy is sufficient for the claim being made |
| Secrets management beyond Kubernetes Secrets | not a goal |

---

## Key decisions

**NetworkPolicy, not a service mesh.** The claim is that the agent zone cannot reach clinical data.
NetworkPolicy makes that claim and is testable in twenty lines. A mesh would add a large operational
surface to make a claim that is already made.

**Default-deny both directions.** An allowlist that starts from deny is auditable. One that starts
from allow is a list of things someone remembered.

**Verify the CNI actually enforces policy.** This is the trap that makes the whole increment
decorative if missed. Several local Kubernetes distributions ship without a policy-enforcing CNI, in
which case `NetworkPolicy` objects are accepted and silently ignored. k3d with k3s enforces by
default. Assert it: the suite includes a negative connectivity test that must fail, and a test that
the test itself is meaningful.

**Keep Compose.** Two paths is a small maintenance cost and a large iteration-speed benefit.

**Roles and RLS as well as network policy.** Either alone is a single point of failure.

---

## Definition of done

- [ ] `make cluster` brings everything up on k3d from a clean clone.
- [ ] Tilt gives live reload on both backend and front-end changes.
- [ ] The full evidence suite passes against the cluster, unchanged.
- [ ] `make up` (Compose) still works.
- [ ] Jobs run as Kubernetes Jobs, with retries visible in the job card's history.
- [ ] A connection attempt from `agent-runtime` to the clinical database fails at the network layer.
- [ ] A connection attempt to the internet from any pod except `llm-gateway` fails.
- [ ] The agent zone's database role cannot read clinical tables.
- [ ] A test proves the CNI enforces policy, so the negative tests are meaningful.
- [ ] Traces from a full conversation, including job execution, are viewable in Tempo.

---

## Evidence added

**REQ-PHI-05 (invariant).** The agent zone has no network route to clinical data. Tested by
attempted connection from inside the pod, which must be refused.

**REQ-PHI-06 (invariant).** Only the LLM gateway has internet egress. Tested per pod.

**REQ-ISO-02 (invariant).** The agent zone's database credentials cannot read clinical tables.
Tested directly against the role.

**REQ-META-01 (invariant).** The policy enforcement mechanism is active. A test that asserts a
connection which *should* be allowed succeeds, so a wholesale networking failure cannot be mistaken
for correct enforcement.

That last requirement is worth stating explicitly. A negative test passes when nothing works at
all, which means a broken cluster looks identical to a well-secured one. The positive control is
what distinguishes them.

---

## Traps

**A CNI that ignores NetworkPolicy.** The single most important check in this increment, and the
easiest to skip. Without enforcement, the network half of the privacy story is decoration.

**Negative tests that pass for the wrong reason.** Covered by REQ-META-01. Every deny test needs a
paired allow test.

**Extraction revealing hidden coupling.** Services that shared a process may have shared a
transaction or an in-memory cache. Where that surfaces, fix the coupling rather than reintroducing
it across a network boundary.

**The dev loop getting slower.** Measure the edit-to-visible-change time before and after. If it
grows by more than a few seconds, fix it before moving on, because every later increment pays that
cost repeatedly.

**Suite runtime growing.** The suite must stay in the tens of seconds in replay mode. A cluster adds
startup cost, so the suite should run against a persistent cluster rather than bringing one up per
invocation.

---

## Next

[PLAN10](PLAN10.md) attacks all of it, and proves the evidence can actually detect a broken build.