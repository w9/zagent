import hashlib
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from zagent.agent import MAIN_TOOLS, SYSTEM_PROMPT, LlmAgent
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.drafts import model_facing_draft
from zagent.evals.assertions import check_case, render_transcript
from zagent.evals.environment import local_api
from zagent.evals.local_knowledge import local_tools
from zagent.evals.privacy import private_gateway
from zagent.evals.schema import Case, Provenance, TrialResult
from zagent.llm import CompletionRequest, ModelRoute, canonical_json, normalized_request
from zagent.privacy import Tokenized
from zagent.scope import SCOPE_POLICY_HASH
from zagent.store import Store
from zagent.tools import ToolsGateway

SIMULATOR_MODEL = "deepseek/deepseek-v4.1-flash"
SIMULATOR_PROMPT = """You simulate a user editing a genomics analysis draft with an assistant.
Your private target and the conversation are supplied as data. Reply with only your next short
user message, no role labels. Do not reveal the whole target at once. Answer the assistant's
most recent clarification; otherwise correct just one parameter that differs from your target.
Use the exact parameter name and desired value when correcting it. Refer to the existing draft
instead of requesting a second draft. Never ask to submit or confirm: stop at an editable draft.
If no draft exists yet, ask for a draft of the target application for the patient already mentioned.
"""


class SampleGateway:
    def __init__(self, gateway, sample: int):
        self.gateway, self.sample = gateway, sample

    async def complete(self, request):
        return await self.gateway.complete(request.model_copy(update={"sample": self.sample}))

    def requests_for_session(self, session_id):
        return self.gateway.requests_for_session(session_id)


async def evaluate_simulated_users(
    case: Case,
    root: Path,
    database_url: str,
    *,
    mode: str,
    trials: int,
    seed: int,
    record_missing: bool,
    commit: str | None,
    dirty: bool | None,
) -> list[TrialResult]:
    from zagent.evals.runner import capture_case

    results = []
    store = await Store.open(database_url)
    try:
        await store.migrate(seed=False)
        clinical = ClinicalStore(store, lambda: FROZEN_NOW)
        await clinical.seed()
        gateway = private_gateway(mode, store.privacy, record_missing=record_missing)
        gateway.routes["simulator"] = ModelRoute(
            model=os.environ.get("ZAGENT_SIMULATOR_MODEL", SIMULATOR_MODEL)
        )
        prompt_hash = normalized_request(
            CompletionRequest(messages=[{"role": "system", "content": SYSTEM_PROMPT}]),
            gateway.routes["default"],
        )["prompt_hash"]
        tool_schema_hash = hashlib.sha256(canonical_json(MAIN_TOOLS).encode()).hexdigest()
        for sample in range(seed, seed + trials):
            started, clock = time.perf_counter(), datetime.now(UTC)
            evidence, failures, turns = None, [], 0
            sampled = SampleGateway(gateway, sample)
            agent = LlmAgent(
                store,
                sampled,
                ToolsGateway(store, local_tools(clinical)),
            )
            try:
                async with local_api(database_url, agent) as environment:
                    evidence = await capture_case(
                        environment.client, case, timeout_seconds=600 if mode != "replay" else 30
                    )
                    turns = 1
                    while turns < case.simulator.max_turns:
                        if not check_case(case, evidence, root, skip_golden=True):
                            break
                        if (
                            evidence.projection.conversation_turn.status == "failed"
                            or evidence.projection.refusals
                        ):
                            break
                        state = evidence.projection
                        response = await sampled.complete(
                            CompletionRequest(
                                route="simulator",
                                max_tokens=160,
                                reasoning="disabled",
                                messages=[
                                    {"role": "system", "content": SIMULATOR_PROMPT},
                                    {
                                        "role": "user",
                                        "content": canonical_json(
                                            {
                                                "target": case.simulator.model_dump(),
                                                "conversation": [
                                                    {"role": item.role, "content": item.text}
                                                    for item in state.messages
                                                ],
                                                "drafts": [
                                                    model_facing_draft(item.model_dump())
                                                    for item in state.drafts.values()
                                                ],
                                            }
                                        ),
                                    },
                                ],
                                metadata={
                                    "session_id": str(state.session_id),
                                    "conversation_turn_id": str(state.conversation_turn.id),
                                    "purpose": "simulated_user",
                                    "scope_hash": SCOPE_POLICY_HASH,
                                },
                            )
                        )
                        text = response.message.content
                        if not text or response.message.tool_calls:
                            raise ValueError("Simulator must produce one plain-text user message")
                        text = (
                            await store.privacy.resolve(
                                state.session_id, Tokenized(value=text), strict=True
                            )
                        ).value
                        followup = case.model_copy(
                            update={
                                "conversation_turns": [
                                    case.conversation_turns[0].model_copy(update={"user": text})
                                ]
                            }
                        )
                        evidence = await capture_case(
                            environment.client,
                            followup,
                            previous=evidence,
                            timeout_seconds=600 if mode != "replay" else 30,
                        )
                        turns += 1
                    failures.extend(check_case(case, evidence, root, skip_golden=True))
            except Exception as error:
                failures.append(f"{case.id}: {type(error).__name__}: {error}")
            results.append(
                TrialResult(
                    case_id=case.id,
                    verification="standard",
                    seed=sample,
                    passed=not failures,
                    failures=failures,
                    transcript=render_transcript(evidence) if evidence else "",
                    duration_seconds=time.perf_counter() - started,
                    executions=1,
                    session_id=str(evidence.projection.session_id) if evidence else None,
                    slot_app=case.simulator.app_id,
                    slot_turns=turns,
                    privacy_requests=len(evidence.requests) if evidence else 0,
                    provenance=Provenance(
                        commit=commit,
                        dirty_worktree=dirty,
                        seed=sample,
                        clock=clock,
                        agent_implementation="LlmAgent+SimulatedUser",
                        mode=mode,
                        model=gateway.routes["default"].model,
                        prompt_hash=prompt_hash,
                        tool_schema_hash=tool_schema_hash,
                        simulator_model=gateway.routes["simulator"].model,
                        simulator_prompt_hash=hashlib.sha256(SIMULATOR_PROMPT.encode()).hexdigest(),
                        independent_sample=sample,
                        scope_hash=SCOPE_POLICY_HASH,
                    ),
                )
            )
            print(
                f"{case.id} sample {sample}: "
                f"{'passed' if not failures else 'failed'} after {turns} turns",
                file=sys.stderr,
            )
    finally:
        await store.close()
    return results
