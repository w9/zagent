import asyncio
import json
import logging
import os
import re
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlencode
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

from zagent.agent import Agent, LlmAgent, ScriptedAgent
from zagent.cohort import ClinicalStore, HandleError, configured_clock
from zagent.display import SessionDisplay
from zagent.draft_store import DraftConflict, DraftStore, InvalidDraft
from zagent.drafts import CATALOG
from zagent.events import Projection
from zagent.identity import DEFAULT_PERSONA, PERSONAS, CallerSigner, GrantSigner, PersonaId
from zagent.jobs import JobStore
from zagent.jobs_server import UI_RESOURCES, create_jobs_server
from zagent.llm import GatewayClient
from zagent.privacy import PrivacyError, Raw, Tokenized
from zagent.runtime import Runtime
from zagent.store import DEFAULT_DATABASE_URL, ConversationTurnConflict, NotFound, Session, Store
from zagent.stream import Notifications, tail_events
from zagent.titles import SessionTitles
from zagent.tools import McpToolClient, ToolsGateway

logger = logging.getLogger(__name__)
ARCHIVED_REASON = "Stopped because the session was archived."


class Settings(BaseModel):
    database_url: str = Field(
        default_factory=lambda: os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    coalesce_seconds: float = Field(default=0.18, gt=0)
    poll_seconds: float = Field(default=2, gt=0)
    agent_mode: Literal["llm", "scripted"] = Field(
        default_factory=lambda: os.environ.get("ZAGENT_AGENT", "llm")
    )
    agent_max_tokens: int = Field(
        default_factory=lambda: int(
            os.environ.get(
                "ZAGENT_AGENT_MAX_TOKENS",
                "4096" if os.environ.get("ZAGENT_LLM_MODE") == "live" else "1200",
            )
        ),
        ge=1,
        le=4096,
        validate_default=True,
    )
    gateway_url: str = Field(
        default_factory=lambda: os.environ.get("ZAGENT_GATEWAY_URL", "http://127.0.0.1:8001")
    )
    tools_url: str = Field(
        default_factory=lambda: os.environ.get("ZAGENT_TOOLS_URL", "http://127.0.0.1:8002/mcp")
    )
    jobs_url: str | None = Field(default_factory=lambda: os.environ.get("ZAGENT_JOBS_URL"))
    broker_url: str | None = Field(default_factory=lambda: os.environ.get("ZAGENT_BROKER_URL"))
    site_id: str = "northgate"
    display_mode: bool = Field(
        default_factory=lambda: os.environ.get("ZAGENT_DISPLAY_MODE", "1") == "1"
    )
    runtime_url: str | None = Field(default_factory=lambda: os.environ.get("ZAGENT_RUNTIME_URL"))
    intranet_url: str = Field(
        default_factory=lambda: os.environ.get("ZAGENT_INTRANET_URL", "http://localhost:5180")
    )
    migrate_database: bool = Field(
        default_factory=lambda: os.environ.get("ZAGENT_MIGRATE", "1") == "1"
    )


class MessageInput(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("A message cannot be blank")
        return text


class AcceptedConversationTurn(BaseModel):
    session_id: UUID
    conversation_turn_id: UUID


class TokenizedMessageInput(BaseModel):
    text: Tokenized[str]
    conversation_turn_id: UUID | None = None
    caller_context: str | None = Field(default=None, max_length=4096)


class RetryInput(BaseModel):
    model_config = {"extra": "forbid"}
    retry_of: UUID
    # Set only by the display edge when it forwards to the runtime.
    conversation_turn_id: UUID | None = None
    caller_context: str | None = Field(default=None, max_length=4096)


class SessionInput(BaseModel):
    model_config = {"extra": "forbid"}
    persona: PersonaId = DEFAULT_PERSONA


class DraftEditInput(BaseModel):
    model_config = {"extra": "forbid"}
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    app_id: str | None = None
    specimen_handle: str | None = Field(default=None, pattern=r"^query-[0-9]{4,}$")
    parameters: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=20
    )


class ConfirmInput(BaseModel):
    model_config = {"extra": "forbid"}
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RenameInput(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ArchiveInput(BaseModel):
    model_config = {"extra": "forbid"}
    force: bool = False


class StopInput(BaseModel):
    model_config = {"extra": "forbid"}
    reason: str = Field(min_length=1, max_length=200)


class CitationInput(BaseModel):
    model_config = {"extra": "forbid"}
    document: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    snapshot: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    lines: str | None = Field(default=None, pattern=r"^[0-9]{1,5}(?:-[0-9]{1,5})?$")
    q: str | None = Field(default=None, max_length=300)


def create_app(settings: Settings | None = None, agent: Agent | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as resources:
            store = await Store.open(settings.database_url)
            resources.push_async_callback(store.close)
            if settings.migrate_database:
                await store.migrate()
            notifications = await Notifications.open(settings.database_url)
            resources.push_async_callback(notifications.close)
            script = os.environ.get("ZAGENT_SCRIPT")
            selected_agent = agent
            if selected_agent is None and not settings.runtime_url:
                selected_agent = (
                    ScriptedAgent(Path(script) if script else None)
                    if settings.agent_mode == "scripted" or script
                    else LlmAgent(
                        store,
                        GatewayClient(settings.gateway_url),
                        ToolsGateway(
                            store,
                            McpToolClient(
                                url=settings.tools_url,
                                jobs_url=settings.jobs_url,
                                knowledge=McpToolClient(url=settings.broker_url)
                                if settings.broker_url
                                else None,
                            ),
                        ),
                        max_tokens=settings.agent_max_tokens,
                    )
                )
            runtime = Runtime(
                store,
                selected_agent,
                settings.coalesce_seconds,
                titles=SessionTitles(store, selected_agent.gateway)
                if isinstance(selected_agent, LlmAgent)
                else None,
            )
            if runtime.resumable and not settings.runtime_url:
                ownership = await asyncpg.connect(settings.database_url)
                resources.push_async_callback(ownership.close)
                if not await ownership.fetchval("SELECT pg_try_advisory_lock(710008)"):
                    raise RuntimeError("Another runtime already owns this database")
            resources.push_async_callback(runtime.close)
            app.state.store = store
            app.state.runtime = runtime
            app.state.signer = CallerSigner.configured() if settings.display_mode else None
            app.state.grants = GrantSigner.configured() if settings.display_mode else None
            app.state.notifications = notifications
            app.state.clinical = ClinicalStore(store, configured_clock())
            app.state.drafts = DraftStore(app.state.clinical)
            app.state.jobs_client = (
                McpToolClient(url=settings.jobs_url)
                if settings.jobs_url
                else McpToolClient(server=create_jobs_server(app.state.clinical))
            )
            if not settings.runtime_url:
                if runtime.resumable:
                    await runtime.recover()
                else:
                    await store.fail_interrupted_conversation_turns()
            yield

    app = FastAPI(title="Zagent", version="0.1.0", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-bff" if settings.runtime_url else "zagent-runtime", app)

    async def scoped_session(session_id: UUID) -> Session:
        session = await app.state.store.get_session(session_id)
        if session.site_id != settings.site_id:
            raise NotFound("Session not found")
        return session

    async def writable_session(session_id: UUID) -> Session:
        session = await scoped_session(session_id)
        if session.archived_at is not None:
            raise HTTPException(409, "This session is archived. Unarchive it to continue.")
        return session

    async def displayed(session: Session) -> Session:
        session.title = (
            await app.state.store.privacy.resolve(session.id, Tokenized(value=session.title))
        ).value
        return session

    @app.exception_handler(NotFound)
    async def not_found(request: Request, error: NotFound):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ConversationTurnConflict)
    async def conflict(request: Request, error: ConversationTurnConflict):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(HandleError)
    async def expired_handle(request: Request, error: HandleError):
        return JSONResponse(status_code=410, content={"detail": str(error)})

    @app.exception_handler(PrivacyError)
    async def privacy_error(request: Request, error: PrivacyError):
        return JSONResponse(
            status_code=503, content={"detail": "Privacy service unavailable or access denied"}
        )

    @app.exception_handler(DraftConflict)
    async def draft_conflict(request: Request, error: DraftConflict):
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(error),
                "code": error.reason,
                "current": error.current.model_dump(),
                "changes": error.changes,
            },
        )

    @app.exception_handler(InvalidDraft)
    async def invalid_draft(request: Request, error: InvalidDraft):
        return JSONResponse(
            status_code=422, content={"detail": str(error), "current": error.current.model_dump()}
        )

    def display_only() -> None:
        if not settings.display_mode:
            raise HTTPException(403, "This operation requires the human display edge")

    @app.get("/catalog")
    async def catalog():
        return [app.model_dump() for app in CATALOG.values()]

    async def job_view(session_id: UUID, view_id: str):
        display_only()
        await scoped_session(session_id)
        snapshot = await app.state.store.snapshot(session_id)
        view = next((item for item in snapshot.views if item.id == view_id), None)
        if view is None or view.spec.kind not in UI_RESOURCES:
            raise NotFound("MCP view not found in this session")
        return view

    @app.get("/sessions/{session_id}/views/{view_id}/app")
    async def app_resource(session_id: UUID, view_id: str):
        view = await job_view(session_id, view_id)
        uri = UI_RESOURCES[view.spec.kind]
        return {"resource_uri": uri, "html": await app.state.jobs_client.resource(uri)}

    @app.get("/sessions/{session_id}/views/{view_id}/data")
    async def app_data(session_id: UUID, view_id: str):
        view = await job_view(session_id, view_id)
        data = await app.state.jobs_client.app_data(
            session_id, handle=view.spec.props.get("handle"), job_id=view.spec.props.get("job_id")
        )
        return (await app.state.store.privacy.resolve(session_id, Tokenized(value=data))).value

    @app.get("/sessions/{session_id}/jobs/{job_id}")
    async def job_data(
        session_id: UUID, job_id: str, representation: Literal["display", "model"] = "display"
    ):
        display_only()
        await scoped_session(session_id)
        data = await JobStore(app.state.clinical).read(session_id, job_id, limit=100)
        return (
            data
            if representation == "model"
            else (await app.state.store.privacy.resolve(session_id, Tokenized(value=data))).value
        )

    @app.get("/sessions/{session_id}/views/{view_id}/updates")
    async def app_updates(request: Request, session_id: UUID, view_id: str):
        await job_view(session_id, view_id)

        async def updates():
            yield "retry: 1000\n\n"
            previous = None
            async with app.state.notifications.subscribe(f"jobs:{session_id}") as signal:
                while not await request.is_disconnected():
                    signal.clear()
                    try:
                        current = json.dumps(await app_data(session_id, view_id))
                    except (ValueError, HandleError, NotFound):
                        yield (
                            'event: jobs\ndata: {"jobs": [], '
                            '"error": "Job view unavailable or expired"}\n\n'
                        )
                        return
                    if current != previous:
                        yield f"event: jobs\ndata: {current}\n\n"
                        previous = current
                    try:
                        await asyncio.wait_for(signal.wait(), timeout=settings.poll_seconds)
                    except TimeoutError:
                        yield ": keep-alive\n\n"

        return StreamingResponse(
            updates(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform"},
        )

    @app.get("/sessions/{session_id}/drafts/{draft_id}")
    async def get_draft(session_id: UUID, draft_id: str):
        display_only()
        await scoped_session(session_id)
        return await app.state.drafts.get(session_id, draft_id)

    @app.patch("/sessions/{session_id}/drafts/{draft_id}")
    async def edit_draft(session_id: UUID, draft_id: str, body: DraftEditInput):
        display_only()
        await writable_session(session_id)
        if body.app_id is not None and body.app_id not in CATALOG:
            raise HTTPException(422, "Unknown application")
        params = (
            await app.state.store.privacy.tokenize(
                session_id,
                Raw(value=body.parameters),
                path="view_interaction",
                external=True,
            )
        ).value
        return await app.state.drafts.update(
            session_id,
            draft_id=draft_id,
            expected_hash=body.content_hash,
            app_id=body.app_id,
            specimen_handle=body.specimen_handle,
            parameters=params,
        )

    @app.post("/sessions/{session_id}/drafts/{draft_id}/confirm")
    async def confirm_draft(session_id: UUID, draft_id: str, body: ConfirmInput):
        display_only()
        await writable_session(session_id)
        return await app.state.drafts.confirm(session_id, draft_id, body.content_hash)

    @app.get("/health")
    async def health():
        await app.state.store.pool.fetchval("SELECT 1")
        return {
            "status": "ok",
            "mode": "scripted"
            if isinstance(app.state.runtime.agent, ScriptedAgent)
            else os.environ.get("ZAGENT_LLM_MODE", "replay"),
        }

    @app.get("/personas")
    async def personas():
        return {
            "default": DEFAULT_PERSONA,
            "personas": [persona.model_dump() for persona in PERSONAS.values()],
        }

    @app.post("/sessions/{session_id}/citations/open")
    async def open_citation(request: Request, session_id: UUID):
        """Sign the session's persona into the intranet; a form post keeps quotes out of logs."""
        display_only()
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Citations open only from the workbench")
        session = await scoped_session(session_id)
        form = parse_qs((await request.body()).decode(errors="replace")[:4096])
        try:
            citation = CitationInput.model_validate(
                {name: values[0] for name, values in form.items() if values and values[0]}
            )
        except ValidationError as error:
            raise HTTPException(422, "Invalid citation") from error
        token = app.state.grants.mint(
            site=session.site_id,
            persona=session.persona,
            document=citation.document,
            snapshot=citation.snapshot,
            lines=citation.lines,
            quote=re.sub(r"\s+", " ", citation.q).strip() if citation.q else None,
        )
        return RedirectResponse(
            f"{settings.intranet_url.rstrip('/')}/signin/grant?{urlencode({'token': token})}",
            status_code=303,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    @app.post("/sessions", status_code=201, response_model=Session)
    async def create_session(body: SessionInput | None = None):
        return await app.state.store.create_session(
            settings.site_id, body.persona if body else DEFAULT_PERSONA
        )

    @app.get("/sessions", response_model=list[Session])
    async def list_sessions(archived: bool = False):
        sessions = [
            session
            for session in await app.state.store.list_sessions(archived=archived)
            if session.site_id == settings.site_id
        ]
        if settings.display_mode:
            for session in sessions:
                await displayed(session)
        return sessions

    @app.patch("/sessions/{session_id}", response_model=Session)
    async def rename_session(session_id: UUID, body: RenameInput):
        display_only()
        await scoped_session(session_id)
        if not body.title.strip():
            raise HTTPException(422, "A title cannot be blank")
        return await displayed(await app.state.store.rename_session(session_id, body.title))

    async def stop_turn(session_id: UUID) -> None:
        if not settings.runtime_url:
            await app.state.runtime.stop(session_id, ARCHIVED_REASON)
            return
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.runtime_url}/sessions/{session_id}/stop",
                    json={"reason": ARCHIVED_REASON},
                )
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.warning("Could not stop the turn of archived session: %s", error)

    @app.post("/sessions/{session_id}/archive", response_model=Session)
    async def archive_session(session_id: UUID, body: ArchiveInput | None = None):
        display_only()
        session = await scoped_session(session_id)
        if session.archived_at is None:
            responding = await app.state.store.responding(session_id)
            jobs = await JobStore(app.state.clinical).unfinished(session_id)
            if (responding or jobs) and not (body and body.force):
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "This session still has work in progress",
                        "code": "work_in_progress",
                        "responding": responding,
                        "jobs": jobs,
                    },
                )
            session = await app.state.store.set_archived(session_id, True)
            if responding:
                await stop_turn(session_id)
        return await displayed(session)

    @app.post("/sessions/{session_id}/unarchive", response_model=Session)
    async def unarchive_session(session_id: UUID):
        display_only()
        await scoped_session(session_id)
        return await displayed(await app.state.store.set_archived(session_id, False))

    @app.post("/sessions/{session_id}/stop", status_code=204)
    async def stop_session_turn(session_id: UUID, body: StopInput):
        if settings.display_mode:
            raise HTTPException(403, "Archive the session to stop its conversation turn")
        await scoped_session(session_id)
        await app.state.runtime.stop(session_id, body.reason)

    @app.get("/session-list/events")
    async def session_updates(request: Request):
        async def updates():
            yield "retry: 1000\n\n"
            async with app.state.notifications.subscribe("sessions") as signal:
                while not await request.is_disconnected():
                    signal.clear()
                    yield (
                        "event: sessions\ndata: "
                        + json.dumps(
                            [item.model_dump(mode="json") for item in await list_sessions()]
                        )
                        + "\n\n"
                    )
                    try:
                        await asyncio.wait_for(signal.wait(), timeout=15)
                    except TimeoutError:
                        pass

        return StreamingResponse(
            updates(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform"},
        )

    @app.post(
        "/sessions/{session_id}/messages", status_code=202, response_model=AcceptedConversationTurn
    )
    async def message(session_id: UUID, body: MessageInput | TokenizedMessageInput):
        session = await writable_session(session_id)
        if settings.display_mode:
            if not isinstance(body, MessageInput):
                raise HTTPException(422, "The display edge expects a user message")
            text = (
                await app.state.store.privacy.tokenize(
                    session_id,
                    Raw(value=body.text),
                    path="user_message",
                    external=True,
                )
            ).value
            turn_id = uuid4()
            caller_context = app.state.signer.mint(
                session_id=session_id,
                turn_id=turn_id,
                site=session.site_id,
                persona=session.persona,
            )
        else:
            if not isinstance(body, TokenizedMessageInput):
                raise HTTPException(422, "The runtime accepts only tokenized messages")
            text = body.text.value
            turn_id, caller_context = body.conversation_turn_id, body.caller_context
            checked = await app.state.store.privacy.tokenize(
                session_id,
                Raw(value=text),
                path="user_message",
            )
            if checked.value != text:
                raise HTTPException(422, "Untokenized identifier at the runtime boundary")
        if settings.runtime_url:
            return await forward_turn(
                session_id,
                "messages",
                {
                    "text": Tokenized(value=text).model_dump(),
                    "conversation_turn_id": str(turn_id),
                    "caller_context": caller_context,
                },
            )
        turn = await app.state.store.begin_conversation_turn(
            session_id, text, conversation_turn_id=turn_id, caller_context=caller_context
        )
        app.state.runtime.start(turn)
        return AcceptedConversationTurn(
            session_id=turn.id, conversation_turn_id=turn.conversation_turn_id
        )

    @app.post(
        "/sessions/{session_id}/retry", status_code=202, response_model=AcceptedConversationTurn
    )
    async def retry(session_id: UUID, body: RetryInput):
        session = await writable_session(session_id)
        turn_id, caller_context = body.conversation_turn_id, body.caller_context
        if settings.display_mode:
            if turn_id or caller_context:
                raise HTTPException(422, "The display edge expects only the turn to retry")
            turn_id = uuid4()
            caller_context = app.state.signer.mint(
                session_id=session_id,
                turn_id=turn_id,
                site=session.site_id,
                persona=session.persona,
            )
        if settings.runtime_url:
            return await forward_turn(
                session_id,
                "retry",
                {
                    "retry_of": str(body.retry_of),
                    "conversation_turn_id": str(turn_id),
                    "caller_context": caller_context,
                },
            )
        turn = await app.state.store.retry_conversation_turn(
            session_id, body.retry_of, conversation_turn_id=turn_id, caller_context=caller_context
        )
        app.state.runtime.start(turn)
        return AcceptedConversationTurn(
            session_id=turn.id, conversation_turn_id=turn.conversation_turn_id
        )

    async def forward_turn(session_id: UUID, path: str, body: dict) -> AcceptedConversationTurn:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.runtime_url}/sessions/{session_id}/{path}", json=body
            )
        if response.is_error:
            raise HTTPException(
                response.status_code, response.json().get("detail", "Runtime unavailable")
            )
        return AcceptedConversationTurn.model_validate(response.json())

    @app.get("/sessions/{session_id}/snapshot", response_model=Projection)
    async def snapshot(session_id: UUID, representation: Literal["display", "model"] = "display"):
        await scoped_session(session_id)
        projection = await app.state.store.snapshot(session_id)
        if settings.display_mode and representation == "display":
            return await SessionDisplay(session_id, app.state.store.privacy).projection(projection)
        return projection

    @app.get("/sessions/{session_id}/handles/{handle}")
    async def resolve_handle(session_id: UUID, handle: str):
        await scoped_session(session_id)
        if not settings.display_mode:
            raise HTTPException(403, "Clinical data is available only through the display edge")
        resolved = await app.state.clinical.resolve(session_id, handle)
        return {
            "columns": resolved["columns"],
            "rows": resolved["rows"],
            "row_count": resolved["row_count"],
        }

    @app.get("/sessions/{session_id}/xray")
    async def xray(session_id: UUID):
        await scoped_session(session_id)
        if not settings.display_mode:
            raise HTTPException(403, "Identifier resolution is unavailable in the runtime")
        display = SessionDisplay(session_id, app.state.store.privacy)
        projection = await app.state.store.snapshot(session_id)
        rendered = await display.projection(projection)
        gateway = getattr(app.state.runtime.agent, "gateway", None)
        if gateway is None and hasattr(app.state.runtime.agent, "agent"):
            gateway = getattr(app.state.runtime.agent.agent, "gateway", None)
        if gateway is not None and hasattr(gateway, "requests_for_session"):
            requests = await asyncio.to_thread(gateway.requests_for_session, str(session_id))
        elif not settings.runtime_url and gateway is None:
            requests = []
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{settings.gateway_url}/sessions/{session_id}/model-requests"
                )
                response.raise_for_status()
                requests = response.json()
        executions = await app.state.store.pool.fetch(
            """SELECT conversation_turn_id, tool, arguments FROM privacy.execution_audit
               WHERE session_id = $1 ORDER BY id""",
            session_id,
        )
        return {
            "display": rendered.model_dump(mode="json"),
            "model": projection.model_dump(mode="json"),
            "requests": requests,
            "bindings": [binding.model_dump() for binding in display.vault.bindings],
            "executions": [dict(row) for row in executions],
        }

    @app.get("/sessions/{session_id}/bindings")
    async def display_bindings(session_id: UUID):
        await scoped_session(session_id)
        display_only()
        return [
            binding.model_dump() for binding in await app.state.store.privacy.bindings(session_id)
        ]

    @app.get("/sessions/{session_id}/events")
    async def events(
        request: Request,
        session_id: UUID,
        from_seq: Annotated[int, Query(alias="from", ge=0)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
        follow: bool = False,
        representation: Literal["display", "model"] = "display",
    ):
        await scoped_session(session_id)
        try:
            header_cursor = int(last_event_id) if last_event_id is not None else 0
            if header_cursor < 0:
                raise ValueError
        except ValueError as error:
            raise HTTPException(422, "Last-Event-ID must be a nonnegative integer") from error
        cursor = max(from_seq, header_cursor)
        from zagent.faults import enabled

        if enabled("resume_off"):
            cursor = from_seq
        head, _ = await app.state.store.head(session_id)
        if cursor > head:
            raise HTTPException(409, "Cursor is ahead of this session's event log")
        display = None
        if settings.display_mode and representation == "display":
            display = SessionDisplay(session_id, app.state.store.privacy)
            await display.refresh()
            if cursor:
                for previous in await app.state.store.snapshot_events(session_id):
                    if previous.seq > cursor:
                        break
                    await display.event(previous)
        return StreamingResponse(
            tail_events(
                request,
                app.state.store,
                app.state.notifications,
                session_id,
                cursor,
                follow=follow,
                poll_seconds=settings.poll_seconds,
                display=display,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
