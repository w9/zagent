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


class RunConflict(Exception):
    pass


class Session(BaseModel):
    id: UUID
    seq: int
    created_at: datetime


class AgentSession(BaseModel):
    id: UUID
    run_id: UUID
    message: str


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
        migration = files("zagent").joinpath("migrations/001_spine.sql").read_text()
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(710001)")
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version integer PRIMARY KEY)"
            )
            applied = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = 1)"
            )
            if not applied:
                await connection.execute(migration)
                await connection.execute("INSERT INTO schema_migrations VALUES (1)")
            if seed:
                await connection.execute(
                    "INSERT INTO sessions (id) VALUES ($1) ON CONFLICT DO NOTHING", SEED_SESSION_ID
                )

    async def create_session(self) -> Session:
        row = await self.pool.fetchrow(
            "INSERT INTO sessions (id) VALUES ($1) RETURNING id, last_seq AS seq, created_at",
            uuid4(),
        )
        return Session.model_validate(dict(row))

    async def get_session(self, session_id: UUID) -> Session:
        row = await self.pool.fetchrow(
            "SELECT id, last_seq AS seq, created_at FROM sessions WHERE id = $1", session_id
        )
        if row is None:
            raise NotFound("Session not found")
        return Session.model_validate(dict(row))

    async def list_sessions(self) -> list[Session]:
        rows = await self.pool.fetch(
            "SELECT id, last_seq AS seq, created_at FROM sessions ORDER BY created_at, id"
        )
        return [Session.model_validate(dict(row)) for row in rows]

    async def begin_run(self, session_id: UUID, text: str) -> AgentSession:
        run_id = uuid4()
        async with self.pool.acquire() as connection, connection.transaction():
            exists = await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1 FOR UPDATE", session_id
            )
            if exists is None:
                raise NotFound("Session not found")
            active = await connection.fetchval(
                "SELECT id FROM runs WHERE session_id = $1 AND status = 'running'", session_id
            )
            if active:
                raise RunConflict("This session already has an active run")
            await connection.execute(
                "INSERT INTO runs (id, session_id, status) VALUES ($1, $2, 'running')",
                run_id,
                session_id,
            )
            await self._append(
                connection,
                session_id,
                run_id,
                EventDraft(type="user_message", payload={"message_id": str(uuid4()), "text": text}),
            )
        return AgentSession(id=session_id, run_id=run_id, message=text)

    async def _append(
        self,
        connection: asyncpg.Connection,
        session_id: UUID,
        run_id: UUID,
        event: EventDraft,
    ) -> Event:
        seq = await connection.fetchval(
            "UPDATE sessions SET last_seq = last_seq + 1 WHERE id = $1 RETURNING last_seq",
            session_id,
        )
        if seq is None:
            raise NotFound("Session not found")
        status = await connection.fetchval(
            "SELECT status FROM runs WHERE id = $1 AND session_id = $2", run_id, session_id
        )
        if status != "running":
            raise RunConflict("Run is not active")
        row = await connection.fetchrow(
            """INSERT INTO events (session_id, seq, run_id, type, payload)
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            session_id,
            seq,
            run_id,
            event.type,
            event.payload,
        )
        await connection.execute("SELECT pg_notify($1, $2)", NOTIFY_CHANNEL, str(session_id))
        return Event.model_validate(dict(row))

    async def append(self, session_id: UUID, run_id: UUID, event: EventDraft) -> Event:
        async with self.pool.acquire() as connection, connection.transaction():
            return await self._append(connection, session_id, run_id, event)

    async def finish_run(self, session_id: UUID, run_id: UUID, error: str | None = None) -> None:
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1 FOR UPDATE", session_id
            )
            status = await connection.fetchval(
                "SELECT status FROM runs WHERE id = $1 AND session_id = $2", run_id, session_id
            )
            if status != "running":
                return
            await self._append(
                connection,
                session_id,
                run_id,
                EventDraft(
                    type="run_failed" if error is not None else "run_finished",
                    payload={"error": error} if error is not None else {},
                ),
            )
            await connection.execute(
                "UPDATE runs SET status = $2, finished_at = clock_timestamp() WHERE id = $1",
                run_id,
                "failed" if error is not None else "finished",
            )

    async def fail_interrupted_runs(self) -> None:
        rows = await self.pool.fetch("SELECT id, session_id FROM runs WHERE status = 'running'")
        for row in rows:
            await self.finish_run(
                row["session_id"], row["id"], "Agent service restarted before the run completed."
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
                   SELECT 1 FROM runs WHERE session_id = $1 AND status = 'running'
               ) AS active FROM sessions WHERE id = $1""",
            session_id,
        )
        if row is None:
            raise NotFound("Session not found")
        return row["last_seq"], row["active"]
