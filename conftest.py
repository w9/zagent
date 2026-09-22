import asyncio
import os
import socket
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from zagent.agent import ScriptedAgent
from zagent.app import Settings, create_app
from zagent.store import Store


@pytest.fixture(scope="session")
def database_url():
    return os.environ.get(
        "ZAGENT_TEST_DATABASE_URL", "postgresql://zagent:zagent@localhost:5432/zagent_test"
    )


@pytest.fixture
async def store(database_url):
    instance = await Store.open(database_url)
    await instance.migrate(seed=False)
    try:
        yield instance
    finally:
        await instance.close()


@pytest.fixture(scope="session")
async def api(database_url):
    application = create_app(
        Settings(database_url=database_url, coalesce_seconds=0.015, poll_seconds=0.05),
        ScriptedAgent(delay_scale=0.12),
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
                    raise RuntimeError("Test server did not start")
                await asyncio.sleep(0.005)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            yield SimpleNamespace(client=client, app=application)
    finally:
        server.should_exit = True
        await task
        listener.close()


async def read_events(client, session_id, *, after=0, stop_after=None, headers=None):
    from zagent.events import Event

    events = []
    async with client.stream(
        "GET", f"/sessions/{session_id}/events", params={"from": after}, headers=headers
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                import json

                data = json.loads(line[6:])
                if "type" not in data:
                    continue
                events.append(Event.model_validate(data))
                if stop_after is not None and len(events) >= stop_after:
                    break
    return events
