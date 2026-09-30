import asyncio
from uuid import UUID, uuid4

import pytest
from zagent.events import Projection, normalize_transcript, project
from zagent.store import NOTIFY_CHANNEL

from conftest import read_events

pytestmark = pytest.mark.integration


async def session_with_turn(api, text="Hello"):
    response = await api.client.post("/sessions")
    assert response.status_code == 201
    session_id = response.json()["id"]
    response = await api.client.post(f"/sessions/{session_id}/messages", json={"text": text})
    assert response.status_code == 202
    assert response.headers["content-type"] == "application/json"
    accepted = response.json()
    assert set(accepted) == {"session_id", "conversation_turn_id"}
    assert accepted["session_id"] == session_id
    assert UUID(accepted["conversation_turn_id"])
    return session_id


async def test_post_returns_before_completion_and_coalesces(api):
    session_id = await session_with_turn(api)
    early = (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    assert early["conversation_turn"]["status"] == "running"
    assert "run" not in early
    events = await read_events(api.client, session_id)
    assert events[0].type == "user_message"
    assert events[-1].type == "conversation_turn_finished"
    text_events = [event for event in events if event.type == "text_delta"]
    words = sum(len(event.payload["text"].split()) for event in text_events)
    assert 1 < len(text_events) < words
    snapshot = (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    assert snapshot == project(UUID(session_id), events).model_dump(mode="json")


async def test_failure_flushes_pending_text_and_finishes(api):
    session_id = await session_with_turn(api, "/fail")
    events = await read_events(api.client, session_id)
    assert events[-1].type == "conversation_turn_failed"
    state = project(UUID(session_id), events)
    assert state.conversation_turn.status == "failed"
    assert state.messages[-1].status == "failed"
    assert state.messages[-1].text.endswith("error.")
    assert "Scripted failure" in state.conversation_turn.error


async def test_two_subscribers_agree_and_completed_reconnect_terminates(api):
    session_id = await session_with_turn(api)
    first, second = await asyncio.gather(
        read_events(api.client, session_id), read_events(api.client, session_id)
    )
    assert first == second
    async with asyncio.timeout(2):
        assert (
            await read_events(api.client, session_id, headers={"Last-Event-ID": str(first[-1].seq)})
            == []
        )


async def test_snapshot_to_stream_handoff_and_header_precedence(api):
    session_id = await session_with_turn(api)
    initial = await read_events(api.client, session_id, stop_after=4)
    snapshot = Projection.model_validate(
        (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    )
    resumed = await read_events(
        api.client, session_id, after=1, headers={"Last-Event-ID": str(snapshot.seq)}
    )
    from zagent.events import reduce_event

    state = snapshot
    for event in resumed:
        assert event.seq > snapshot.seq
        state = reduce_event(state, event)
    complete = Projection.model_validate(
        (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    )
    assert state == complete
    assert complete.seq > initial[-1].seq


async def test_conversation_turn_survives_no_subscribers(api):
    session_id = await session_with_turn(api)
    prefix = await read_events(api.client, session_id, stop_after=3)
    conversation_turn_id = prefix[0].conversation_turn_id
    await asyncio.wait_for(
        asyncio.shield(api.app.state.runtime.tasks[conversation_turn_id]), timeout=5
    )
    suffix = await read_events(
        api.client, session_id, headers={"Last-Event-ID": str(prefix[-1].seq)}
    )
    all_events = await read_events(api.client, session_id)
    assert normalize_transcript(prefix + suffix) == normalize_transcript(all_events)


async def test_poll_backstop_when_notifications_are_lost(api):
    notifications = api.app.state.notifications
    await notifications.connection.remove_listener(NOTIFY_CHANNEL, notifications.on_notify)
    try:
        session_id = await session_with_turn(api)
        async with asyncio.timeout(5):
            events = await read_events(api.client, session_id)
        assert events[-1].type == "conversation_turn_finished"
    finally:
        await notifications.connection.add_listener(NOTIFY_CHANNEL, notifications.on_notify)


async def test_validation_and_conflict(api):
    session_id = await session_with_turn(api)
    conflict = await api.client.post(f"/sessions/{session_id}/messages", json={"text": "Again"})
    assert conflict.status_code == 409
    assert "active conversation turn" in conflict.json()["detail"]
    blank = await api.client.post(f"/sessions/{session_id}/messages", json={"text": "  "})
    assert blank.status_code == 422
    invalid = await api.client.get(
        f"/sessions/{session_id}/events", headers={"Last-Event-ID": "invalid"}
    )
    assert invalid.status_code == 422
    negative = await api.client.get(f"/sessions/{session_id}/events?from=-1")
    assert negative.status_code == 422
    ahead = await api.client.get(f"/sessions/{session_id}/events?from=99999")
    assert ahead.status_code == 409
    for suffix in ("snapshot", "events"):
        missing = await api.client.get(f"/sessions/{uuid4()}/{suffix}")
        assert missing.status_code == 404
    await read_events(api.client, session_id)


async def test_scripted_turn_pushes_two_valid_views_and_complete_steps(api):
    from zagent.views import ViewSpec

    session_id = await session_with_turn(api)
    events = await read_events(api.client, session_id)
    snapshot = (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    assert len(snapshot["views"]) == 2
    assert len({view["id"] for view in snapshot["views"]}) == 2
    for view in snapshot["views"]:
        assert ViewSpec.model_validate(view["spec"]).kind == "table"
    assert [step["status"] for step in snapshot["steps"]] == ["complete", "complete"]
    assert snapshot == project(UUID(session_id), events).model_dump(mode="json")


async def test_invalid_view_fails_without_changing_existing_surface(api):
    session_id = await session_with_turn(api)
    await read_events(api.client, session_id)
    before = (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    response = await api.client.post(
        f"/sessions/{session_id}/messages", json={"text": "/invalid-view"}
    )
    assert response.status_code == 202
    events = await read_events(api.client, session_id, after=before["seq"])
    assert "view_pushed" not in [event.type for event in events]
    assert events[-1].type == "conversation_turn_failed"
    assert "View schema error" in events[-1].payload["error"]
    assert response.json()["conversation_turn_id"] not in events[-1].payload["error"]
    after = (await api.client.get(f"/sessions/{session_id}/snapshot")).json()
    assert after["views"] == before["views"]
    assert after["steps"][-1]["status"] == "failed"


def test_deployment_service_name_wins_over_imported_app_factory(monkeypatch):
    import os
    import subprocess
    import sys

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "zagent-agent-runtime")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from zagent.app import app; "
            "from opentelemetry import trace; "
            "assert trace.get_tracer_provider().resource.attributes['service.name'] "
            "== 'zagent-agent-runtime'",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
