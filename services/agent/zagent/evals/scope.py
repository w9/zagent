import asyncio
import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from zagent.evals.assertions import Evidence, check_case, refusal_invariants, render_transcript
from zagent.evals.schema import Case, Provenance, ScopeOutcome, TrialResult
from zagent.events import Event, project
from zagent.gateway import configured_gateway
from zagent.llm import CompletionRequest, LlmGateway, canonical_json, normalized_request
from zagent.scope import GUARD_PROMPT, GUARD_TOOLS, SCOPE_POLICY_HASH, ScopeGuard


def case_events(case: Case) -> list[Event]:
    session_id, turn_id = uuid4(), uuid4()
    events = []

    def append(kind: str, payload: dict) -> None:
        events.append(
            Event(
                type=kind,
                payload=payload,
                seq=len(events) + 1,
                session_id=session_id,
                conversation_turn_id=turn_id,
                created_at=datetime.now(UTC),
            )
        )

    for message in case.context:
        if message.role == "user":
            turn_id = uuid4()
            append("user_message", {"message_id": str(uuid4()), "text": message.content})
        else:
            message_id = str(uuid4())
            append("text_delta", {"message_id": message_id, "text": message.content})
            append("message_done", {"message_id": message_id})
    if case.draft is not None:
        append("draft_updated", {"draft": case.draft})
    turn_id = uuid4()
    append("user_message", {"message_id": str(uuid4()), "text": case.conversation_turns[0].user})
    append("conversation_turn_started", {})
    return events


async def evaluate_scope_trial(
    case: Case,
    root: Path,
    gateway: LlmGateway,
    *,
    sample: int,
    commit: str | None = None,
    dirty: bool | None = None,
    disable_guard: bool = False,
) -> TrialResult:
    started, clock = time.perf_counter(), datetime.now(UTC)
    events = case_events(case)
    current = events[-1]
    turn_id = str(current.conversation_turn_id)
    failures = []
    actual = None
    execution_error = False

    def append(kind: str, payload: dict) -> None:
        events.append(
            Event(
                type=kind,
                payload=payload,
                seq=len(events) + 1,
                session_id=current.session_id,
                conversation_turn_id=current.conversation_turn_id,
                created_at=clock,
            )
        )

    try:
        rejected = (
            None
            if disable_guard
            else await ScopeGuard(gateway, route=case.agent.removeprefix("guard:")).classify(
                events,
                sample=sample,
                metadata={
                    "session_id": str(current.session_id),
                    "conversation_turn_id": turn_id,
                },
            )
        )
        if rejected:
            actual = rejected.code
            append("refused", rejected.model_dump())
        append("conversation_turn_finished", {})
    except Exception as error:
        execution_error = True
        detail = f"{type(error).__name__}: {error}"
        failures.append(f"{case.id}: {detail}")
        append("conversation_turn_failed", {"error": detail})

    audits = await asyncio.to_thread(gateway.audit_for_turn, turn_id)
    if not disable_guard and (len(audits) != 1 or audits[0]["purpose"] != "scope_guard"):
        failures.append(f"{case.id}: expected exactly one audited scope call")
        execution_error = True
    evidence = Evidence(events, project(current.session_id, events))
    structural = refusal_invariants(evidence, case.id)
    failures.extend(check_case(case, evidence, root))
    expected = None if case.expect["refusal"] == "none" else case.expect["refusal"]["code"]
    route = gateway.routes[case.agent.removeprefix("guard:")]
    return TrialResult(
        case_id=case.id,
        verification="standard",
        seed=sample,
        passed=not failures,
        failures=failures,
        transcript=render_transcript(evidence),
        session_id=str(current.session_id),
        duration_seconds=time.perf_counter() - started,
        executions=0,
        scope=ScopeOutcome(
            expected=expected,
            actual=actual,
            error=execution_error,
            structured=not structural,
            gateway_calls=len(audits),
            provider_calls=sum(item["provider_calls"] for item in audits),
        ),
        requirement_outcomes={
            "REQ-SCOPE-01": not execution_error and actual is not None,
            "REQ-SCOPE-02": not execution_error and actual is None,
            "REQ-SCOPE-03": not structural,
        },
        provenance=Provenance(
            commit=commit,
            dirty_worktree=dirty,
            agent_implementation="ScopeGuard",
            seed=sample,
            clock=clock,
            mode=gateway.mode,
            model=route.model,
            prompt_hash=normalized_request(
                CompletionRequest(
                    messages=[
                        {
                            "role": "system",
                            "content": GUARD_PROMPT,
                        }
                    ]
                ),
                route,
            )["prompt_hash"],
            tool_schema_hash=hashlib.sha256(canonical_json(GUARD_TOOLS).encode()).hexdigest(),
            scope_hash=SCOPE_POLICY_HASH,
            independent_sample=sample,
            mutation="disable_scope_guard" if disable_guard else None,
        ),
    )


async def evaluate_scope_cases(
    cases: list[Case],
    root: Path,
    *,
    mode: str,
    trials: int,
    seed: int,
    commit: str | None,
    dirty: bool | None,
    concurrency: int = 8,
    disable_guard: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> list[TrialResult]:
    gateway = configured_gateway(mode)
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(cases) * trials

    async def evaluate(case: Case, sample: int):
        nonlocal completed
        async with semaphore:
            result = await evaluate_scope_trial(
                case,
                root,
                gateway,
                sample=sample,
                commit=commit,
                dirty=dirty,
                disable_guard=disable_guard,
            )
            completed += 1
            if progress and (completed % 100 == 0 or completed == total):
                progress(completed, total)
            return result

    return await asyncio.gather(
        *(evaluate(case, sample) for case in cases for sample in range(seed, seed + trials))
    )
