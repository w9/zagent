from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from zagent.cohort import HANDLE_TTL, ClinicalStore, HandleError
from zagent.drafts import CATALOG, DraftContent
from zagent.job_worker import JobRecord
from zagent.privacy import Raw
from zagent.store import NOTIFY_CHANNEL, NotFound

TERMINAL_STATES = {"completed", "failed"}


class LeaseLost(RuntimeError):
    pass


class JobLease(BaseModel):
    model_config = ConfigDict(frozen=True)
    session_id: UUID
    job_id: str
    owner: UUID
    revision: int
    attempt: int
    execution_name: str
    snapshot: dict
    terminal_exit_code: int | None = None


def json_row(row) -> dict:
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in dict(row).items()
    }


class JobStore:
    def __init__(self, clinical: ClinicalStore):
        self.clinical = clinical
        self.store = clinical.store

    async def freeze_input(self, session_id: UUID, job_id: str, content: DraftContent) -> dict:
        selection = await self.clinical.resolve(session_id, content.specimen_handle, "specimens")
        session = await self.store.get_session(session_id)
        async with self.clinical.site_connection(session.site_id) as connection:
            specimens = [
                dict(row)
                for row in await connection.fetch(
                    """SELECT specimens.id, patient_id, kind, assayed_kind, purity, simulation, mrn
                   FROM specimens JOIN patients ON patients.id=specimens.patient_id
                   AND patients.site_id=specimens.site_id WHERE specimens.id=ANY($1::text[])
                   ORDER BY specimens.id""",
                    selection["row_ids"],
                )
            ]
            libraries = [
                dict(row)
                for row in await connection.fetch(
                    """SELECT id, specimen_id, prep, coverage FROM libraries
                   WHERE specimen_id=ANY($1::text[]) ORDER BY id""",
                    selection["row_ids"],
                )
            ]
        for specimen in specimens:
            specimen["kind"] = selection["selection_roles"].get(specimen["id"], specimen["kind"])
        return {
            "execution_id": f"{session_id}:{job_id}",
            "job_id": job_id,
            "app_id": content.app_id,
            "parameters": content.parameters,
            "specimens": specimens,
            "libraries": libraries,
        }

    async def notify(self, connection, session_id: UUID) -> None:
        await connection.execute("SELECT pg_notify($1, $2)", NOTIFY_CHANNEL, f"jobs:{session_id}")

    async def create_handle(
        self,
        connection,
        session_id: UUID,
        *,
        job_id: str | None = None,
        state: str = "all",
        since: datetime | None = None,
    ) -> str:
        await connection.fetchval(
            "SELECT id FROM sessions WHERE id=$1 FOR NO KEY UPDATE", session_id
        )
        number = await connection.fetchval(
            "SELECT count(*)+1 FROM job_handles WHERE session_id=$1",
            session_id,
        )
        handle = f"jobs-{number:04d}"
        await connection.execute(
            "INSERT INTO job_handles VALUES ($1,$2,$3,$4,$5,$6)",
            session_id,
            handle,
            job_id,
            state,
            since,
            self.clinical.clock() + HANDLE_TTL,
        )
        return handle

    async def read_handle(self, session_id: UUID, handle: str) -> dict:
        query = await self.store.pool.fetchrow(
            "SELECT * FROM job_handles WHERE session_id=$1 AND handle=$2",
            session_id,
            handle,
        )
        if query is None:
            raise NotFound("Job view not found in this session")
        if query["expires_at"] <= self.clinical.clock():
            raise HandleError("Job view expired after 24 hours; request a new view")
        states = {
            "active": ["pending", "starting", "running", "retrying"],
            "failed": ["failed"],
            "completed": ["completed"],
        }.get(query["state_filter"])
        rows = await self.store.pool.fetch(
            """SELECT id FROM jobs WHERE session_id=$1 AND ($2::text IS NULL OR id=$2)
               AND ($3::text[] IS NULL OR status=ANY($3))
               AND ($4::timestamptz IS NULL OR created_at >= $4)
               ORDER BY created_at DESC, id DESC LIMIT 50""",
            session_id,
            query["job_id"],
            states,
            query["created_since"],
        )
        return {"handle": handle, "jobs": [await self.read(session_id, row["id"]) for row in rows]}

    async def claim(
        self, owner: UUID, *, session_id: UUID | None = None, lease_seconds: float = 15
    ) -> JobLease | None:
        async with self.store.pool.acquire() as connection, connection.transaction():
            queue = await connection.fetchrow(
                """SELECT * FROM job_queue WHERE completed_at IS NULL
                   AND available_at <= clock_timestamp()
                   AND (lease_until IS NULL OR lease_until < clock_timestamp())
                   AND ($1::uuid IS NULL OR session_id=$1)
                   ORDER BY available_at, session_id, job_id
                   FOR UPDATE SKIP LOCKED LIMIT 1""",
                session_id,
            )
            if queue is None:
                return None
            session_id, job_id = queue["session_id"], queue["job_id"]
            revision = await connection.fetchval(
                """UPDATE job_queue SET lease_owner=$3,
                   lease_until=clock_timestamp()+$4*interval '1 second', revision=revision+1
                   WHERE session_id=$1 AND job_id=$2 RETURNING revision""",
                session_id,
                job_id,
                owner,
                lease_seconds,
            )
            job = await connection.fetchrow(
                "SELECT * FROM jobs WHERE session_id=$1 AND id=$2 FOR UPDATE",
                session_id,
                job_id,
            )
            snapshot = await connection.fetchval(
                "SELECT snapshot FROM privacy.job_inputs WHERE session_id=$1 AND job_id=$2",
                session_id,
                job_id,
            )
            if snapshot is None:
                raise ValueError("Confirmed job has no frozen execution input")
            name = f"zagent-job-{session_id.hex}-{job_id}-{job['attempt']}"
            await connection.execute(
                """INSERT INTO job_attempts (session_id,job_id,attempt,execution_name)
                   VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING""",
                session_id,
                job_id,
                job["attempt"],
                name,
            )
            await connection.execute(
                """UPDATE jobs SET status=CASE WHEN status IN ('pending','retrying')
                   THEN 'starting' ELSE status END,
                   started_at=COALESCE(started_at,clock_timestamp()),
                   version=version+1 WHERE session_id=$1 AND id=$2""",
                session_id,
                job_id,
            )
            await self.notify(connection, session_id)
            return JobLease(
                session_id=session_id,
                job_id=job_id,
                owner=owner,
                revision=revision,
                attempt=job["attempt"],
                execution_name=name,
                snapshot=snapshot,
                terminal_exit_code=queue["terminal_exit_code"],
            )

    async def fence(self, connection, lease: JobLease) -> None:
        held = await connection.fetchval(
            """SELECT revision FROM job_queue WHERE session_id=$1 AND job_id=$2
               AND lease_owner=$3 AND revision=$4 AND lease_until > clock_timestamp()
               AND completed_at IS NULL FOR UPDATE""",
            lease.session_id,
            lease.job_id,
            lease.owner,
            lease.revision,
        )
        if held is None:
            raise LeaseLost("Dispatcher no longer owns this execution lease")

    async def renew(self, lease: JobLease, seconds: float = 15) -> None:
        async with self.store.pool.acquire() as connection, connection.transaction():
            await self.fence(connection, lease)
            await connection.execute(
                """UPDATE job_queue SET lease_until=clock_timestamp()+$3*interval '1 second'
                   WHERE session_id=$1 AND job_id=$2""",
                lease.session_id,
                lease.job_id,
                seconds,
            )

    async def ingest(self, lease: JobLease, source: JobRecord) -> JobRecord | None:
        protected = await self.store.privacy.tokenize(
            lease.session_id,
            Raw(value=source.model_dump()),
            path="job_log",
            external=True,
        )
        record = JobRecord.model_validate(protected.value)
        state = record.attributes.get("job.state")
        progress = record.attributes.get("job.progress")
        if state not in {"running", "retrying", "failed", "completed"}:
            raise ValueError("Unknown execution state")
        if not isinstance(progress, (float, int)) or not 0 <= progress <= 1:
            raise ValueError("Invalid execution progress")
        attempt = lease.attempt
        if type(attempt) is not int or not 1 <= attempt <= 2:
            raise ValueError("Invalid execution attempt")
        async with self.store.pool.acquire() as connection, connection.transaction():
            await self.fence(connection, lease)
            duplicate = await connection.fetchval(
                """SELECT 1 FROM job_logs WHERE session_id=$1 AND job_id=$2
                   AND attempt=$3 AND worker_sequence=$4""",
                lease.session_id,
                lease.job_id,
                attempt,
                record.sequence,
            )
            if duplicate:
                return None
            previous = await connection.fetchval(
                """SELECT COALESCE(max(worker_sequence),0) FROM job_logs
                   WHERE session_id=$1 AND job_id=$2 AND attempt=$3""",
                lease.session_id,
                lease.job_id,
                attempt,
            )
            if record.sequence != previous + 1:
                raise ValueError("Noncontiguous worker log")
            sequence = await connection.fetchval(
                """UPDATE jobs SET log_seq=log_seq+1, version=version+1, status=$3,
                   progress=$4, detail=$5, attempt=$6
                   WHERE session_id=$1 AND id=$2 RETURNING log_seq""",
                lease.session_id,
                lease.job_id,
                state,
                progress,
                record.body,
                attempt,
            )
            await connection.execute(
                "INSERT INTO job_logs VALUES ($1,$2,$3,$4,$5,$6)",
                lease.session_id,
                lease.job_id,
                sequence,
                attempt,
                record.sequence,
                record.model_dump(),
            )
            await connection.execute(
                """UPDATE job_attempts SET status=$4,
                         finished_at=CASE WHEN $4 IN ('completed','failed','evicted')
                              THEN clock_timestamp() ELSE finished_at END,
                         exit_code=CASE WHEN $4='evicted' THEN 75 ELSE exit_code END
                   WHERE session_id=$1 AND job_id=$2 AND attempt=$3""",
                lease.session_id,
                lease.job_id,
                attempt,
                state,
            )
            await self.notify(connection, lease.session_id)
            return record

    async def record_terminal(self, lease: JobLease, exit_code: int) -> None:
        async with self.store.pool.acquire() as connection, connection.transaction():
            await self.fence(connection, lease)
            previous = await connection.fetchval(
                "SELECT terminal_exit_code FROM job_queue WHERE session_id=$1 AND job_id=$2",
                lease.session_id,
                lease.job_id,
            )
            if previous is not None and previous != exit_code:
                raise ValueError("Execution terminal result changed")
            await connection.execute(
                "UPDATE job_queue SET terminal_exit_code=$3 WHERE session_id=$1 AND job_id=$2",
                lease.session_id,
                lease.job_id,
                exit_code,
            )

    async def finish(self, lease: JobLease, exit_code: int) -> None:
        async with self.store.pool.acquire() as connection, connection.transaction():
            await self.fence(connection, lease)
            state = await connection.fetchval(
                "SELECT status FROM jobs WHERE session_id=$1 AND id=$2 FOR UPDATE",
                lease.session_id,
                lease.job_id,
            )
            attempt = await connection.fetchval(
                "SELECT attempt FROM jobs WHERE session_id=$1 AND id=$2",
                lease.session_id,
                lease.job_id,
            )
            retry = exit_code in {75, 137} and attempt < 2
            final = (
                "retrying"
                if retry
                else "completed"
                if exit_code == 0 and state == "completed"
                else "failed"
            )
            await connection.execute(
                """UPDATE job_attempts SET status=$4, exit_code=$5, finished_at=clock_timestamp()
                   WHERE session_id=$1 AND job_id=$2 AND attempt=$3""",
                lease.session_id,
                lease.job_id,
                attempt,
                "evicted" if retry else final,
                exit_code,
            )
            await connection.execute(
                """UPDATE jobs SET status=$3, version=version+1, attempt=attempt+$4,
                   finished_at=CASE WHEN $4=0 THEN clock_timestamp() ELSE NULL END
                   WHERE session_id=$1 AND id=$2""",
                lease.session_id,
                lease.job_id,
                final,
                1 if retry else 0,
            )
            await connection.execute(
                """UPDATE job_queue SET lease_owner=NULL, lease_until=NULL,
                   completed_at=CASE WHEN $3 THEN NULL ELSE clock_timestamp() END
                   WHERE session_id=$1 AND job_id=$2""",
                lease.session_id,
                lease.job_id,
                retry,
            )
            await self.notify(connection, lease.session_id)

    async def read(
        self, session_id: UUID, job_id: str, *, after: int | None = None, limit: int = 40
    ) -> dict:
        job = await self.store.pool.fetchrow(
            "SELECT * FROM jobs WHERE session_id=$1 AND id=$2",
            session_id,
            job_id,
        )
        if job is None:
            raise NotFound("Job not found in this session")
        records = await self.store.pool.fetch(
            """SELECT seq, attempt, record FROM job_logs WHERE session_id=$1 AND job_id=$2
               AND seq > $3 ORDER BY seq LIMIT $4""",
            session_id,
            job_id,
            max(0, job["log_seq"] - limit) if after is None else after,
            min(limit, 100),
        )
        attempts = await self.store.pool.fetch(
            """SELECT attempt, status, started_at, finished_at, exit_code FROM job_attempts
               WHERE session_id=$1 AND job_id=$2 ORDER BY attempt""",
            session_id,
            job_id,
        )
        content = job["content"]
        return {
            "job_id": job_id,
            "app_id": content["app_id"],
            "title": CATALOG[content["app_id"]].title,
            "parameters": content["parameters"],
            "specimen_handle": content["specimen_handle"],
            **{
                key: json_row(job)[key]
                for key in (
                    "status",
                    "progress",
                    "detail",
                    "version",
                    "attempt",
                    "log_seq",
                    "created_at",
                    "started_at",
                    "finished_at",
                )
            },
            "logs": [dict(row) for row in records],
            "attempts": [json_row(row) for row in attempts],
        }
