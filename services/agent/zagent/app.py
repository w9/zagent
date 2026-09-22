import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from zagent.agent import Agent, LlmAgent, ScriptedAgent
from zagent.cohort import ClinicalStore, HandleError, configured_clock
from zagent.display import SessionDisplay
from zagent.events import Projection
from zagent.llm import GatewayClient
from zagent.privacy import PrivacyError, Raw, Tokenized
from zagent.runtime import Runtime
from zagent.store import DEFAULT_DATABASE_URL, ConversationTurnConflict, NotFound, Session, Store
from zagent.stream import Notifications, tail_events
from zagent.tools import McpToolClient, ToolsGateway


class Settings(BaseModel):
    database_url: str = Field(
        default_factory=lambda: os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    coalesce_seconds: float = Field(default=0.18, gt=0)
    poll_seconds: float = Field(default=2, gt=0)
    agent_mode: Literal["llm", "scripted"] = Field(
        default_factory=lambda: os.environ.get("ZAGENT_AGENT", "llm")
    )
    gateway_url: str = Field(
        default_factory=lambda: os.environ.get("ZAGENT_GATEWAY_URL", "http://127.0.0.1:8001")
    )
    tools_url: str = Field(
        default_factory=lambda: os.environ.get("ZAGENT_TOOLS_URL", "http://127.0.0.1:8002/mcp")
    )
    site_id: str = "northgate"
    display_mode: bool = Field(
        default_factory=lambda: os.environ.get("ZAGENT_DISPLAY_MODE", "1") == "1"
    )
    runtime_url: str | None = Field(default_factory=lambda: os.environ.get("ZAGENT_RUNTIME_URL"))
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


def create_app(settings: Settings | None = None, agent: Agent | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as resources:
            store = await Store.open(settings.database_url)
            resources.push_async_callback(store.close)
            if settings.migrate_database:
                await store.migrate()
            if not settings.runtime_url:
                await store.fail_interrupted_conversation_turns()
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
                        ToolsGateway(store, McpToolClient(url=settings.tools_url)),
                    )
                )
            runtime = Runtime(
                store,
                selected_agent,
                settings.coalesce_seconds,
            )
            resources.push_async_callback(runtime.close)
            app.state.store = store
            app.state.runtime = runtime
            app.state.notifications = notifications
            app.state.clinical = ClinicalStore(store, configured_clock())
            yield

    app = FastAPI(title="Zagent", version="0.1.0", lifespan=lifespan)

    async def scoped_session(session_id: UUID) -> Session:
        session = await app.state.store.get_session(session_id)
        if session.site_id != settings.site_id:
            raise NotFound("Session not found")
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

    @app.get("/health")
    async def health():
        await app.state.store.pool.fetchval("SELECT 1")
        return {
            "status": "ok",
            "mode": "scripted"
            if isinstance(app.state.runtime.agent, ScriptedAgent)
            else os.environ.get("ZAGENT_LLM_MODE", "replay"),
        }

    @app.post("/sessions", status_code=201, response_model=Session)
    async def create_session():
        return await app.state.store.create_session(settings.site_id)

    @app.get("/sessions", response_model=list[Session])
    async def list_sessions():
        return [
            session
            for session in await app.state.store.list_sessions()
            if session.site_id == settings.site_id
        ]

    @app.post(
        "/sessions/{session_id}/messages", status_code=202, response_model=AcceptedConversationTurn
    )
    async def message(session_id: UUID, body: MessageInput | TokenizedMessageInput):
        await scoped_session(session_id)
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
        else:
            if not isinstance(body, TokenizedMessageInput):
                raise HTTPException(422, "The runtime accepts only tokenized messages")
            text = body.text.value
            checked = await app.state.store.privacy.tokenize(
                session_id,
                Raw(value=text),
                path="user_message",
            )
            if checked.value != text:
                raise HTTPException(422, "Untokenized identifier at the runtime boundary")
        if settings.runtime_url:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.runtime_url}/sessions/{session_id}/messages",
                    json={"text": Tokenized(value=text).model_dump()},
                )
            if response.is_error:
                raise HTTPException(
                    response.status_code, response.json().get("detail", "Runtime unavailable")
                )
            return AcceptedConversationTurn.model_validate(response.json())
        session = await app.state.store.begin_conversation_turn(session_id, text)
        app.state.runtime.start(session)
        return AcceptedConversationTurn(
            session_id=session.id, conversation_turn_id=session.conversation_turn_id
        )

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
