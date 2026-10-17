import asyncio
import os
import sys
from uuid import UUID

import pytest
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.tools import ClinicalTools

pytestmark = pytest.mark.integration


async def test_tool_replay_returns_the_committed_draft_without_a_second_mutation(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Prepare a readqc draft")
    tools = ClinicalTools(clinical)
    arguments = {"app_id": "readqc"}
    first = await tools.dispatch(
        session.id,
        "update_draft",
        arguments,
        conversation_turn_id=turn.conversation_turn_id,
        operation_id="operation-1",
    )
    second = await tools.dispatch(
        session.id,
        "update_draft",
        arguments,
        conversation_turn_id=turn.conversation_turn_id,
        operation_id="operation-1",
    )
    assert first == second
    snapshot = await store.snapshot(session.id)
    assert len(snapshot.drafts) == len(snapshot.artifacts) == 1
    assert snapshot.drafts["draft-0001"].version == 1
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


async def test_crash_before_tool_receipt_rolls_back_the_mutation(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Prepare a readqc draft")
    tools = ClinicalTools(ClinicalStore(store, lambda: FROZEN_NOW))
    dispatch = tools._dispatch

    async def interrupted(*arguments, **options):
        await dispatch(*arguments, **options)
        raise RuntimeError("Interrupted before receipt commit")

    tools._dispatch = interrupted
    with pytest.raises(RuntimeError, match="receipt commit"):
        await tools.dispatch(
            session.id,
            "update_draft",
            {"app_id": "readqc"},
            conversation_turn_id=turn.conversation_turn_id,
            operation_id="operation-1",
        )
    assert not (await store.snapshot(session.id)).drafts
    tools._dispatch = dispatch
    result = await tools.dispatch(
        session.id,
        "update_draft",
        {"app_id": "readqc"},
        conversation_turn_id=turn.conversation_turn_id,
        operation_id="operation-1",
    )
    assert result["draft"]["draft_id"] == "draft-0001"
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


async def test_atomic_tool_can_tokenize_through_a_separate_privacy_connection(store, database_url):
    from zagent.privacy_store import PrivacyStore
    from zagent.store import Store

    privacy_owner = await Store.open(database_url)
    tools_owner = await Store.open(database_url)
    tools_owner.privacy = PrivacyStore(privacy_owner.pool)
    clinical = ClinicalStore(tools_owner, lambda: FROZEN_NOW)
    try:
        await clinical.seed()
        session = await store.create_session()
        turn = await store.begin_conversation_turn(session.id, "Prepare a draft")
        async with asyncio.timeout(3):
            result = await ClinicalTools(clinical).dispatch(
                session.id,
                "find_patients",
                {"mrn": "NGC-0041872"},
                conversation_turn_id=turn.conversation_turn_id,
                operation_id="remote-privacy",
            )
            assert result["count"] == 1
            draft = await ClinicalTools(clinical).dispatch(
                session.id,
                "update_draft",
                {"app_id": "readqc"},
                conversation_turn_id=turn.conversation_turn_id,
                operation_id="remote-draft",
            )
            assert draft["draft"]["draft_id"] == "draft-0001"
        await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    finally:
        await tools_owner.close()
        await privacy_owner.close()


class Allow:
    async def classify(self, *_arguments, **_options):
        return None


class Responses:
    def __init__(self, *messages):
        self.messages = list(messages)
        self.calls = 0

    async def complete(self, _request):
        from zagent.llm import AssistantMessage, Completion

        self.calls += 1
        return Completion(message=AssistantMessage.model_validate(self.messages.pop(0)))


@pytest.mark.parametrize("boundary", ["text_delta", "tool_result"])
async def test_interrupted_turn_replays_checkpoints_without_duplicate_effects(store, boundary):
    from zagent.agent import LlmAgent
    from zagent.runtime import Runtime
    from zagent.tools import McpToolClient, ToolsGateway, create_mcp_server

    final = {"role": "assistant", "content": "The draft is ready for review."}
    tool = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "draft-call",
                "type": "function",
                "function": {"name": "update_draft", "arguments": '{"app_id":"readqc"}'},
            }
        ],
    }
    gateway = Responses(tool, final) if boundary == "tool_result" else Responses(final)
    tools = ToolsGateway(
        store, McpToolClient(server=create_mcp_server(ClinicalStore(store, lambda: FROZEN_NOW)))
    )
    agent = LlmAgent(store, gateway, tools, guard=Allow())
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Prepare a readqc draft")

    class Interrupted:
        resumable = True

        async def run_turn(self, session, emit):
            async def interrupted(event):
                if event.type == boundary:
                    if boundary == "text_delta":
                        await emit(event)
                    raise asyncio.CancelledError()
                await emit(event)

            await agent.run_turn(session, interrupted)

    with pytest.raises(asyncio.CancelledError):
        await Runtime(store, Interrupted())._run_turn(turn)
    assert (await store.snapshot(session.id)).conversation_turn.status == "running"
    resumed = Runtime(store, agent)
    await resumed.recover()
    await asyncio.gather(*list(resumed.tasks.values()))
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "finished"
    assert [item.text for item in snapshot.messages if item.role == "assistant"] == [
        final["content"]
    ]
    events = await store.snapshot_events(session.id)
    assert sum(event.type == "conversation_turn_started" for event in events) == 1
    assert gateway.calls == (2 if boundary == "tool_result" else 1)
    if boundary == "text_delta":
        assert any(event.type == "message_dropped" for event in events)
    else:
        assert len(snapshot.drafts) == len(snapshot.artifacts) == 1
        assert snapshot.drafts["draft-0001"].version == 1


@pytest.mark.parametrize("boundary", ["text_delta", "tool_result"])
async def test_sigkill_runtime_process_resumes_its_persisted_journal(store, database_url, boundary):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Prepare a readqc draft")
    environment = dict(os.environ, ZAGENT_RECOVERY_DATABASE=database_url)
    arguments = [
        sys.executable,
        __file__,
        str(session.id),
        str(turn.conversation_turn_id),
        boundary,
    ]
    child = await asyncio.create_subprocess_exec(
        *arguments,
        "interrupt",
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(10):
            assert await child.stdout.readline() == b"ready-to-kill\n"
        child.kill()
        await child.wait()
        assert child.returncode == -9
        assert (await store.snapshot(session.id)).conversation_turn.status == "running"
        replacement = await asyncio.create_subprocess_exec(
            *arguments,
            "resume",
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with asyncio.timeout(15):
            output, errors = await replacement.communicate()
        assert replacement.returncode == 0, errors.decode()
        assert b"resumed" in output
        state = await store.snapshot(session.id)
        assert state.conversation_turn.status == "finished"
        assert [message.text for message in state.messages if message.role == "assistant"] == [
            "The draft is ready for review."
        ]
        if boundary == "tool_result":
            assert len(state.drafts) == len(state.artifacts) == 1
        else:
            assert any(
                event.type == "message_dropped" for event in await store.snapshot_events(session.id)
            )
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()


async def process_worker():
    from zagent.agent import LlmAgent
    from zagent.runtime import Runtime
    from zagent.store import AgentSession, Store
    from zagent.tools import McpToolClient, ToolsGateway, create_mcp_server

    session_id, turn_id, boundary, phase = sys.argv[1:]
    store = await Store.open(os.environ["ZAGENT_RECOVERY_DATABASE"])
    final = {"role": "assistant", "content": "The draft is ready for review."}
    tool = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "draft-call",
                "type": "function",
                "function": {"name": "update_draft", "arguments": '{"app_id":"readqc"}'},
            }
        ],
    }
    gateway = (
        Responses(tool, final)
        if phase == "interrupt" and boundary == "tool_result"
        else Responses(final)
    )
    tools = ToolsGateway(
        store, McpToolClient(server=create_mcp_server(ClinicalStore(store, lambda: FROZEN_NOW)))
    )
    agent = LlmAgent(store, gateway, tools, guard=Allow())

    class AwaitKill:
        resumable = True

        async def run_turn(self, session, emit):
            async def capture(event):
                if event.type == boundary:
                    if event.type == "text_delta":
                        await store.append(session.id, session.conversation_turn_id, event)
                    print("ready-to-kill", flush=True)
                    await asyncio.Event().wait()
                await emit(event)

            await agent.run_turn(session, capture)

    runtime = Runtime(store, AwaitKill() if phase == "interrupt" else agent)
    try:
        await runtime._run_turn(
            AgentSession(
                id=UUID(session_id),
                conversation_turn_id=UUID(turn_id),
                message="Prepare a readqc draft",
            )
        )
        if phase == "resume":
            print("resumed", flush=True)
    finally:
        await runtime.close()
        await store.close()


if __name__ == "__main__":
    asyncio.run(process_worker())
