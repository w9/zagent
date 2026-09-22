import asyncio
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import uvicorn
from fastapi import FastAPI

from zagent.agent import Agent, Emit
from zagent.app import Settings, create_app
from zagent.events import EventDraft
from zagent.store import AgentSession


@dataclass
class APIEnvironment:
    client: httpx.AsyncClient
    app: FastAPI


class PausedAgent:
    def __init__(self, agent: Agent, *, emit_index: int, seconds: float):
        self.agent = agent
        self.emit_index = emit_index
        self.seconds = seconds

    async def run_turn(self, session: AgentSession, emit: Emit) -> None:
        emitted = 0

        async def paused_emit(event: EventDraft) -> None:
            nonlocal emitted
            emitted += 1
            if emitted == self.emit_index:
                await asyncio.sleep(self.seconds)
            await emit(event)

        await self.agent.run_turn(session, paused_emit)


@asynccontextmanager
async def local_api(
    database_url: str,
    agent: Agent,
    *,
    coalesce_seconds: float = 0.015,
    poll_seconds: float = 0.05,
):
    application = create_app(
        Settings(
            database_url=database_url, coalesce_seconds=coalesce_seconds, poll_seconds=poll_seconds
        ),
        agent,
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            log_level="error",
            timeout_graceful_shutdown=2,
        )
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Evaluation HTTP server did not start")
                await asyncio.sleep(0.005)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=90) as client:
            yield APIEnvironment(client, application)
    finally:
        server.should_exit = True
        await task
        listener.close()
