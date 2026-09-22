import os

import pytest
from zagent.agent import ScriptedAgent
from zagent.evals.environment import local_api
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
    async with local_api(database_url, ScriptedAgent(delay_scale=0.12)) as environment:
        yield environment


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
