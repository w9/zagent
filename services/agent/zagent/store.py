import hashlib
import json
import os
from datetime import UTC, datetime
from importlib.resources import files
from typing import Literal
from uuid import UUID, uuid4

import asyncpg
from pydantic import BaseModel, Field

from zagent.events import Event, EventDraft, Projection, project
from zagent.faults import configured, enabled
from zagent.identity import DEFAULT_PERSONA, PersonaId
from zagent.privacy import Raw
from zagent.privacy_client import PrivacyClient, Tokenizer
from zagent.privacy_store import PrivacyStore
from zagent.transactions import AtomicPool
from zagent.views import ViewSpec

DEFAULT_DATABASE_URL = "postgresql://zagent:zagent@localhost:5432/zagent"
SEED_SESSION_ID = UUID("01950000-0000-7000-8000-000000000001")
NOTIFY_CHANNEL = "zagent_events"
EVENT_INGRESS = {
    "user_message": "user_message",
    "text_delta": "assistant_output",
    "step_started": "assistant_output",
    "step_finished": "assistant_output",
    "tool_call": "tool_arguments",
    "tool_result": "tool_result",
    "view_pushed": "view_spec",
    "draft_updated": "draft_updated",
    "refused": "assistant_output",
    "conversation_turn_failed": "assistant_output",
    "privacy_alert": "assistant_output",
    "job_submitted": "draft_updated",
    "session_updated": "view_interaction",
}
LIFECYCLE_EVENTS = frozenset(
    {
        "conversation_turn_started",
        "conversation_turn_finished",
        "message_done",
        "message_dropped",
    }
)


class NotFound(Exception):
    pass


class ConversationTurnConflict(Exception):
    pass


class Session(BaseModel):
    id: UUID
    seq: int
    created_at: datetime
    site_id: str = "northgate"
    persona: PersonaId = DEFAULT_PERSONA
    title: str = "Session"
    title_source: Literal["fallback", "automatic", "manual"] = "fallback"


class AgentSession(BaseModel):
    id: UUID
    conversation_turn_id: UUID
    message: str
    site_id: str = "northgate"
    caller_context: str | None = Field(default=None, repr=False)
    kb_snapshot: str | None = None


SESSION_COLUMNS = "id, last_seq AS seq, created_at, site_id, persona, title, title_source"


async def configure_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads, format="text"
    )


class Store:
    def __init__(self, pool: asyncpg.Pool, privacy: Tokenizer | None = None):
        self.pool = pool if isinstance(pool, AtomicPool) else AtomicPool(pool)
        self.privacy = privacy or (
            PrivacyClient.configured()
            if os.environ.get("ZAGENT_PRIVACY_URL")
            else PrivacyStore(self.pool)
        )

    @classmethod
    async def open(cls, database_url: str) -> "Store":
        configured(database_url)
        pool = await asyncpg.create_pool(
            database_url, min_size=2, max_size=10, init=configure_connection
        )
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    async def tool_operation(self, session_id, turn_id, operation_id, name, arguments, action):
        digest = hashlib.sha256(json.dumps([name, arguments], sort_keys=True).encode()).hexdigest()
        async with self.pool.atomic() as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"{turn_id}:{operation_id}"
            )
            previous = await connection.fetchrow(
                "SELECT * FROM tool_receipts WHERE conversation_turn_id=$1 AND operation_id=$2",
                turn_id,
                operation_id,
            )
            if previous is not None:
                if previous["arguments_hash"] != digest or previous["session_id"] != session_id:
                    raise ValueError("Recovery operation does not match its original arguments")
                return previous["result"]
            active = await connection.fetchval(
                "SELECT status FROM conversation_turns WHERE session_id=$1 AND id=$2",
                session_id,
                turn_id,
            )
            if active != "running":
                raise ConversationTurnConflict("Tool operation requires an active turn")
            result = (
                await self.privacy.tokenize(
                    session_id,
                    Raw(value=await action()),
                    path="tool_result",
                )
            ).value
            await connection.execute(
                "INSERT INTO tool_receipts VALUES ($1,$2,$3,$4,$5)",
                session_id,
                turn_id,
                operation_id,
                digest,
                result,
            )
            return result

    async def checkpoints(self, session_id: UUID, turn_id: UUID) -> dict[int, dict]:
        rows = await self.pool.fetch(
            "SELECT step, response FROM turn_checkpoints "
            "WHERE session_id=$1 AND conversation_turn_id=$2",
            session_id,
            turn_id,
        )
        return {row["step"]: row["response"] for row in rows}

    async def checkpoint(self, session_id: UUID, turn_id: UUID, step: int, response: dict) -> dict:
        response = (
            await self.privacy.tokenize(
                session_id,
                Raw(value=response),
                path="assistant_output",
            )
        ).value
        await self.pool.execute(
            "INSERT INTO turn_checkpoints VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
            session_id,
            turn_id,
            step,
            response,
        )
        return (await self.checkpoints(session_id, turn_id))[step]

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
        if isinstance(self.privacy, PrivacyStore):
            await self.privacy.migrate_history()
        if enabled("rls_off"):
            async with self.pool.acquire() as connection, connection.transaction():
                for table in ("patients", "specimens", "libraries", "query_handles"):
                    await connection.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
                    await connection.execute(f"GRANT SELECT ON {table} TO zagent_runtime")

    async def protect_event(self, session_id: UUID, event: EventDraft) -> EventDraft:
        event = EventDraft.model_validate(event.model_dump())
        if event.type in LIFECYCLE_EVENTS and not event.payload:
            return event
        path = EVENT_INGRESS.get(event.type)
        if path is None:
            if event.type not in LIFECYCLE_EVENTS:
                raise ValueError("Event has no registered privacy ingress")
            path = "assistant_output"
        payload = (
            await self.privacy.tokenize(session_id, Raw(value=event.payload), path=path)
        ).value
        return EventDraft(type=event.type, payload=payload)

    async def create_session(
        self, site_id: str = "northgate", persona: PersonaId = DEFAULT_PERSONA
    ) -> Session:
        session_id = uuid4()
        row = await self.pool.fetchrow(
            f"""INSERT INTO sessions (id, site_id, persona, title) VALUES ($1, $2, $3, $4)
               RETURNING {SESSION_COLUMNS}""",
            session_id,
            site_id,
            persona,
            f"Session {session_id.hex[:8]}",
        )
        await self.pool.execute("SELECT pg_notify($1, 'sessions')", NOTIFY_CHANNEL)
        return Session.model_validate(dict(row))

    async def get_session(self, session_id: UUID) -> Session:
        row = await self.pool.fetchrow(
            f"SELECT {SESSION_COLUMNS} FROM sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            raise NotFound("Session not found")
        return Session.model_validate(dict(row))

    async def list_sessions(self) -> list[Session]:
        rows = await self.pool.fetch(
            f"SELECT {SESSION_COLUMNS} FROM sessions ORDER BY created_at DESC, id DESC"
        )
        return [Session.model_validate(dict(row)) for row in rows]

    async def claim_title(self, session_id: UUID) -> bool:
        return bool(
            await self.pool.fetchval(
                """UPDATE sessions SET title_attempted = true
                         WHERE id=$1 AND title_source='fallback'
               AND NOT title_attempted RETURNING id""",
                session_id,
            )
        )

    async def rename_session(
        self, session_id: UUID, title: str, *, automatic: bool = False
    ) -> Session:
        if not title.strip() or len(title) > 120:
            raise ValueError("Session title must contain 1 to 120 characters")
        safe = (
            await self.privacy.tokenize(
                session_id,
                Raw(value=title.strip()),
                path="view_interaction",
                external=not automatic,
            )
        ).value
        async with self.pool.acquire() as connection, connection.transaction():
            exists = await connection.fetchval(
                "SELECT id FROM sessions WHERE id=$1 FOR UPDATE", session_id
            )
            if exists is None:
                raise NotFound("Session not found")
            await connection.execute(
                """UPDATE sessions SET title=$2, title_source=$3 WHERE id=$1
                   AND (NOT $4 OR title_source='fallback')""",
                session_id,
                safe,
                "automatic" if automatic else "manual",
                automatic,
            )
            await connection.execute("SELECT pg_notify($1, 'sessions')", NOTIFY_CHANNEL)
        return await self.get_session(session_id)

    async def begin_conversation_turn(
        self,
        session_id: UUID,
        text: str,
        *,
        conversation_turn_id: UUID | None = None,
        caller_context: str | None = None,
    ) -> AgentSession:
        text = (
            await self.privacy.tokenize(
                session_id,
                Raw(value=text),
                path="user_message",
            )
        ).value
        conversation_turn_id = conversation_turn_id or uuid4()
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
                """INSERT INTO conversation_turns (id, session_id, status, caller_context)
                   VALUES ($1, $2, 'running', $3)""",
                conversation_turn_id,
                session_id,
                caller_context,
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
            caller_context=caller_context,
        )

    async def _append(
        self,
        connection: asyncpg.Connection,
        session_id: UUID,
        conversation_turn_id: UUID,
        event: EventDraft,
        *,
        allow_finished: bool = False,
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
        if status != "running" and not (
            allow_finished
            and status in {"finished", "failed"}
            and event.type in {"draft_updated", "view_pushed", "job_submitted", "session_updated"}
        ):
            raise ConversationTurnConflict("Conversation turn is not active")
        if enabled("drop_events") and event.type == "text_delta":
            return Event(
                session_id=session_id,
                seq=seq,
                conversation_turn_id=conversation_turn_id,
                type=event.type,
                payload=event.payload,
                created_at=datetime.now(UTC),
            )
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
        event = await self.protect_event(session_id, event)
        async with self.pool.acquire() as connection, connection.transaction():
            return await self._append(connection, session_id, conversation_turn_id, event)

    async def publish_view(
        self, session_id: UUID, conversation_turn_id: UUID, spec: ViewSpec
    ) -> Event:
        spec = ViewSpec.model_validate(
            (
                await self.privacy.tokenize(
                    session_id,
                    Raw(value=spec.model_dump()),
                    path="view_spec",
                )
            ).value
        )
        async with self.pool.acquire() as connection, connection.transaction():
            exists = await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1 FOR NO KEY UPDATE", session_id
            )
            if exists is None:
                raise NotFound("Session not found")
            turn_id = await connection.fetchval(
                """SELECT id FROM conversation_turns
                   WHERE session_id = $1 AND id = $2 AND status = 'running'""",
                session_id,
                conversation_turn_id,
            )
            if turn_id is None:
                raise ConversationTurnConflict("Publishing a view requires an active turn")
            number = await connection.fetchval(
                "SELECT count(*) + 1 FROM events WHERE session_id = $1 AND type = 'view_pushed'",
                session_id,
            )
            return await self._append(
                connection,
                session_id,
                turn_id,
                EventDraft(
                    type="view_pushed",
                    payload={
                        "view_id": f"view-{number:04d}",
                        "spec": spec.model_dump(),
                    },
                ),
            )

    async def finish_conversation_turn(
        self, session_id: UUID, conversation_turn_id: UUID, error: str | None = None
    ) -> None:
        if error is not None:
            error = (
                await self.privacy.tokenize(
                    session_id,
                    Raw(value=error),
                    path="assistant_output",
                )
            ).value
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
