from contextlib import asynccontextmanager

import httpx
import pytest
from test_drafts import fixture_draft
from zagent.agent import ScriptedAgent
from zagent.app import ARCHIVED_REASON, Settings, create_app
from zagent.evals.environment import PausedAgent

pytestmark = pytest.mark.integration


@asynccontextmanager
async def display_edge(database_url, agent):
    app = create_app(Settings(database_url=database_url), agent)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://bff"
        ) as client:
            yield app, client


async def listed(client, **params):
    return [item["id"] for item in (await client.get("/sessions", params=params)).json()]


async def test_archived_sessions_leave_the_list_and_become_read_only(database_url):
    async with display_edge(database_url, ScriptedAgent(delay_scale=0)) as (_app, client):
        session_id = (await client.post("/sessions")).json()["id"]
        archived = await client.post(f"/sessions/{session_id}/archive")
        assert archived.status_code == 200 and archived.json()["archived_at"]
        assert session_id not in await listed(client)
        assert (await listed(client, archived="true"))[0] == session_id
        again = await client.post(f"/sessions/{session_id}/archive")
        assert again.json()["archived_at"] == archived.json()["archived_at"]
        assert (await client.get(f"/sessions/{session_id}/snapshot")).status_code == 200
        refused = await client.post(f"/sessions/{session_id}/messages", json={"text": "Hello"})
        assert refused.status_code == 409
        restored = await client.post(f"/sessions/{session_id}/unarchive")
        assert restored.status_code == 200 and restored.json()["archived_at"] is None
        assert session_id in await listed(client)
        assert session_id not in await listed(client, archived="true")


async def test_archiving_a_responding_session_needs_force_and_stops_the_turn(database_url):
    agent = PausedAgent(ScriptedAgent(delay_scale=0), emit_index=1, seconds=30)
    async with display_edge(database_url, agent) as (app, client):
        session_id = (await client.post("/sessions")).json()["id"]
        sent = await client.post(f"/sessions/{session_id}/messages", json={"text": "Hello"})
        assert sent.status_code == 202
        blocked = await client.post(f"/sessions/{session_id}/archive")
        assert blocked.status_code == 409
        assert {key: blocked.json()[key] for key in ("code", "responding", "jobs")} == {
            "code": "work_in_progress",
            "responding": True,
            "jobs": 0,
        }
        assert session_id in await listed(client)
        forced = await client.post(f"/sessions/{session_id}/archive", json={"force": True})
        assert forced.status_code == 200
        turn = (await client.get(f"/sessions/{session_id}/snapshot")).json()["conversation_turn"]
        assert turn["status"] == "failed" and turn["error"] == ARCHIVED_REASON
        assert not app.state.runtime.tasks


async def test_archiving_with_unfinished_jobs_needs_force_and_leaves_them_queued(database_url):
    async with display_edge(database_url, ScriptedAgent(delay_scale=0)) as (app, client):
        session, drafts, draft = await fixture_draft(app.state.store)
        await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
        blocked = await client.post(f"/sessions/{session.id}/archive")
        assert blocked.status_code == 409
        assert not blocked.json()["responding"] and blocked.json()["jobs"] == 1
        forced = await client.post(f"/sessions/{session.id}/archive", json={"force": True})
        assert forced.status_code == 200
        status = await app.state.store.pool.fetchval(
            "SELECT status FROM jobs WHERE session_id=$1", session.id
        )
        assert status == "pending"
        edit = await client.patch(
            f"/sessions/{session.id}/drafts/{draft.draft_id}",
            json={"content_hash": draft.content_hash, "parameters": {"min_vaf": 0.03}},
        )
        assert edit.status_code == 409
        assert edit.json()["detail"] == "This session is archived. Unarchive it to continue."


async def test_only_the_runtime_stops_turns_and_only_the_display_edge_archives(database_url):
    async with display_edge(database_url, ScriptedAgent(delay_scale=0)) as (_app, client):
        session_id = (await client.post("/sessions")).json()["id"]
        stop = await client.post(f"/sessions/{session_id}/stop", json={"reason": "No"})
        assert stop.status_code == 403
    runtime = create_app(
        Settings(database_url=database_url, display_mode=False), ScriptedAgent(delay_scale=0)
    )
    async with runtime.router.lifespan_context(runtime):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=runtime), base_url="http://runtime"
        ) as client:
            assert (await client.post(f"/sessions/{session_id}/archive")).status_code == 403
            stop = await client.post(f"/sessions/{session_id}/stop", json={"reason": "No"})
            assert stop.status_code == 204
