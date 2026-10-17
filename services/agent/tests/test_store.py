import asyncio
from importlib.resources import files
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest
from zagent.artifacts import ArtifactSpec
from zagent.events import EventDraft
from zagent.privacy import Tokenized
from zagent.store import ConversationTurnConflict, Store, configure_connection

pytestmark = pytest.mark.integration


TABLE_SPEC = {
    "kind": "table",
    "version": 1,
    "props": {
        "title": "Rows",
        "columns": [{"key": "id", "label": "Id", "type": "string"}],
        "rows": [],
        "row_count": 0,
    },
}


def delta(text="word "):
    return EventDraft(type="text_delta", payload={"message_id": "answer", "text": text})


async def test_concurrent_appends_are_contiguous(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Hello")
    await asyncio.gather(
        *(store.append(session.id, turn.conversation_turn_id, delta()) for _ in range(40))
    )
    events = await store.events_after(session.id, 0)
    assert [event.seq for event in events] == list(range(1, 42))
    assert (await store.get_session(session.id)).seq == 41


async def test_uncommitted_append_cannot_be_overtaken(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Hello")
    async with store.pool.acquire() as connection:
        async with connection.transaction():
            first = await store._append(
                connection, session.id, turn.conversation_turn_id, delta("first")
            )
            pending = asyncio.create_task(
                store.append(session.id, turn.conversation_turn_id, delta("second"))
            )
            visible = await store.events_after(session.id, 0)
            assert [event.seq for event in visible] == [1]
            assert not pending.done()
        second = await asyncio.wait_for(pending, timeout=3)
    assert (first.seq, second.seq) == (2, 3)


async def test_rollback_does_not_allocate_a_sequence(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Hello")
    with pytest.raises(RuntimeError, match="rollback"):
        async with store.pool.acquire() as connection, connection.transaction():
            await store._append(
                connection, session.id, turn.conversation_turn_id, delta("discarded")
            )
            raise RuntimeError("rollback")
    appended = await store.append(session.id, turn.conversation_turn_id, delta("kept"))
    assert appended.seq == 2
    assert (await store.snapshot(session.id)).messages[-1].text == "kept"


async def test_one_active_conversation_turn_and_atomic_completion(store):
    session = await store.create_session()
    attempts = await asyncio.gather(
        store.begin_conversation_turn(session.id, "first"),
        store.begin_conversation_turn(session.id, "second"),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ConversationTurnConflict) for result in attempts) == 1
    turn = next(result for result in attempts if not isinstance(result, Exception))
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    assert await store.head(session.id) == (2, False)
    assert (await store.snapshot(session.id)).conversation_turn.status == "finished"
    with pytest.raises(ConversationTurnConflict):
        await store.append(session.id, turn.conversation_turn_id, delta())
    await store.begin_conversation_turn(session.id, "next")
    assert (await store.get_session(session.id)).seq == 3


async def test_event_log_rejects_mutation(store):
    session = await store.create_session()
    await store.begin_conversation_turn(session.id, "Hello")
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


async def test_artifact_numbering_continues_after_stored_view_events(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Show rows")
    async with store.pool.acquire() as connection, connection.transaction():
        seq = await connection.fetchval(
            "UPDATE sessions SET last_seq = last_seq + 1 WHERE id = $1 RETURNING last_seq",
            session.id,
        )
        await connection.execute(
            """INSERT INTO events
                      (session_id, seq, conversation_turn_id, schema_version, type, payload)
               VALUES ($1, $2, $3, 2, 'view_pushed', $4)""",
            session.id,
            seq,
            turn.conversation_turn_id,
            {"view_id": "view-0001", "spec": TABLE_SPEC},
        )
    published = await store.publish_artifact(
        session.id, turn.conversation_turn_id, ArtifactSpec.model_validate(TABLE_SPEC)
    )
    assert (published.schema_version, published.type) == (3, "artifact_published")
    assert published.payload["artifact_id"] == "view-0002"
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    snapshot = await store.snapshot(session.id)
    assert [artifact.id for artifact in snapshot.artifacts] == ["view-0001", "view-0002"]
    assert snapshot.conversation_turn.status == "finished"
    stored = await store.pool.fetch(
        "SELECT schema_version, type FROM events WHERE session_id = $1 ORDER BY seq", session.id
    )
    assert [tuple(row) for row in stored] == [
        (3, "user_message"),
        (2, "view_pushed"),
        (3, "artifact_published"),
        (3, "conversation_turn_finished"),
    ]
    for schema_version, kind in [(3, "view_pushed"), (3, "run_finished"), (4, "user_message")]:
        with pytest.raises(asyncpg.CheckViolationError):
            await store.pool.execute(
                """INSERT INTO events
                          (session_id, seq, conversation_turn_id, schema_version, type, payload)
                   VALUES ($1, 99, $2, $3, $4, '{}')""",
                session.id,
                turn.conversation_turn_id,
                schema_version,
                kind,
            )


async def test_upgrade_preserves_legacy_history_and_allows_new_turns(store, database_url):
    database = f"migration_{uuid4().hex}"
    await store.pool.execute(f'CREATE DATABASE "{database}"')
    isolated_url = urlunsplit(urlsplit(database_url)._replace(path=f"/{database}"))
    isolated = Store(
        await asyncpg.create_pool(
            isolated_url,
            min_size=1,
            max_size=2,
            init=configure_connection,
        )
    )
    try:
        await isolated.pool.execute(
            files("zagent").joinpath("migrations/001_spine.sql").read_text()
        )
        await isolated.pool.execute("CREATE TABLE schema_migrations (version integer PRIMARY KEY)")
        await isolated.pool.execute("INSERT INTO schema_migrations VALUES (1)")
        session_id, turn_id = uuid4(), uuid4()
        await isolated.pool.execute(
            "INSERT INTO sessions (id, last_seq) VALUES ($1, 5)", session_id
        )
        await isolated.pool.execute(
            "INSERT INTO runs (id, session_id, status) VALUES ($1, $2, 'finished')",
            turn_id,
            session_id,
        )
        for seq, kind, payload in [
            (1, "user_message", {"message_id": "user", "text": "Hello NGC-0041872"}),
            (2, "run_started", {}),
            (3, "view_pushed", {"view_id": "view-0001", "spec": TABLE_SPEC}),
            (4, "text_delta", {"message_id": "answer", "text": "Saved response NGC-0041872"}),
            (5, "run_finished", {}),
        ]:
            await isolated.pool.execute(
                """INSERT INTO events (session_id, seq, run_id, type, payload)
                   VALUES ($1, $2, $3, $4, $5)""",
                session_id,
                seq,
                turn_id,
                kind,
                payload,
            )
        original = await isolated.pool.fetch("SELECT * FROM events ORDER BY seq")
        await isolated.migrate(seed=False)
        await isolated.migrate(seed=False)
        migrated = await isolated.pool.fetch("SELECT * FROM events ORDER BY seq")
        original = [
            {
                ("conversation_turn_id" if key == "run_id" else key): value
                for key, value in dict(row).items()
            }
            for row in original
        ]
        archived = await isolated.pool.fetch("SELECT * FROM privacy.legacy_events ORDER BY seq")
        assert [dict(row) for row in archived] == original
        for before, after in zip(original, migrated, strict=True):
            restored = await isolated.privacy.resolve(session_id, Tokenized(value=after["payload"]))
            assert {**dict(after), "payload": restored.value} == before
        snapshot = await isolated.snapshot(session_id)
        assert snapshot.seq == 5
        assert [artifact.id for artifact in snapshot.artifacts] == ["view-0001"]
        assert snapshot.conversation_turn.id == turn_id
        assert snapshot.conversation_turn.status == "finished"
        assert snapshot.messages[-1].text == "Saved response [PT_1]"
        turn = await isolated.begin_conversation_turn(session_id, "Next")
        await isolated.finish_conversation_turn(session_id, turn.conversation_turn_id)
        events = await isolated.events_after(session_id, 0)
        assert [event.seq for event in events] == list(range(1, 8))
        assert all(event.schema_version == 3 for event in events)
        assert events[2].type == "artifact_published"
        assert events[-1].type == "conversation_turn_finished"
        stored = await isolated.pool.fetch(
            "SELECT schema_version, type FROM events WHERE session_id = $1 ORDER BY seq",
            session_id,
        )
        assert [tuple(row) for row in stored][2:] == [
            (1, "view_pushed"),
            (1, "text_delta"),
            (1, "run_finished"),
            (3, "user_message"),
            (3, "conversation_turn_finished"),
        ]
        with pytest.raises(asyncpg.RaiseError, match="append-only"):
            await isolated.pool.execute("DELETE FROM events")
    finally:
        await isolated.close()
        await store.pool.execute(f'DROP DATABASE "{database}"')
