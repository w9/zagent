import asyncio

import asyncpg
import pytest
from zagent.events import EventDraft
from zagent.store import RunConflict

pytestmark = pytest.mark.integration


def delta(text="word "):
    return EventDraft(type="text_delta", payload={"message_id": "answer", "text": text})


async def test_concurrent_appends_are_contiguous(store):
    session = await store.create_session()
    run = await store.begin_run(session.id, "Hello")
    await asyncio.gather(*(store.append(session.id, run.run_id, delta()) for _ in range(40)))
    events = await store.events_after(session.id, 0)
    assert [event.seq for event in events] == list(range(1, 42))
    assert (await store.get_session(session.id)).seq == 41


async def test_uncommitted_append_cannot_be_overtaken(store):
    session = await store.create_session()
    run = await store.begin_run(session.id, "Hello")
    async with store.pool.acquire() as connection:
        async with connection.transaction():
            first = await store._append(connection, session.id, run.run_id, delta("first"))
            pending = asyncio.create_task(store.append(session.id, run.run_id, delta("second")))
            visible = await store.events_after(session.id, 0)
            assert [event.seq for event in visible] == [1]
            assert not pending.done()
        second = await asyncio.wait_for(pending, timeout=3)
    assert (first.seq, second.seq) == (2, 3)


async def test_rollback_does_not_allocate_a_sequence(store):
    session = await store.create_session()
    run = await store.begin_run(session.id, "Hello")
    with pytest.raises(RuntimeError, match="rollback"):
        async with store.pool.acquire() as connection, connection.transaction():
            await store._append(connection, session.id, run.run_id, delta("discarded"))
            raise RuntimeError("rollback")
    appended = await store.append(session.id, run.run_id, delta("kept"))
    assert appended.seq == 2
    assert (await store.snapshot(session.id)).messages[-1].text == "kept"


async def test_one_active_run_and_atomic_completion(store):
    session = await store.create_session()
    attempts = await asyncio.gather(
        store.begin_run(session.id, "first"),
        store.begin_run(session.id, "second"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, RunConflict) for result in attempts) == 1
    run = next(result for result in attempts if not isinstance(result, Exception))
    await store.finish_run(session.id, run.run_id)
    assert await store.head(session.id) == (2, False)
    assert (await store.snapshot(session.id)).run.status == "finished"
    with pytest.raises(RunConflict):
        await store.append(session.id, run.run_id, delta())
    await store.begin_run(session.id, "next")
    assert (await store.get_session(session.id)).seq == 3


async def test_event_log_rejects_mutation(store):
    session = await store.create_session()
    await store.begin_run(session.id, "Hello")
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        await store.pool.execute("DELETE FROM events WHERE session_id = $1", session.id)
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        await store.pool.execute(
            "UPDATE events SET payload = '{}' WHERE session_id = $1", session.id
        )


async def test_migration_and_seed_are_idempotent(store):
    await store.migrate()
    before = await store.list_sessions()
    await store.migrate()
    assert await store.list_sessions() == before
