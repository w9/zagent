from typing import Any
from uuid import UUID

from zagent.cohort import ClinicalStore, HandleError
from zagent.drafts import (
    CATALOG,
    DraftContent,
    DraftIssue,
    DraftState,
    JobState,
    content_hash,
    default_parameters,
    draft_changes,
    validate_draft,
)
from zagent.events import EventDraft
from zagent.jobs import JobStore
from zagent.privacy import Raw
from zagent.store import ConversationTurnConflict, NotFound


class DraftConflict(Exception):
    def __init__(self, current: DraftState, changes: list[dict], reason: str = "stale_version"):
        self.current = current
        self.changes = changes
        self.reason = reason
        super().__init__("The draft changed. Review the current values before confirming.")


class InvalidDraft(Exception):
    def __init__(self, current: DraftState):
        self.current = current
        super().__init__("Resolve the draft's validation issues before confirmation.")


class DraftStore:
    def __init__(self, clinical: ClinicalStore):
        self.clinical = clinical
        self.store = clinical.store

    async def validate(self, session_id: UUID, content: DraftContent) -> list[DraftIssue]:
        records, libraries = [], []
        if content.specimen_handle:
            try:
                selection = await self.clinical.resolve(
                    session_id, content.specimen_handle, "specimens"
                )
                session = await self.store.get_session(session_id)
                async with self.clinical.site_connection(session.site_id) as connection:
                    records = [
                        dict(row)
                        for row in await connection.fetch(
                            "SELECT id, patient_id, kind FROM specimens WHERE id = ANY($1::text[])",
                            selection["row_ids"],
                        )
                    ]
                    libraries = [
                        dict(row)
                        for row in await connection.fetch(
                            "SELECT specimen_id, prep FROM libraries "
                            "WHERE specimen_id = ANY($1::text[])",
                            selection["row_ids"],
                        )
                    ]
                    for record in records:
                        record["kind"] = selection["selection_roles"].get(
                            record["id"], record["kind"]
                        )
            except (HandleError, NotFound):
                return [
                    DraftIssue(
                        code="invalid_selection",
                        field="specimen_handle",
                        message="The specimen query is unavailable or expired. Run it again.",
                    )
                ]
        return validate_draft(content, records, libraries)

    @staticmethod
    def state(row: Any, *, job_id: str | None = None) -> DraftState:
        return DraftState(
            **row["content"],
            draft_id=row["id"],
            view_id=row["view_id"],
            version=row["version"],
            content_hash=row["content_hash"],
            validation=row["validation"],
            status=row["status"],
            job_id=job_id,
        )

    async def get(self, session_id: UUID, draft_id: str) -> DraftState:
        row = await self.store.pool.fetchrow(
            "SELECT * FROM drafts WHERE session_id = $1 AND id = $2",
            session_id,
            draft_id,
        )
        if row is None:
            raise NotFound("Draft not found")
        job_id = await self.store.pool.fetchval(
            "SELECT id FROM jobs WHERE session_id = $1 AND draft_id = $2",
            session_id,
            draft_id,
        )
        return self.state(row, job_id=job_id)

    async def update(
        self,
        session_id: UUID,
        *,
        draft_id: str | None = None,
        conversation_turn_id: UUID | None = None,
        app_id: str | None = None,
        specimen_handle: str | None = None,
        parameters: dict | None = None,
        expected_hash: str | None = None,
    ) -> DraftState:
        parameters = (
            await self.store.privacy.tokenize(
                session_id,
                Raw(value=parameters or {}),
                path="draft_updated",
            )
        ).value
        async with self.store.pool.acquire() as connection, connection.transaction():
            session = await connection.fetchrow(
                "SELECT * FROM sessions WHERE id = $1 FOR NO KEY UPDATE", session_id
            )
            if session is None:
                raise NotFound("Session not found")
            if conversation_turn_id is not None:
                active = await connection.fetchval(
                    "SELECT status FROM conversation_turns WHERE session_id = $1 AND id = $2",
                    session_id,
                    conversation_turn_id,
                )
                if active != "running":
                    raise ConversationTurnConflict(
                        "Draft mutation requires the requesting active turn"
                    )
            row = (
                await connection.fetchrow(
                    "SELECT * FROM drafts WHERE session_id = $1 AND id = $2 FOR UPDATE",
                    session_id,
                    draft_id,
                )
                if draft_id
                else None
            )
            if draft_id and row is None:
                raise NotFound("Draft not found")
            if row is not None:
                current = self.state(row)
                if current.status != "editing":
                    raise DraftConflict(current, [], "already_submitted")
                if expected_hash is not None and current.content_hash != expected_hash:
                    raise DraftConflict(
                        current, await self.changes(connection, current, session_id, expected_hash)
                    )
                origin = conversation_turn_id or row["conversation_turn_id"]
                selected_app = app_id or current.app_id
                params = (
                    current.parameters
                    if selected_app == current.app_id
                    else default_parameters(selected_app)
                )
                selected_handle = specimen_handle or current.specimen_handle
            else:
                if app_id not in CATALOG or conversation_turn_id is None:
                    raise ValueError("A new draft requires an application and active turn")
                selected_app, params, selected_handle = (
                    app_id,
                    default_parameters(app_id),
                    specimen_handle,
                )
                origin = conversation_turn_id
            merged = {**params, **parameters}
            content = DraftContent(
                app_id=selected_app,
                specimen_handle=selected_handle,
                parameters={key: value for key, value in merged.items() if value is not None},
            )
            validation = await self.validate(session_id, content)
            digest = content_hash(content)
            if (
                row is not None
                and digest == row["content_hash"]
                and [item.model_dump() for item in validation] == row["validation"]
            ):
                return current
            if row is None:
                number = await connection.fetchval(
                    "SELECT count(*) + 1 FROM drafts WHERE session_id = $1", session_id
                )
                draft_id = f"draft-{number:04d}"
                view_number = await connection.fetchval(
                    "SELECT count(*) + 1 FROM events "
                    "WHERE session_id = $1 AND type = 'view_pushed'",
                    session_id,
                )
                view_id, version = f"view-{view_number:04d}", 1
            else:
                view_id, version = row["view_id"], row["version"] + 1
            state = DraftState(
                **content.model_dump(),
                draft_id=draft_id,
                view_id=view_id,
                version=version,
                content_hash=digest,
                validation=validation,
            )
            await connection.execute(
                """INSERT INTO drafts VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'editing')
                   ON CONFLICT (session_id,id) DO UPDATE SET version=$5, content_hash=$6,
                   content=$7, validation=$8""",
                session_id,
                draft_id,
                origin,
                view_id,
                version,
                digest,
                content.model_dump(),
                [item.model_dump() for item in validation],
            )
            await connection.execute(
                "INSERT INTO draft_revisions VALUES ($1,$2,$3,$4,$5)",
                session_id,
                draft_id,
                version,
                digest,
                content.model_dump(),
            )
            await self.store._append(
                connection,
                session_id,
                origin,
                EventDraft(type="draft_updated", payload={"draft": state.model_dump()}),
                allow_finished=True,
            )
            if row is None:
                await self.store._append(
                    connection,
                    session_id,
                    origin,
                    EventDraft(
                        type="view_pushed",
                        payload={
                            "view_id": view_id,
                            "spec": {
                                "kind": "draft_form",
                                "version": 1,
                                "props": {
                                    "title": CATALOG[selected_app].title,
                                    "draft_id": draft_id,
                                },
                            },
                        },
                    ),
                    allow_finished=True,
                )
            return state

    async def changes(
        self, connection, current: DraftState, session_id: UUID, expected_hash: str
    ) -> list[dict]:
        previous = await connection.fetchval(
            """SELECT content FROM draft_revisions
                    WHERE session_id=$1 AND draft_id=$2 AND content_hash=$3
               ORDER BY version DESC LIMIT 1""",
            session_id,
            current.draft_id,
            expected_hash,
        )
        return (
            draft_changes(
                DraftContent.model_validate(previous),
                DraftContent(
                    app_id=current.app_id,
                    specimen_handle=current.specimen_handle,
                    parameters=current.parameters,
                ),
            )
            if previous
            else [{"field": "version", "before": "unrecognized", "after": current.version}]
        )

    async def confirm(self, session_id: UUID, draft_id: str, expected_hash: str) -> JobState:
        async with self.store.pool.acquire() as connection, connection.transaction():
            await connection.fetchval(
                "SELECT id FROM sessions WHERE id=$1 FOR NO KEY UPDATE", session_id
            )
            row = await connection.fetchrow(
                "SELECT * FROM drafts WHERE session_id=$1 AND id=$2 FOR UPDATE",
                session_id,
                draft_id,
            )
            if row is None:
                raise NotFound("Draft not found")
            current = self.state(row)
            if current.content_hash != expected_hash:
                raise DraftConflict(
                    current, await self.changes(connection, current, session_id, expected_hash)
                )
            existing = await connection.fetchrow(
                "SELECT * FROM jobs WHERE session_id=$1 AND draft_id=$2", session_id, draft_id
            )
            if existing:
                return JobState(
                    **existing["content"],
                    job_id=existing["id"],
                    draft_id=draft_id,
                    confirmed_version=existing["confirmed_version"],
                    content_hash=expected_hash,
                )
            content = DraftContent.model_validate(row["content"])
            current.validation = await self.validate(session_id, content)
            if current.validation:
                raise InvalidDraft(current)
            number = await connection.fetchval(
                "SELECT count(*) + 1 FROM jobs WHERE session_id=$1", session_id
            )
            job_id = f"job-{number:04d}"
            await connection.execute(
                """INSERT INTO jobs
                         (session_id,id,draft_id,confirmed_version,confirmation_hash,content_hash,content)
                   VALUES ($1,$2,$3,$4,$5,$5,$6)""",
                session_id,
                job_id,
                draft_id,
                current.version,
                expected_hash,
                content.model_dump(),
            )
            snapshot = await JobStore(self.clinical).freeze_input(session_id, job_id, content)
            await connection.execute(
                "INSERT INTO privacy.job_inputs VALUES ($1, $2, $3, $4)",
                session_id,
                job_id,
                expected_hash,
                snapshot,
            )
            await connection.execute(
                "INSERT INTO job_queue (session_id, job_id) VALUES ($1, $2)",
                session_id,
                job_id,
            )
            await connection.execute("SELECT pg_notify('zagent_jobs', 'queued')")
            await connection.execute(
                "UPDATE drafts SET status='submitted' WHERE session_id=$1 AND id=$2",
                session_id,
                draft_id,
            )
            current.status, current.job_id = "submitted", job_id
            job = JobState(
                **content.model_dump(),
                job_id=job_id,
                draft_id=draft_id,
                confirmed_version=current.version,
                content_hash=expected_hash,
            )
            origin = row["conversation_turn_id"]
            await self.store._append(
                connection,
                session_id,
                origin,
                EventDraft(type="draft_updated", payload={"draft": current.model_dump()}),
                allow_finished=True,
            )
            await self.store._append(
                connection,
                session_id,
                origin,
                EventDraft(type="job_submitted", payload={"job": job.model_dump()}),
                allow_finished=True,
            )
            view_number = await connection.fetchval(
                "SELECT count(*) + 1 FROM events WHERE session_id=$1 AND type='view_pushed'",
                session_id,
            )
            handle = await JobStore(self.clinical).create_handle(
                connection, session_id, job_id=job_id
            )
            await self.store._append(
                connection,
                session_id,
                origin,
                EventDraft(
                    type="view_pushed",
                    payload={
                        "view_id": f"view-{view_number:04d}",
                        "spec": {
                            "kind": "job_card",
                            "version": 2,
                            "props": {
                                "title": CATALOG[content.app_id].title,
                                "handle": handle,
                                "server": "jobs",
                                "resource_uri": "ui://jobs/card",
                            },
                        },
                    },
                ),
                allow_finished=True,
            )
            return job
