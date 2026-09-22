import os
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from zagent.agent import Agent, LlmAgent, ScriptedAgent
from zagent.cohort import ClinicalStore, HandleError, configured_clock
from zagent.events import Projection
from zagent.llm import GatewayClient
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


def create_app(settings: Settings | None = None, agent: Agent | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as resources:
            store = await Store.open(settings.database_url)
            resources.push_async_callback(store.close)
            await store.migrate()
            await store.fail_interrupted_conversation_turns()
            notifications = await Notifications.open(settings.database_url)
            resources.push_async_callback(notifications.close)
            script = os.environ.get("ZAGENT_SCRIPT")
            selected_agent = agent
            if selected_agent is None:
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
    async def message(session_id: UUID, body: MessageInput):
        await scoped_session(session_id)
        session = await app.state.store.begin_conversation_turn(session_id, body.text)
        app.state.runtime.start(session)
        return AcceptedConversationTurn(
            session_id=session.id, conversation_turn_id=session.conversation_turn_id
        )

    @app.get("/sessions/{session_id}/snapshot", response_model=Projection)
    async def snapshot(session_id: UUID):
        await scoped_session(session_id)
        return await app.state.store.snapshot(session_id)

    @app.get("/sessions/{session_id}/handles/{handle}")
    async def resolve_handle(session_id: UUID, handle: str):
        await scoped_session(session_id)
        resolved = await app.state.clinical.resolve(session_id, handle)
        return {
            "columns": resolved["columns"],
            "rows": resolved["rows"],
            "row_count": resolved["row_count"],
        }

    @app.get("/sessions/{session_id}/events")
    async def events(
        request: Request,
        session_id: UUID,
        from_seq: Annotated[int, Query(alias="from", ge=0)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
        follow: bool = False,
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
        return StreamingResponse(
            tail_events(
                request,
                app.state.store,
                app.state.notifications,
                session_id,
                cursor,
                follow=follow,
                poll_seconds=settings.poll_seconds,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
