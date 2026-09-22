import asyncio
import fnmatch
import hashlib
import json
import random
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
from httpx_sse import aconnect_sse
from pydantic import Field

from zagent.agent import Agent, ScriptedAgent
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
from zagent.events import Event, Projection, reduce_event


class ChaosPlan(StrictModel):
    conversation_turn_index: int = Field(ge=0)
    disconnect_after_characters: int = Field(ge=0)
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
    return ChaosPlan(
        conversation_turn_index=turn_index,
        disconnect_after_characters=randomizer.randint(0, max(0, text_length // 2)),
        disconnect_seconds=randomizer.uniform(0.005, 0.035),
        pause_emit_index=1,
        pause_seconds=randomizer.uniform(0.015, 0.045),
    )


def scripted_agent(case: Case, root: Path, plan: ChaosPlan | None = None) -> Agent:
    name = case.agent.removeprefix("scripted:")
    script = None if name == "default" else fixture_path(root, f"scripts/{name}.yaml")
    agent = ScriptedAgent(script, delay_scale=0.04)
    if plan is None:
        return agent
    return PausedAgent(agent, emit_index=plan.pause_emit_index, seconds=plan.pause_seconds)


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
                        terminal = event.type in {
                            "conversation_turn_finished",
                            "conversation_turn_failed",
                        }
                        if (
                            plan is not None
                            and not resumed
                            and not terminal
                            and turn_index == plan.conversation_turn_index
                            and text_characters >= plan.disconnect_after_characters
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
) -> list[TrialResult]:
    if min(standard_trials, chaos_trials, seed) < 0 or standard_trials + chaos_trials == 0:
        raise ValueError("Evaluation requires positive trial counts and a nonnegative seed")
    validate_expectations(case, root)
    agent = scripted_agent(case, root)
    script_digest = hashlib.sha256(
        json.dumps(
            {
                "script": agent.script.model_dump(),
                "failure": agent.failure.model_dump(),
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
                    agent_implementation="ScriptedAgent",
                    script_sha256=script_digest,
                    seed=trial_seed,
                    clock=clock,
                ),
                interruption=plan.model_dump() if plan is not None else None,
            )
        )

    try:
        async with local_api(database_url, agent, coalesce_seconds=0.008) as environment:
            reference_executions += 1
            reference = await capture_case(environment.client, case)
            reference_executions += 1
            repeated = await capture_case(environment.client, case)
            reference_failures.extend(check_case(case, reference, root, skip_golden=update_golden))
            reference_failures.extend(check_case(case, repeated, root, skip_golden=update_golden))
            difference = transcript_diff(
                case.id,
                render_transcript(reference),
                render_transcript(repeated),
                "determinism",
            )
            if difference:
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
                        evidence = await capture_case(environment.client, case)
                        failures.extend(check_case(case, evidence, root))
                        difference = transcript_diff(
                            case.id,
                            render_transcript(reference),
                            render_transcript(evidence),
                            "determinism",
                        )
                        if difference:
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

    for trial_index in range(chaos_trials):
        trial_seed = seed + trial_index
        plan = chaos_plan(case, reference, trial_seed)
        started, clock = time.perf_counter(), datetime.now(UTC)
        failures = list(reference_failures)
        evidence = None
        try:
            async with local_api(
                database_url,
                scripted_agent(case, root, plan),
                coalesce_seconds=0.008,
            ) as environment:
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
        executions = 1 + (reference_executions if not standard_trials and trial_index == 0 else 0)
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
) -> Report:
    if trials is not None and trials < 1:
        raise ValueError("--trials must be positive")
    if seed < 0 or pass_streak < 1:
        raise ValueError("Seed must be nonnegative and pass^k must be positive")
    if chaos_only and update_golden:
        raise ValueError("Goldens can only be updated from uninterrupted executions")
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
        scripted_agent(case, root)
        paths.append(fixture_path(root, case.expect["golden"]))
    if len(paths) != len(set(paths)):
        raise ValueError("Each case must own a distinct golden file")
    standard_trials = 0 if chaos_only else (trials or 1)
    chaos_trials = (trials or 10) if include_chaos and not update_golden else 0
    verifications = (["standard"] if standard_trials else []) + (["chaos"] if chaos_trials else [])
    commit, dirty = git_provenance(root)
    started, clock = time.perf_counter(), datetime.now(UTC)
    results = []
    for case in selected:
        results.extend(
            await evaluate_case(
                case,
                root,
                database_url,
                standard_trials=standard_trials,
                chaos_trials=chaos_trials,
                seed=seed,
                update_golden=update_golden,
                commit=commit,
                dirty_worktree=dirty,
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
