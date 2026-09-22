import json
from datetime import datetime
from importlib.resources import files
from uuid import UUID, uuid4

import asyncpg
from pydantic import BaseModel

from zagent.events import Event, EventDraft, Projection, project

DEFAULT_DATABASE_URL = "postgresql://zagent:zagent@localhost:5432/zagent"
SEED_SESSION_ID = UUID("01950000-0000-7000-8000-000000000001")
NOTIFY_CHANNEL = "zagent_events"


class NotFound(Exception):
    pass


class ConversationTurnConflict(Exception):
    pass


class Session(BaseModel):
    id: UUID
    seq: int
    created_at: datetime
    site_id: str = "northgate"


class AgentSession(BaseModel):
    id: UUID
    conversation_turn_id: UUID
    message: str
    site_id: str = "northgate"


async def configure_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads, format="text"
    )


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def open(cls, database_url: str) -> "Store":
        pool = await asyncpg.create_pool(
            database_url, min_size=2, max_size=10, init=configure_connection
        )
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def migrate(self, *, seed: bool = True) -> None:
        migrations = sorted(
            files("zagent").joinpath("migrations").iterdir(), key=lambda path: path.name
        )
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(710001)")
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY)"
            )
            for migration in migrations:
                if not migration.name.endswith(".sql"):
                    continue
                version = int(migration.name.split("_", 1)[0])
                applied = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)", version
                )
                if not applied:
                    await connection.execute(migration.read_text())
                    await connection.execute("INSERT INTO schema_migrations VALUES ($1)", version)
            if seed:
                await connection.execute(
                    "INSERT INTO sessions (id) VALUES ($1) ON CONFLICT DO NOTHING", SEED_SESSION_ID
                )

    async def create_session(self, site_id: str = "northgate") -> Session:
        row = await self.pool.fetchrow(
            """INSERT INTO sessions (id, site_id) VALUES ($1, $2)
               RETURNING id, last_seq AS seq, created_at, site_id""",
            uuid4(),
            site_id,
        )
        return Session.model_validate(dict(row))

    async def get_session(self, session_id: UUID) -> Session:
        row = await self.pool.fetchrow(
            "SELECT id, last_seq AS seq, created_at, site_id FROM sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            raise NotFound("Session not found")
        return Session.model_validate(dict(row))

    async def list_sessions(self) -> list[Session]:
        rows = await self.pool.fetch(
            "SELECT id, last_seq AS seq, created_at, site_id FROM sessions ORDER BY created_at, id"
        )
        return [Session.model_validate(dict(row)) for row in rows]

    async def begin_conversation_turn(self, session_id: UUID, text: str) -> AgentSession:
        conversation_turn_id = uuid4()
        async with self.pool.acquire() as connection, connection.transaction():
            session = await connection.fetchrow(
                "SELECT id, site_id FROM sessions WHERE id = $1 FOR UPDATE", session_id
            )
            if session is None:
                raise NotFound("Session not found")
            active = await connection.fetchval(
                "SELECT id FROM conversation_turns WHERE session_id = $1 AND status = 'running'",
                session_id,
            )
            if active:
                raise ConversationTurnConflict(
                    "This session already has an active conversation turn"
                )
            await connection.execute(
                """INSERT INTO conversation_turns (id, session_id, status)
                   VALUES ($1, $2, 'running')""",
                conversation_turn_id,
                session_id,
            )
            await self._append(
                connection,
                session_id,
                conversation_turn_id,
                EventDraft(type="user_message", payload={"message_id": str(uuid4()), "text": text}),
            )
        return AgentSession(
            id=session_id,
            conversation_turn_id=conversation_turn_id,
            message=text,
            site_id=session["site_id"],
        )

    async def _append(
        self,
        connection: asyncpg.Connection,
        session_id: UUID,
        conversation_turn_id: UUID,
        event: EventDraft,
    ) -> Event:
        event = EventDraft.model_validate(event.model_dump())
        seq = await connection.fetchval(
            "UPDATE sessions SET last_seq = last_seq + 1 WHERE id = $1 RETURNING last_seq",
            session_id,
        )
        if seq is None:
            raise NotFound("Session not found")
        status = await connection.fetchval(
            "SELECT status FROM conversation_turns WHERE id = $1 AND session_id = $2",
            conversation_turn_id,
            session_id,
        )
        if status != "running":
            raise ConversationTurnConflict("Conversation turn is not active")
        row = await connection.fetchrow(
            """INSERT INTO events (session_id, seq, conversation_turn_id, type, payload)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            session_id,
            seq,
            conversation_turn_id,
            event.type,
            event.payload,
        )
        await connection.execute("SELECT pg_notify($1, $2)", NOTIFY_CHANNEL, str(session_id))
        return Event.model_validate(dict(row))

    async def append(
        self, session_id: UUID, conversation_turn_id: UUID, event: EventDraft
    ) -> Event:
        async with self.pool.acquire() as connection, connection.transaction():
            return await self._append(connection, session_id, conversation_turn_id, event)

    async def finish_conversation_turn(
        self, session_id: UUID, conversation_turn_id: UUID, error: str | None = None
    ) -> None:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1 FOR UPDATE", session_id
            )
            status = await connection.fetchval(
                "SELECT status FROM conversation_turns WHERE id = $1 AND session_id = $2",
                conversation_turn_id,
                session_id,
            )
            if status != "running":
                return
            await self._append(
                connection,
                session_id,
                conversation_turn_id,
                EventDraft(
                    type="conversation_turn_failed"
                    if error is not None
                    else "conversation_turn_finished",
                    payload={"error": error} if error is not None else {},
                ),
            )
            await connection.execute(
                """UPDATE conversation_turns SET status = $2, finished_at = clock_timestamp()
                   WHERE id = $1""",
                conversation_turn_id,
                "failed" if error is not None else "finished",
            )

    async def fail_interrupted_conversation_turns(self) -> None:
        rows = await self.pool.fetch(
            "SELECT id, session_id FROM conversation_turns WHERE status = 'running'"
        )
        for row in rows:
            await self.finish_conversation_turn(
                row["session_id"],
                row["id"],
                "Agent service restarted before the conversation turn completed.",
            )

    async def events_after(self, session_id: UUID, seq: int, limit: int = 500) -> list[Event]:
        rows = await self.pool.fetch(
            "SELECT * FROM events WHERE session_id = $1 AND seq > $2 ORDER BY seq LIMIT $3",
            session_id,
            seq,
            limit,
        )
        return [Event.model_validate(dict(row)) for row in rows]

    async def snapshot_events(self, session_id: UUID) -> list[Event]:
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation="repeatable_read", readonly=True):
                exists = await connection.fetchval(
                    "SELECT id FROM sessions WHERE id = $1", session_id
                )
                if exists is None:
                    raise NotFound("Session not found")
                rows = await connection.fetch(
                    "SELECT * FROM events WHERE session_id = $1 ORDER BY seq", session_id
                )
        return [Event.model_validate(dict(row)) for row in rows]

    async def snapshot(self, session_id: UUID) -> Projection:
        return project(session_id, await self.snapshot_events(session_id))

    async def head(self, session_id: UUID) -> tuple[int, bool]:
        row = await self.pool.fetchrow(
            """SELECT last_seq, EXISTS (
                     SELECT 1 FROM conversation_turns WHERE session_id = $1 AND status = 'running'
               ) AS active FROM sessions WHERE id = $1""",
            session_id,
        )
        if row is None:
            raise NotFound("Session not found")
        return row["last_seq"], row["active"]
