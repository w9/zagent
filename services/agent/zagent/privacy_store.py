import asyncio
from typing import Any
from uuid import UUID

import asyncpg

from zagent.privacy import (
    Binding,
    Detector,
    Identifier,
    PrivacyError,
    Raw,
    SessionTokens,
    Tokenized,
    normalize_identifier,
)


class PrivacyStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self.detector: Detector | None = None
        self.registry_lock = asyncio.Lock()

    async def registry(self) -> list[Identifier]:
        identifiers = []
        for row in await self.pool.fetch(
            "SELECT id, mrn, display_name FROM patients ORDER BY site_id, id"
        ):
            identifiers.extend(Identifier(value=value) for value in row.values() if value)
        for entity, kind in (("specimens", "SP"), ("libraries", "LB")):
            identifiers.extend(
                Identifier(value=row["id"], kind=kind)
                for row in await self.pool.fetch(f"SELECT id FROM {entity} ORDER BY id")
            )
        identifiers.extend(
            Identifier(value=row["value"], kind=row["kind"])
            for row in await self.pool.fetch(
                "SELECT DISTINCT value, kind FROM privacy.tokens WHERE kind <> 'LIT'"
            )
        )
        return identifiers

    async def load_detector(self) -> Detector:
        async with self.registry_lock:
            if self.detector is None:
                self.detector = Detector(await self.registry())
            return self.detector

    async def _session(self, connection: asyncpg.Connection, session_id: UUID) -> SessionTokens:
        rows = await connection.fetch(
            "SELECT token, kind, value FROM privacy.tokens WHERE session_id = $1 ORDER BY token",
            session_id,
        )
        return SessionTokens(await self.load_detector(), [Binding(**dict(row)) for row in rows])

    async def _save(
        self, connection: asyncpg.Connection, session_id: UUID, vault: SessionTokens
    ) -> None:
        await connection.executemany(
            """INSERT INTO privacy.tokens (session_id, token, kind, value, normalized_value)
               VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING""",
            [
                (session_id, item.token, item.kind, item.value, normalize_identifier(item.value))
                for item in vault.bindings
            ],
        )

    async def tokenize(
        self,
        session_id: UUID,
        raw: Raw[Any],
        *,
        path: str,
        schema: dict | None = None,
        external: bool = False,
    ) -> Tokenized[Any]:
        await self.load_detector()
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 710006))", str(session_id)
            )
            exists = await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1",
                session_id,
            )
            if exists is None:
                raise PrivacyError("Unknown privacy session")
            vault = await self._session(connection, session_id)
            result = vault.tokenize(raw, path=path, schema=schema, external=external)
            await self._save(connection, session_id, vault)
            return result

    async def resolve(
        self, session_id: UUID, value: Tokenized[Any], *, strict: bool = False
    ) -> Raw[Any]:
        await self.load_detector()
        async with self.pool.acquire() as connection:
            vault = await self._session(connection, session_id)
        return vault.resolve(value, strict=strict)

    async def bindings(self, session_id: UUID) -> list[Binding]:
        await self.load_detector()
        async with self.pool.acquire() as connection:
            return (await self._session(connection, session_id)).bindings

    async def migrate_history(self) -> None:
        await self.load_detector()
        async with self.pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(710006)")
            if await connection.fetchval(
                "SELECT value FROM privacy.settings WHERE name = 'history_tokenized'"
            ):
                return
            await connection.execute("LOCK TABLE events IN ACCESS EXCLUSIVE MODE")
            await connection.execute("INSERT INTO privacy.legacy_events SELECT * FROM events")
            await connection.execute("ALTER TABLE events DISABLE TRIGGER immutable_events")
            session_ids = await connection.fetch("SELECT DISTINCT session_id FROM events")
            for row in session_ids:
                session_id = row["session_id"]
                vault = await self._session(connection, session_id)
                events = await connection.fetch(
                    "SELECT seq, payload FROM events WHERE session_id = $1 ORDER BY seq",
                    session_id,
                )
                updates = []
                for event in events:
                    payload = vault.tokenize(
                        Raw(value=event["payload"]), path="assistant_output"
                    ).value
                    if payload != event["payload"]:
                        updates.append((session_id, event["seq"], payload))
                await connection.executemany(
                    "UPDATE events SET payload = $3 WHERE session_id = $1 AND seq = $2",
                    updates,
                )
                await self._save(connection, session_id, vault)
            await connection.execute("ALTER TABLE events ENABLE TRIGGER immutable_events")
            await connection.execute(
                "INSERT INTO privacy.settings VALUES ('history_tokenized', '1')"
            )
