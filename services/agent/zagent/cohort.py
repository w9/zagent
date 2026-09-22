import asyncio
import os
import random
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from zagent.store import NotFound, Store

SITES = ("northgate", "lakeside", "sequoia", "cedar", "harbor")
SITE_ROLES = {site: f"zagent_site_{site}" for site in SITES}
FROZEN_NOW = datetime(2026, 1, 15, 12, tzinfo=UTC)
HANDLE_TTL = timedelta(hours=24)
MAX_RESULT_ROWS = 200


class HandleError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def configured_clock() -> Callable[[], datetime]:
    if value := os.environ.get("ZAGENT_FROZEN_TIME"):
        frozen = datetime.fromisoformat(value)
        if frozen.tzinfo is None:
            raise ValueError("ZAGENT_FROZEN_TIME must include a timezone")
        return lambda: frozen
    if os.environ.get("ZAGENT_LLM_MODE", "replay") == "replay":
        return lambda: FROZEN_NOW
    return utcnow


def generate_cohort(now: datetime, seed: int = 41872) -> dict[str, list[dict[str, Any]]]:
    randomizer = random.Random(seed)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = midnight + (now - midnight) / 2
    yesterday = midnight - timedelta(hours=12)
    cohort: dict[str, list[dict[str, Any]]] = {"patients": [], "specimens": [], "libraries": []}
    for site_index, site in enumerate(SITES):
        for patient_index in range(10):
            number = 41872 + patient_index
            mrn = (
                f"NGC-{number:07d}",
                f"LHX/26/{number:05d}",
                f"SQ-AB-{patient_index + 1000:04d}",
                f"CV{number:08d}",
                f"{site_index + 700:03d}-42-{patient_index + 1000:04d}",
            )[site_index]
            patient_id = f"PAT-{site}-{patient_index + 1:03d}"
            cohort["patients"].append(
                {
                    "id": patient_id,
                    "site_id": site,
                    "mrn": mrn,
                    "display_name": (
                        (
                            "Mira",
                            "Kellan",
                            "Tessa",
                            "Arin",
                            "Nella",
                            "Ciro",
                            "Elara",
                            "Vesa",
                            "Lorin",
                            "Sela",
                        )[patient_index]
                        + " "
                        + ("Vellorin", "Neralis", "Corvellan", "Merovin", "Talvessa")[site_index]
                    ),
                    "birth_year": randomizer.randint(1940, 2005),
                }
            )
            for kind_index, kind in enumerate(("tumor", "normal", "RNA")):
                if patient_index == 3 and kind == "normal":
                    continue
                specimen_id = f"SPC-{site}-{patient_index + 1:03d}-{kind_index + 1}"
                received = today if kind == "RNA" else yesterday
                purity = 0.12 if patient_index == 1 else round(randomizer.uniform(0.55, 0.95), 2)
                assayed_kind = kind
                if patient_index == 0 and kind != "RNA":
                    assayed_kind = "normal" if kind == "tumor" else "tumor"
                cohort["specimens"].append(
                    {
                        "id": specimen_id,
                        "site_id": site,
                        "patient_id": patient_id,
                        "kind": kind,
                        "assayed_kind": assayed_kind,
                        "purity": purity if kind == "tumor" else None,
                        "collected_at": received - timedelta(hours=4),
                        "received_at": received,
                    }
                )
                coverage = 8.0 if patient_index == 2 else round(randomizer.uniform(35, 120), 1)
                cohort["libraries"].append(
                    {
                        "id": f"LIB-{site}-{patient_index + 1:03d}-{kind_index + 1}",
                        "site_id": site,
                        "specimen_id": specimen_id,
                        "prep": "RNA-seq" if kind == "RNA" else "PCR-free WGS",
                        "coverage": coverage,
                        "qc_status": "review" if coverage < 20 else "passed",
                    }
                )
    return cohort


class ClinicalStore:
    def __init__(self, store: Store, clock: Callable[[], datetime] = utcnow):
        self.store = store
        self.clock = clock

    async def seed(self, seed: int = 41872) -> None:
        cohort = generate_cohort(self.clock(), seed)
        async with self.store.pool.acquire() as connection, connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock(710004)")
            for entity, records in cohort.items():
                columns = list(records[0])
                placeholders = ", ".join(f"${index + 1}" for index in range(len(columns)))
                updates = ", ".join(
                    f"{column} = EXCLUDED.{column}"
                    for column in columns
                    if column not in {"id", "site_id"}
                )
                await connection.executemany(
                    f"INSERT INTO {entity} ({', '.join(columns)}) VALUES ({placeholders}) "
                    f"ON CONFLICT (id, site_id) DO UPDATE SET {updates}",
                    [tuple(record[column] for column in columns) for record in records],
                )
        from zagent.privacy_store import PrivacyStore

        if isinstance(self.store.privacy, PrivacyStore):
            self.store.privacy.detector = None

    @asynccontextmanager
    async def site_connection(self, site_id: str) -> AsyncIterator[asyncpg.Connection]:
        role = SITE_ROLES.get(site_id)
        if role is None:
            raise ValueError("Unknown clinical site")
        async with self.store.pool.acquire() as connection, connection.transaction():
            await connection.execute(f"SET LOCAL ROLE {role}")
            yield connection

    async def save_handle(
        self,
        session_id: UUID,
        entity: str,
        columns: list[dict[str, str]],
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len(records) > MAX_RESULT_ROWS:
            raise HandleError("Result too large; narrow the query")
        session = await self.store.get_session(session_id)
        rows = [
            [
                value.isoformat() if isinstance(value, datetime) else value
                for value in (record[column["key"]] for column in columns)
            ]
            for record in records
        ]
        async with self.store.pool.acquire() as connection, connection.transaction():
            await connection.fetchval(
                "SELECT id FROM sessions WHERE id = $1 FOR UPDATE", session_id
            )
            number = await connection.fetchval(
                "SELECT count(*) + 1 FROM query_handles WHERE session_id = $1", session_id
            )
            handle = f"query-{number:04d}"
            await connection.execute(
                """INSERT INTO query_handles
                   (session_id, handle, site_id, entity, columns, rows,
                    row_ids, row_count, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                session_id,
                handle,
                session.site_id,
                entity,
                columns,
                rows,
                [record["id"] for record in records],
                len(records),
                self.clock() + HANDLE_TTL,
            )
        return {"handle": handle, "count": len(records), "schema": columns}

    async def resolve(self, session_id: UUID, handle: str, entity: str | None = None) -> dict:
        session = await self.store.get_session(session_id)
        async with self.site_connection(session.site_id) as connection:
            row = await connection.fetchrow(
                "SELECT * FROM query_handles WHERE session_id = $1 AND handle = $2",
                session_id,
                handle,
            )
        if row is None:
            raise NotFound("Handle not found in this session")
        if row["expires_at"] <= self.clock():
            raise HandleError("Handle expired after 24 hours; run the query again")
        if entity is not None and row["entity"] != entity:
            raise HandleError(f"Expected a {entity} handle")
        return dict(row)

    async def simulate(self, interval: float = 60) -> None:
        while True:
            await asyncio.sleep(interval)
            await self.seed()
