# PLAN9: The Cluster

**Status:** implemented; full-replay latency target remains open
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
| `bff`, `jobs` | Clinical |
| `privacy` | Clinical |
| `tools-gateway` | Clinical |
| `dispatcher` | Clinical |
| `kb` | Neutral |
| `agent-runtime` | Agent |
| `llm-gateway` | Agent |
| `eval-runner` (Job) | Agent |
| `evidence-runner` (trusted test Job) | Clinical |
| `postgres` | Clinical, split by database role |
| `event-db` (role-pinned PgBouncer) | Neutral |
| `otel-collector`, `tempo`, `grafana` | Neutral |

**Namespaces and NetworkPolicy.** One namespace per zone, default-deny ingress and egress in all,
then explicit allows. The rules that matter:

- The agent zone has no route to the clinical database or to the privacy service's resolve
  endpoint.
- The LLM gateway is the only application pod with public HTTPS egress.
- Worker Job pods can reach the clinical database plus cluster DNS, and nothing else.

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
which case `NetworkPolicy` objects are accepted and silently ignored. The initial k3s kube-router
configuration enforced policy on stable pods but allowed a fresh worker's first public connection
before policy reconciliation. This implementation therefore disables Flannel/kube-router and
installs checksum-pinned Calico VXLAN, including CNI policy-readiness gating. Tests execute inside
real pod network namespaces and immediately in fresh worker/eval Jobs; no test delay conceals
startup exposure. Allowed DNS, service, database, and dispatcher API connections are positive
controls. CNI/control-plane infrastructure is outside the application namespace egress claim.

**Keep Compose.** Two paths is a small maintenance cost and a large iteration-speed benefit.

**Roles and RLS as well as network policy.** Either alone is a single point of failure.

---

## Definition of done

- [ ] `make cluster` brings everything up on k3d from a clean clone.
- [x] Tilt gives live reload on both backend and front-end changes.
- [x] The full evidence suite passes against the cluster, unchanged.
- [x] `make up` (Compose) still works.
- [x] Jobs run as Kubernetes Jobs, with retries visible in the job card's history.
- [x] A connection attempt from `agent-runtime` to the clinical database fails at the network layer.
- [x] A connection attempt to the internet from every application pod except `llm-gateway` fails.
- [x] The agent zone's database role cannot read clinical tables.
- [x] A test proves the CNI enforces policy, so the negative tests are meaningful.
- [x] Traces from a full conversation, including job execution, are viewable in Tempo.

One-command startup, repeat startup, and VM-restart recovery have been exercised locally. The
clean-clone CI job is wired but has not been run in this worktree; existing local volumes were
preserved rather than deleted to simulate a clean machine.

## Implemented Workflow

`make cluster` builds Docker-hosted tooling, installs the CNI, generates scoped Secrets, runs
schema/role initialization, starts one Tilt process, and waits for its resources. The ordinary
shell prerequisites are Docker, Git, Make, and Bash; application runtimes and cluster tools are
inside images. The app is at `http://localhost:5185`, API at `http://localhost:8109`, Tilt at
`http://localhost:10359`, and Tempo at `http://localhost:3284`. Tilt port forwards avoid a
cross-node NodePort reset found on the local Lima setup and require no broad display ingress.

The event database proxy forces `zagent_runtime` on its single backend mapping and uses session
pooling for LISTEN/advisory locks. It has no owner credential or alternate database mapping.
The privacy pod exposes full resolution on 8003 and tokenize/tripwire only on 8006. Policies
separate these ports; this is not a claim that NetworkPolicy filters HTTP paths. The neutral KB
service has no database or privacy capability.

One confirmed analysis maps to one deterministic Kubernetes Job. `backoffLimit: 1` permits one
replacement pod; exit code 2 ends domain failures without retry. Worker admission uses a scoped
database function and private per-job token. Logs are tokenized and deduplicated by attempt and
worker sequence. The dispatcher schedules a one-hour Job TTL only after durable log ingestion
and a persisted terminal receipt. Recovery after TTL deletion finishes bookkeeping from that
receipt without recreating the execution.
Workers have no service-account token, run non-root with a read-only root filesystem, and retain
only the database admission credential. The dispatcher has Job create/read/patch and pod/log
read privileges, not Secret access or a Docker socket.

W3C trace context is persisted with each conversation turn and frozen into confirmed job input.
OTLP spans from HTTP, MCP, database operations, conversation execution, and dispatch reach Tempo.
The deployed workflow verifies a shared trace ID and scans exported trace content for known
identifier leakage. Worker logs use the originating trace ID without needing telemetry egress.

## Verified Evidence

Measured on the local four-CPU arm64 Lima VM on 2026-09-23:

| Check | Result |
|---|---|
| `make cluster-test` | 96 checks across 15 workload identities, 11.36 seconds |
| Full backend tests in a clinical test Job | 499 passed, 1 opt-in Docker test skipped |
| Unchanged full replay harness in that Job | All 29 gates pass, 3,405 trials, 330 HTTP captures, 328.48 seconds |
| Agent-zone database-free scope Job | 3,000 samples, 13.65 seconds, gates pass |
| Deployed-service workflow gate | All 16 ordinary real-agent goldens, success/failure/retry executions, Tempo; 46.92 seconds |
| Frontend unit tests and build | 46 tests pass; production build passes |
| Real-agent browser tests | 22 desktop/mobile checks pass on cluster and rebuilt Compose |
| In-place reload with an open conversation | Frontend 0.82 seconds; backend 3.12 seconds, same pod |
| Actual Docker reattachment | Passed against the final rebuilt Compose image |

The 24 pre-existing recorded scope/provider failures remain in evidence: no requests were rerolled,
no goldens were changed, and replay made no provider calls. The full privacy scan found zero known
identifier violations across 2,339 cassettes, 25 goldens, 15,409 stored events, and 8,960 requests.

The unchanged harness starts controlled production-app instances inside the trusted clinical test
Job and uses a separate test database; its native process executor remains deliberate. It is not
misrepresented as routing all 3,405 trials through deployed services. The additional workflow gate
uses deployed BFF/runtime/privacy/MCP/gateway services, unchanged golden assertions, actual
Kubernetes Jobs, and Tempo. The four deployment requirements below have their own executable
policy report and CI gate, separate from the 29 behavioral requirement rows.

The full replay target of tens of seconds is **not met**: the baseline itself takes minutes, and
this run took 328.48 seconds before unit tests and deployed workflows. The 11-second boundary gate
and 47-second deployed gate are available independently against the persistent cluster.

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