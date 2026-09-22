import asyncio
import json
import random
from pathlib import Path
from uuid import UUID

import pytest
from zagent.events import normalize_transcript, project

from conftest import read_events

pytestmark = pytest.mark.integration


async def start_conversation_turn(api):
    response = await api.client.post("/sessions")
    response.raise_for_status()
    session_id = response.json()["id"]
    response = await api.client.post(f"/sessions/{session_id}/messages", json={"text": "Hello"})
    assert response.status_code == 202
    return session_id


@pytest.fixture(scope="session")
async def uninterrupted(api):
    session_id = await start_conversation_turn(api)
    return await read_events(api.client, session_id)


async def test_req_stream_01_golden_transcript(api, uninterrupted):
    expected = json.loads(Path(__file__).with_name("goldens").joinpath("scripted.json").read_text())
    persisted = await api.app.state.store.snapshot_events(uninterrupted[0].session_id)
    assert normalize_transcript(persisted) == expected
    assert normalize_transcript(uninterrupted) == expected


@pytest.mark.chaos
@pytest.mark.parametrize("seed", range(50), ids=lambda seed: f"seed-{seed:02d}")
async def test_req_stream_02_chaos_resume(api, uninterrupted, seed):
    randomizer = random.Random(seed)
    drop_after = randomizer.randint(3, 10)
    session_id = await start_conversation_turn(api)
    prefix = await read_events(api.client, session_id, stop_after=drop_after)
    assert prefix[-1].type == "text_delta", f"seed={seed}, drop_after={drop_after}"
    assert (
        await api.app.state.store.snapshot(UUID(session_id))
    ).conversation_turn.status == "running"
    await asyncio.sleep(randomizer.uniform(0.001, 0.08))
    suffix = await read_events(
        api.client, session_id, headers={"Last-Event-ID": str(prefix[-1].seq)}
    )
    reassembled = prefix + suffix
    assert [event.seq for event in reassembled] == list(range(1, reassembled[-1].seq + 1))
    assert reassembled[-1].type == "conversation_turn_finished"
    assert normalize_transcript(reassembled) == normalize_transcript(uninterrupted), (
        f"seed={seed}, drop_after={drop_after}"
    )
    client_state = project(UUID(session_id), reassembled)
    persisted_state = await api.app.state.store.snapshot(UUID(session_id))
    assert client_state == persisted_state
    expected_messages = project(uninterrupted[0].session_id, uninterrupted).messages
    assert [(message.role, message.text, message.status) for message in client_state.messages] == [
        (message.role, message.text, message.status) for message in expected_messages
    ]
