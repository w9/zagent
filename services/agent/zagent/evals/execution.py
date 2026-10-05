import asyncio
import hashlib
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from zagent.agent import MAIN_TOOLS, SYSTEM_PROMPT, LlmAgent
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.dispatcher import Dispatcher
from zagent.evals.assertions import ASSERTIONS, check_case, render_transcript, view_invariants
from zagent.evals.environment import local_api
from zagent.evals.local_knowledge import current_snapshot, local_tools
from zagent.evals.privacy import private_gateway
from zagent.evals.schema import Provenance, TrialResult
from zagent.evals.simulator import SampleGateway
from zagent.executors import ProcessExecutor
from zagent.jobs import JobStore
from zagent.llm import CompletionRequest, canonical_json, normalized_request
from zagent.scope import SCOPE_POLICY_HASH
from zagent.store import Store
from zagent.tools import ToolsGateway


class InterruptOnce:
    resumable = True

    def __init__(self, agent, boundary, interrupted):
        self.agent, self.boundary, self.interrupted = agent, boundary, interrupted

    async def run_turn(self, session, emit):
        async def record(event):
            if event.type == self.boundary and not self.interrupted.is_set():
                if event.type == "text_delta":
                    await emit(event)
                self.interrupted.set()
                raise asyncio.CancelledError()
            await emit(event)

        await self.agent.run_turn(session, record)


def requirement_outcomes(case, evidence, root):
    checks = {
        "REQ-EXEC-01": ["job_outcomes"],
        "REQ-EXEC-02": ["egress", "event_log"],
        "REQ-VIEW-03": ["view_references"],
        "REQ-RESUME-01": ["runtime_resumed"],
        "REQ-GROUND-02": ["job_narration", "sop_citations"],
        "REQ-INJECT-01": ["log_injection_resisted", "job_narration"],
    }
    outcomes = {}
    for identity, assertions in checks.items():
        selected = [name for name in assertions if name in case.expect]
        if selected:
            outcomes[identity] = all(
                ASSERTIONS[name](evidence, case.expect[name], root, case.id) is None
                for name in selected
            )
    from zagent.privacy import Detector

    outcomes["REQ-EXEC-02"] = outcomes.get("REQ-EXEC-02", True) and not Detector().contains(
        evidence.job_data
    )
    if "REQ-VIEW-03" in outcomes:
        outcomes["REQ-VIEW-03"] &= not view_invariants(evidence, case.id)
    return outcomes


async def evaluate_execution(
    case, root, database_url, *, mode, trials, seed, record_missing, commit, dirty
):
    from zagent.evals.runner import capture_case

    store = await Store.open(database_url)
    results = []
    try:
        await store.migrate(seed=False)
        clinical = ClinicalStore(store, lambda: FROZEN_NOW)
        await clinical.seed()
        version = current_snapshot()
        if version != case.execution.kb_version:
            raise ValueError("Recorded execution case requires a different knowledge version")
        gateway = private_gateway(mode, store.privacy, record_missing=record_missing)
        for sample in range(seed, seed + trials):
            started = time.perf_counter()
            evidence, failures, outcomes = None, [], {}
            sampled = SampleGateway(gateway, sample)
            agent = LlmAgent(
                store,
                sampled,
                ToolsGateway(store, local_tools(clinical)),
            )
            interrupted = asyncio.Event()

            try:
                with TemporaryDirectory(prefix="zagent-execution-") as directory:
                    executor = ProcessExecutor(Path(directory))
                    try:
                        async with local_api(database_url, agent) as environment:
                            runtime = environment.app.state.runtime
                            recovery = None
                            if case.execution.interrupt:
                                runtime.agent = InterruptOnce(
                                    agent, case.execution.interrupt, interrupted
                                )

                                async def recover(
                                    interrupted=interrupted, runtime=runtime, agent=agent
                                ):
                                    await interrupted.wait()
                                    await asyncio.gather(
                                        *list(runtime.tasks.values()), return_exceptions=True
                                    )
                                    runtime.agent = agent
                                    await runtime.recover()

                                recovery = asyncio.create_task(recover())
                            try:
                                initial = case.model_copy(update={"workflow_actions": ["confirm"]})
                                evidence = await capture_case(
                                    environment.client,
                                    initial,
                                    timeout_seconds=600 if mode != "replay" else 30,
                                )
                                dispatcher = Dispatcher(JobStore(clinical), executor, interval=0.01)
                                while await dispatcher.once(evidence.projection.session_id):
                                    pass
                                followup = case.model_copy(
                                    update={
                                        "conversation_turns": case.execution.followups,
                                        "workflow_actions": [],
                                    }
                                )
                                evidence = await capture_case(
                                    environment.client,
                                    followup,
                                    previous=evidence,
                                    timeout_seconds=600 if mode != "replay" else 30,
                                )
                                if case.execution.confirm_rerun:
                                    last = next(reversed(evidence.projection.drafts.values()))
                                    if last.status != "editing" or last.validation:
                                        raise AssertionError(
                                            "A valid new corrected draft was not prepared"
                                        )
                                    review = case.model_copy(
                                        update={
                                            "conversation_turns": [],
                                            "workflow_actions": ["confirm"],
                                        }
                                    )
                                    evidence = await capture_case(
                                        environment.client, review, previous=evidence
                                    )
                                    while await dispatcher.once(evidence.projection.session_id):
                                        pass
                                evidence.job_data = []
                                for job_id in evidence.projection.jobs:
                                    response = await environment.client.get(
                                        f"/sessions/{evidence.projection.session_id}/jobs/{job_id}",
                                        params={"representation": "model"},
                                    )
                                    response.raise_for_status()
                                    evidence.job_data.append(response.json())
                                evidence.resumed = interrupted.is_set()
                                failures.extend(check_case(case, evidence, root, skip_golden=True))
                                outcomes = requirement_outcomes(case, evidence, root)
                                if runtime.titles:
                                    await asyncio.gather(*runtime.titles.tasks)
                            finally:
                                if recovery:
                                    recovery.cancel()
                                    await asyncio.gather(recovery, return_exceptions=True)
                    finally:
                        executor.close()
            except Exception as error:
                failures.append(f"{case.id}: {type(error).__name__}: {error}")
            results.append(
                TrialResult(
                    case_id=case.id,
                    verification="standard",
                    seed=sample,
                    passed=not failures,
                    failures=failures,
                    requirement_outcomes=outcomes,
                    transcript=render_transcript(evidence) if evidence else "",
                    session_id=str(evidence.projection.session_id) if evidence else None,
                    duration_seconds=time.perf_counter() - started,
                    executions=1,
                    privacy_requests=len(evidence.requests) if evidence else 0,
                    interruption={
                        "boundary": case.execution.interrupt,
                        "resumed": interrupted.is_set(),
                    }
                    if case.execution.interrupt
                    else None,
                    provenance=Provenance(
                        commit=commit,
                        dirty_worktree=dirty,
                        agent_implementation="LlmAgent+ProcessExecutor",
                        seed=sample,
                        clock=FROZEN_NOW,
                        mode=mode,
                        model=gateway.routes["default"].model,
                        kb_version=version,
                        independent_sample=sample,
                        scope_hash=SCOPE_POLICY_HASH,
                        prompt_hash=normalized_request(
                            CompletionRequest(
                                messages=[{"role": "system", "content": SYSTEM_PROMPT}]
                            ),
                            gateway.routes["default"],
                        )["prompt_hash"],
                        tool_schema_hash=hashlib.sha256(
                            canonical_json(MAIN_TOOLS).encode()
                        ).hexdigest(),
                    ),
                )
            )
            print(
                f"{case.id} sample {sample}: {'passed' if not failures else 'failed'}",
                file=sys.stderr,
            )
    finally:
        await store.close()
    return results
