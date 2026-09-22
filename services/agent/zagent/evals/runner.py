import asyncio
import fnmatch
import hashlib
import json
import random
import subprocess
import time
from collections.abc import Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from httpx_sse import aconnect_sse
from pydantic import Field

from zagent.agent import MAIN_TOOLS, SYSTEM_PROMPT, Agent, LlmAgent, ScriptedAgent
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.evals.assertions import (
    Evidence,
    check_case,
    render_transcript,
    transcript_diff,
    validate_expectations,
)
from zagent.evals.environment import PausedAgent, local_api
from zagent.evals.schema import (
    Case,
    Provenance,
    Report,
    StrictModel,
    TrialResult,
    fixture_path,
    load_suite,
)
from zagent.evals.scope import evaluate_scope_cases
from zagent.events import Event, Projection, reduce_event
from zagent.gateway import configured_gateway
from zagent.llm import CompletionRequest, canonical_json, normalized_request
from zagent.scope import SCOPE_POLICY_HASH
from zagent.store import Store
from zagent.tools import McpToolClient, ToolsGateway, create_mcp_server


class ChaosPlan(StrictModel):
    conversation_turn_index: int = Field(ge=0)
    disconnect_after_characters: int = Field(ge=0)
    disconnect_after_view: int | None = Field(default=None, ge=1)
    disconnect_seconds: float = Field(gt=0)
    pause_emit_index: int = Field(ge=1)
    pause_seconds: float = Field(gt=0)
    disconnected_at_seq: int | None = None


def chaos_plan(case: Case, reference: Evidence, seed: int) -> ChaosPlan:
    randomizer = random.Random(seed)
    turn_index = randomizer.randrange(len(case.conversation_turns))
    turn_ids = [
        event.conversation_turn_id for event in reference.events if event.type == "user_message"
    ]
    text_length = sum(
        len(event.payload["text"])
        for event in reference.events
        if event.type == "text_delta" and event.conversation_turn_id == turn_ids[turn_index]
    )
    view_count = sum(
        event.type == "view_pushed" and event.conversation_turn_id == turn_ids[turn_index]
        for event in reference.events
    )
    return ChaosPlan(
        conversation_turn_index=turn_index,
        disconnect_after_characters=randomizer.randint(0, max(0, text_length // 2)),
        disconnect_after_view=randomizer.randint(1, view_count) if view_count else None,
        disconnect_seconds=randomizer.uniform(0.005, 0.035),
        pause_emit_index=1,
        pause_seconds=randomizer.uniform(0.015, 0.045),
    )


def scripted_agent(case: Case, root: Path, plan: ChaosPlan | None = None) -> Agent:
    name = case.agent.removeprefix("scripted:")
    script = None if name == "default" else fixture_path(root, f"scripts/{name}.yaml")
    agent = ScriptedAgent(script, delay_scale=0)
    if plan is None:
        return agent
    return PausedAgent(agent, emit_index=plan.pause_emit_index, seconds=plan.pause_seconds)


@asynccontextmanager
async def case_agent(
    case: Case, root: Path, database_url: str, mode: str = "replay", plan: ChaosPlan | None = None
):
    if case.agent.startswith("scripted:"):
        yield scripted_agent(case, root, plan)
        return
    store = await Store.open(database_url)
    try:
        await store.migrate(seed=False)
        clinical = ClinicalStore(store, lambda: FROZEN_NOW)
        await clinical.seed()
        for table in ("patients", "specimens", "libraries"):
            foreign = await store.pool.fetchval(
                f"SELECT count(*) FROM {table} WHERE site_id = 'lakeside'"
            )
            async with clinical.site_connection("northgate") as connection:
                leaked = await connection.fetchval(
                    f"SELECT count(*) FROM {table} WHERE site_id = 'lakeside'"
                )
            if not foreign or leaked:
                raise AssertionError(f"REQ-ISO-01: wrong-role isolation failed for {table}")
        agent = LlmAgent(
            store,
            configured_gateway(mode),
            ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical))),
            route=case.agent.removeprefix("llm:"),
        )
        yield (
            agent
            if plan is None
            else PausedAgent(agent, emit_index=plan.pause_emit_index, seconds=plan.pause_seconds)
        )
    finally:
        await store.close()


def resume_headers(cursor: int) -> dict[str, str]:
    return {"Last-Event-ID": str(cursor)}


async def capture_case(
    client: httpx.AsyncClient,
    case: Case,
    *,
    plan: ChaosPlan | None = None,
    timeout_seconds: float = 15,
) -> Evidence:
    response = await client.post("/sessions")
    response.raise_for_status()
    session_id = UUID(response.json()["id"])
    state = Projection(session_id=session_id)
    events: list[Event] = []
    for turn_index, turn in enumerate(case.conversation_turns):
        async with asyncio.timeout(timeout_seconds):
            response = await client.post(
                f"/sessions/{session_id}/messages", json={"text": turn.user}
            )
            response.raise_for_status()
            if response.status_code != 202:
                raise AssertionError(f"{case.id}: messages must return 202, not a stream")
            accepted = response.json()
            if accepted["session_id"] != str(session_id):
                raise AssertionError(f"{case.id}: accepted message belongs to another session")
            turn_id = UUID(accepted["conversation_turn_id"])
            text_characters = 0
            pushed_views = 0
            resumed = False
            while True:
                interrupted = False
                terminal = False
                async with aconnect_sse(
                    client,
                    "GET",
                    f"/sessions/{session_id}/events",
                    params={"from": 0 if resumed else state.seq},
                    headers=resume_headers(state.seq) if resumed else {},
                ) as stream:
                    stream.response.raise_for_status()
                    async for frame in stream.aiter_sse():
                        if frame.event != "log":
                            continue
                        event = Event.model_validate_json(frame.data)
                        if frame.id != str(event.seq) or event.seq != state.seq + 1:
                            raise AssertionError(
                                f"{case.id}: noncontiguous SSE cursor; expected {state.seq + 1}, "
                                f"received seq={event.seq}, id={frame.id}"
                            )
                        if event.conversation_turn_id != turn_id:
                            raise AssertionError(
                                f"{case.id}: event belongs to another conversation turn"
                            )
                        state = reduce_event(state, event)
                        events.append(event)
                        if event.type == "text_delta":
                            text_characters += len(event.payload["text"])
                        if event.type == "view_pushed":
                            pushed_views += 1
                        terminal = event.type in {
                            "conversation_turn_finished",
                            "conversation_turn_failed",
                        }
                        if (
                            plan is not None
                            and not resumed
                            and not terminal
                            and turn_index == plan.conversation_turn_index
                            and (
                                pushed_views >= plan.disconnect_after_view
                                if plan.disconnect_after_view is not None
                                else text_characters >= plan.disconnect_after_characters
                            )
                        ):
                            plan.disconnected_at_seq = state.seq
                            interrupted = True
                            break
                if interrupted:
                    await asyncio.sleep(plan.disconnect_seconds)
                    resumed = True
                    continue
                if not terminal:
                    raise AssertionError(
                        f"{case.id}: SSE ended before a terminal conversation-turn event"
                    )
                break
            response = await client.get(f"/sessions/{session_id}/snapshot")
            response.raise_for_status()
            snapshot = Projection.model_validate(response.json())
            if snapshot != state:
                difference = transcript_diff(
                    case.id,
                    render_transcript(Evidence(events, snapshot)),
                    render_transcript(Evidence(events, state)),
                    "http-snapshot",
                )
                raise AssertionError(
                    f"{case.id}: client projection differs from HTTP snapshot\n{difference}"
                )
    if plan is not None and plan.disconnected_at_seq is None:
        raise AssertionError(f"{case.id}: chaos did not interrupt the event feed")
    return Evidence(events, state)


def git_provenance(root: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(dirty)


async def evaluate_case(
    case: Case,
    root: Path,
    database_url: str,
    *,
    standard_trials: int = 1,
    chaos_trials: int = 0,
    seed: int = 0,
    update_golden: bool = False,
    commit: str | None = None,
    dirty_worktree: bool | None = None,
    mode: str = "replay",
) -> list[TrialResult]:
    if min(standard_trials, chaos_trials, seed) < 0 or standard_trials + chaos_trials == 0:
        raise ValueError("Evaluation requires positive trial counts and a nonnegative seed")
    validate_expectations(case, root)
    is_llm = case.agent.startswith("llm:")
    script_digest = None
    model = None
    prompt_digest = None
    if is_llm:
        route = configured_gateway(mode).routes[case.agent.removeprefix("llm:")]
        model = route.model
        prompt_digest = normalized_request(
            CompletionRequest(messages=[{"role": "system", "content": SYSTEM_PROMPT}]), route
        )["prompt_hash"]
    else:
        scripted = scripted_agent(case, root)
        script_digest = hashlib.sha256(
            json.dumps(
                {
                    "script": scripted.script.model_dump(),
                    "failure": scripted.failure.model_dump(),
                    "invalid_view": scripted.invalid_view.model_dump(),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
    results = []
    reference: Evidence | None = None
    reference_failures: list[str] = []
    reference_executions = 0
    reference_started = time.perf_counter()
    reference_clock = datetime.now(UTC)

    def record(
        verification,
        trial_seed,
        evidence,
        failures,
        started,
        clock,
        executions,
        plan=None,
    ) -> None:
        results.append(
            TrialResult(
                case_id=case.id,
                verification=verification,
                seed=trial_seed,
                passed=not failures,
                failures=failures,
                transcript=render_transcript(evidence) if evidence is not None else "",
                session_id=str(evidence.projection.session_id) if evidence is not None else None,
                duration_seconds=time.perf_counter() - started,
                executions=executions,
                provenance=Provenance(
                    commit=commit,
                    dirty_worktree=dirty_worktree,
                    agent_implementation="LlmAgent" if is_llm else "ScriptedAgent",
                    script_sha256=script_digest,
                    seed=trial_seed,
                    clock=FROZEN_NOW if is_llm else clock,
                    mode=mode if is_llm else "replay",
                    model=model,
                    prompt_hash=prompt_digest,
                    tool_schema_hash=hashlib.sha256(canonical_json(MAIN_TOOLS).encode()).hexdigest()
                    if is_llm
                    else None,
                    scope_hash=SCOPE_POLICY_HASH if is_llm else None,
                ),
                interruption=plan.model_dump() if plan is not None else None,
            )
        )

    try:
        async with (
            case_agent(case, root, database_url, mode) as agent,
            local_api(database_url, agent, coalesce_seconds=0.008) as environment,
        ):
            reference_executions += 1
            reference = await capture_case(
                environment.client, case, timeout_seconds=600 if mode != "replay" else 15
            )
            if is_llm and mode == "record":
                agent.gateway.mode = "replay"
            reference_executions += 1
            repeated = await capture_case(
                environment.client, case, timeout_seconds=600 if mode == "live" else 15
            )
            skip_golden = update_golden or mode == "live"
            reference_failures.extend(check_case(case, reference, root, skip_golden=skip_golden))
            reference_failures.extend(check_case(case, repeated, root, skip_golden=skip_golden))
            difference = transcript_diff(
                case.id,
                render_transcript(reference),
                render_transcript(repeated),
                "determinism",
            )
            if difference and mode != "live":
                reference_failures.append(f"{case.id}: nondeterministic transcript\n{difference}")
            if update_golden and not reference_failures:
                path = fixture_path(root, case.expect["golden"])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(render_transcript(reference))
            for trial_index in range(standard_trials):
                started = reference_started if trial_index == 0 else time.perf_counter()
                clock = reference_clock if trial_index == 0 else datetime.now(UTC)
                failures = list(reference_failures)
                evidence = reference
                executions = reference_executions if trial_index == 0 else 1
                if trial_index:
                    try:
                        evidence = await capture_case(
                            environment.client,
                            case,
                            timeout_seconds=600 if mode == "live" else 15,
                        )
                        failures.extend(check_case(case, evidence, root, skip_golden=skip_golden))
                        difference = transcript_diff(
                            case.id,
                            render_transcript(reference),
                            render_transcript(evidence),
                            "determinism",
                        )
                        if difference and mode != "live":
                            failures.append(f"{case.id}: nondeterministic transcript\n{difference}")
                    except Exception as error:
                        failures.append(f"{case.id}: {type(error).__name__}: {error}")
                record(
                    "standard", seed + trial_index, evidence, failures, started, clock, executions
                )
    except Exception as error:
        reference_failures.append(f"{case.id}: reference failed: {type(error).__name__}: {error}")
        record(
            "standard" if standard_trials else "chaos",
            seed,
            reference,
            reference_failures,
            reference_started,
            reference_clock,
            reference_executions,
        )
        return results

    async with AsyncExitStack() as resources:
        environment = None
        for trial_index in range(chaos_trials):
            trial_seed = seed + trial_index
            plan = chaos_plan(case, reference, trial_seed)
            started, clock = time.perf_counter(), datetime.now(UTC)
            failures = list(reference_failures)
            evidence = None
            try:
                if environment is None:
                    agent = await resources.enter_async_context(
                        case_agent(case, root, database_url, "replay" if mode == "record" else mode)
                    )
                    environment = await resources.enter_async_context(
                        local_api(database_url, agent, coalesce_seconds=0.008)
                    )
                environment.app.state.runtime.agent = PausedAgent(
                    agent, emit_index=plan.pause_emit_index, seconds=plan.pause_seconds
                )
                evidence = await capture_case(environment.client, case, plan=plan)
                failures.extend(check_case(case, evidence, root))
                difference = transcript_diff(
                    case.id,
                    render_transcript(reference),
                    render_transcript(evidence),
                    "uninterrupted",
                )
                if difference:
                    failures.append(f"{case.id}: resume changed the transcript\n{difference}")
            except Exception as error:
                failures.append(f"{case.id}: {type(error).__name__}: {error}")
            executions = 1 + (
                reference_executions if not standard_trials and trial_index == 0 else 0
            )
            record("chaos", trial_seed, evidence, failures, started, clock, executions, plan)
    return results


async def evaluate_suite(
    root: Path,
    database_url: str,
    *,
    filter_value: str | None = None,
    trials: int | None = None,
    seed: int = 0,
    chaos_only: bool = False,
    include_chaos: bool = True,
    update_golden: bool = False,
    pass_streak: int = 3,
    mode: str = "replay",
    scope_concurrency: int = 8,
    mutation: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Report:
    if trials is not None and trials < 1:
        raise ValueError("--trials must be positive")
    if seed < 0 or pass_streak < 1:
        raise ValueError("Seed must be nonnegative and pass^k must be positive")
    if chaos_only and update_golden:
        raise ValueError("Goldens can only be updated from uninterrupted executions")
    if not 1 <= scope_concurrency <= 16:
        raise ValueError("Scope concurrency must be between 1 and 16")
    if mutation not in {None, "disable_scope_guard"}:
        raise ValueError("Unknown evaluation mutation")
    suite = load_suite(root)
    selected = suite.cases
    if filter_value:

        def matches(value: str) -> bool:
            return filter_value in value or fnmatch.fnmatchcase(value, filter_value)

        linked = {
            case_id
            for requirement in suite.requirements
            if matches(requirement.id)
            for case_id in requirement.cases
        }
        selected = [case for case in selected if matches(case.id) or case.id in linked]
        if not selected:
            raise ValueError(f"No cases match {filter_value!r}")
    paths = []
    for case in selected:
        validate_expectations(case, root)
        if case.agent.startswith("scripted:"):
            scripted_agent(case, root)
        if "golden" in case.expect:
            paths.append(fixture_path(root, case.expect["golden"]))
    if len(paths) != len(set(paths)):
        raise ValueError("Each case must own a distinct golden file")
    standard_trials = 0 if chaos_only else (trials or 1)
    chaos_trials = (trials or 10) if include_chaos and not update_golden else 0
    verifications = (["standard"] if standard_trials else []) + (["chaos"] if chaos_trials else [])
    commit, dirty = git_provenance(root)
    started, clock = time.perf_counter(), datetime.now(UTC)
    results = []
    scope_cases = [case for case in selected if case.agent.startswith("guard:")]
    if mutation and (mode != "replay" or len(scope_cases) != len(selected)):
        raise ValueError("Scope mutation requires replay mode and a guard-only case selection")
    if scope_cases and not chaos_only:
        results.extend(
            await evaluate_scope_cases(
                scope_cases,
                root,
                mode=mode,
                trials=trials or 10,
                seed=seed,
                commit=commit,
                dirty=dirty,
                concurrency=scope_concurrency,
                disable_guard=mutation == "disable_scope_guard",
                progress=progress,
            )
        )
    for case in selected:
        if case.agent.startswith("guard:"):
            continue
        case_trials = standard_trials
        if standard_trials and trials is None:
            case_trials = max(
                [
                    standard_trials,
                    *(
                        requirement.threshold.trials
                        for requirement in suite.requirements
                        if requirement.threshold
                        and requirement.verification == "standard"
                        and case.id in requirement.cases
                    ),
                ]
            )
        results.extend(
            await evaluate_case(
                case,
                root,
                database_url,
                standard_trials=case_trials,
                chaos_trials=chaos_trials,
                seed=seed,
                update_golden=update_golden,
                commit=commit,
                dirty_worktree=dirty,
                mode=mode,
            )
        )
    return Report(
        created_at=clock,
        duration_seconds=time.perf_counter() - started,
        requirements=suite.requirements,
        cases=selected,
        verifications=verifications,
        results=results,
        pass_streak=pass_streak,
    )
