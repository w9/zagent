import asyncio

import pytest
from zagent.events import EventDraft
from zagent.llm import AssistantMessage, CassetteMiss, Completion
from zagent.runtime import Runtime
from zagent.titles import SessionTitles

pytestmark = pytest.mark.integration


async def exchange(store, session, refused=False):
    turn = await store.begin_conversation_turn(session.id, "Find NGC-0041872 specimens")
    if refused:
        from zagent.scope import refusal

        await store.append(
            session.id,
            turn.conversation_turn_id,
            EventDraft(type="refused", payload=refusal("out_of_domain").model_dump()),
        )
    else:
        await store.append(
            session.id,
            turn.conversation_turn_id,
            EventDraft(
                type="text_delta",
                payload={"message_id": "answer", "text": "Specimen intake is available."},
            ),
        )
        await store.append(
            session.id,
            turn.conversation_turn_id,
            EventDraft(type="message_done", payload={"message_id": "answer"}),
        )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    return turn


async def test_newest_first_titles_are_stable_with_timestamp_ties(store):
    first, second = await store.create_session(), await store.create_session()
    assert (await store.list_sessions())[0].id == second.id
    await store.pool.execute(
        "UPDATE sessions SET created_at=$2 WHERE id = ANY($1::uuid[])",
        [first.id, second.id],
        second.created_at,
    )
    listed = [item for item in await store.list_sessions() if item.id in {first.id, second.id}]
    assert [item.id for item in listed] == sorted([first.id, second.id], reverse=True)
    await store.rename_session(first.id, "Manual NGC-0041872 review")
    assert (await store.get_session(first.id)).title == "Manual [PT_1] review"
    assert (await store.get_session(second.id)).title == second.title
    assert [
        item.id for item in await store.list_sessions() if item.id in {first.id, second.id}
    ] == [item.id for item in listed]


async def test_manual_rename_wins_while_automatic_generation_is_in_flight(store):
    started, release = asyncio.Event(), asyncio.Event()

    class SlowModel:
        calls = []

        async def complete(self, request):
            self.calls.append(request)
            started.set()
            await release.wait()
            return Completion(message=AssistantMessage(content="Specimen intake review"))

    session = await store.create_session()
    turn = await exchange(store, session)
    model = SlowModel()
    titles = SessionTitles(store, model)
    titles.start(turn)
    await started.wait()
    assert "NGC-0041872" not in str(model.calls[0].model_dump())
    await store.rename_session(session.id, "My chosen title")
    release.set()
    await asyncio.gather(*titles.tasks)
    assert (await store.get_session(session.id)).title == "My chosen title"
    await titles.generate(turn)
    assert len(model.calls) == 1


async def test_title_miss_and_refused_only_sessions_keep_fallback(store):
    class Missing:
        calls = 0

        async def complete(self, request):
            self.calls += 1
            raise CassetteMiss("Missing title recording")

    model = Missing()
    titles = SessionTitles(store, model)
    session = await store.create_session()
    refused = await exchange(store, session, refused=True)
    await titles.generate(refused)
    assert model.calls == 0
    turn = await exchange(store, session)
    await titles.generate(turn)
    await titles.generate(turn)
    assert model.calls == 1
    assert (await store.get_session(session.id)).title == session.title
    assert (await store.snapshot(session.id)).conversation_turn.status == "finished"


async def test_slow_title_generation_does_not_hold_the_turn_open(store):
    started, release = asyncio.Event(), asyncio.Event()

    class Model:
        async def complete(self, request):
            started.set()
            await release.wait()
            return Completion(message=AssistantMessage(content="Specimen intake review"))

    class Reply:
        async def run_turn(self, session, emit):
            await emit(
                EventDraft(type="text_delta", payload={"message_id": "answer", "text": "Ready."})
            )
            await emit(EventDraft(type="message_done", payload={"message_id": "answer"}))

    session = await store.create_session()
    titles = SessionTitles(store, Model())
    runtime = Runtime(store, Reply(), titles=titles)
    first = await store.begin_conversation_turn(session.id, "Show specimens")
    await runtime._run_turn(first)
    await started.wait()
    second = await store.begin_conversation_turn(session.id, "A follow-up")
    assert second.conversation_turn_id != first.conversation_turn_id
    release.set()
    await asyncio.gather(*titles.tasks)
    assert (await store.get_session(session.id)).title_source == "automatic"
    await store.finish_conversation_turn(session.id, second.conversation_turn_id)


async def test_empty_exchange_leaves_title_attempt_available(store):
    class NoModel:
        async def complete(self, _request):
            raise AssertionError("An empty response must not generate a topic title")

    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Show specimens")
    await store.append(
        session.id,
        turn.conversation_turn_id,
        EventDraft(
            type="message_done",
            payload={"message_id": "answer"},
        ),
    )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    await SessionTitles(store, NoModel()).generate(turn)
    assert (await store.get_session(session.id)).title == session.title
    assert not await store.pool.fetchval(
        "SELECT title_attempted FROM sessions WHERE id=$1", session.id
    )


async def test_generated_and_manual_titles_keep_identifier_storage_tokenized(store):
    class Model:
        async def complete(self, request):
            assert "NGC-0041872" not in str(request.model_dump())
            assert "Mira Vellorin" not in str(request.model_dump())
            return Completion(message=AssistantMessage(content="Mira Vellorin specimen review"))

    session = await store.create_session()
    turn = await exchange(store, session)
    await SessionTitles(store, Model()).generate(turn)
    automatic = await store.get_session(session.id)
    assert "Mira Vellorin" not in automatic.title
    assert "[PT_" in automatic.title
    await store.rename_session(session.id, "NGC-0041872 intake")
    manual = await store.get_session(session.id)
    assert manual.title_source == "manual"
    assert "NGC-0041872" not in manual.title
