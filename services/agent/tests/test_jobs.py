import asyncio
import os
from uuid import uuid4

import pytest
from zagent.cohort import FROZEN_NOW, generate_cohort
from zagent.drafts import default_parameters
from zagent.job_worker import execution_records


def worker_input(patient=0, app="somatic-snv", simulation="standard", verified=False):
    cohort = generate_cohort(FROZEN_NOW)
    owner = cohort["patients"][patient]
    specimens = [
        dict(item, mrn=owner["mrn"], simulation=simulation)
        for item in cohort["specimens"]
        if item["patient_id"] == owner["id"]
    ]
    if verified:
        for specimen in specimens:
            specimen["kind"] = specimen["assayed_kind"]
    return {
        "execution_id": "test-execution",
        "job_id": "job-0001",
        "app_id": app,
        "parameters": default_parameters(app),
        "specimens": specimens,
        "libraries": [
            item
            for item in cohort["libraries"]
            if item["specimen_id"] in {specimen["id"] for specimen in specimens}
        ],
    }


def test_somatic_failure_is_caused_by_identity_not_randomness():
    failed = list(execution_records(worker_input()))
    assert failed[-1].attributes["job.code"] == "genotype_concordance_failed"
    assert failed[-1].attributes["job.state"] == "failed"
    corrected = list(execution_records(worker_input(verified=True)))
    assert corrected[-1].attributes["job.state"] == "completed"


def test_coverage_and_purity_outcomes_come_from_fixture_values():
    coverage = list(execution_records(worker_input(patient=2, app="readqc")))
    assert coverage[-1].attributes["job.code"] == "low_coverage"
    purity = list(execution_records(worker_input(patient=1)))
    assert any(item.attributes["job.code"] == "low_purity_warning" for item in purity)
    assert purity[-1].attributes["job.state"] == "completed"


def test_eviction_retries_once_and_long_jobs_have_more_progress():
    snapshot = worker_input(patient=4, simulation="node_eviction")
    assert list(execution_records(snapshot))[-1].attributes["job.state"] == "retrying"
    assert list(execution_records(snapshot, attempt=2))[-1].attributes["job.state"] == "completed"
    long = list(execution_records(worker_input(patient=5, simulation="long_running")))
    assert len(long) > 20
    assert [item.sequence for item in long] == list(range(1, len(long) + 1))


@pytest.mark.integration
async def test_lease_takeover_deduplicates_logs_and_fences_stale_dispatcher(store):
    from test_drafts import fixture_draft
    from zagent.jobs import JobStore, LeaseLost
    from zagent.privacy import Detector

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs = JobStore(drafts.clinical)
    claims = await asyncio.gather(
        *(jobs.claim(uuid4(), session_id=session.id) for _index in range(2))
    )
    first = next(lease for lease in claims if lease)
    assert sum(lease is not None for lease in claims) == 1
    records = list(execution_records(first.snapshot))
    await jobs.ingest(first, records[0])
    await store.pool.execute(
        "UPDATE job_queue SET lease_until=clock_timestamp()-interval '1 second' "
        "WHERE session_id=$1",
        session.id,
    )
    second = await jobs.claim(uuid4(), session_id=session.id)
    assert second.execution_name == first.execution_name
    with pytest.raises(LeaseLost):
        await jobs.ingest(first, records[1])
    for record in records:
        await jobs.ingest(second, record)
    await jobs.finish(second, 0)
    snapshot = await jobs.read(session.id, job.job_id)
    assert snapshot["status"] == "completed"
    assert len(snapshot["attempts"]) == 1
    assert len(snapshot["logs"]) == len(records)
    assert not Detector().contains(snapshot["logs"])
    assert await jobs.claim(uuid4(), session_id=session.id) is None
    assert (await store.snapshot(session.id)).jobs[job.job_id].status == "pending"


@pytest.mark.integration
async def test_dispatcher_reconnects_to_execution_after_create_crash(store, tmp_path):
    from test_drafts import fixture_draft
    from zagent.dispatcher import Dispatcher
    from zagent.executors import ProcessExecutor
    from zagent.jobs import JobStore

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs, executor = JobStore(drafts.clinical), ProcessExecutor(tmp_path)
    lease = await jobs.claim(uuid4(), session_id=session.id)
    await executor.ensure(lease)
    await store.pool.execute(
        "UPDATE job_queue SET lease_until=clock_timestamp()-interval '1 second' "
        "WHERE session_id=$1",
        session.id,
    )
    try:
        assert await Dispatcher(jobs, executor, interval=0.01).once(session.id)
        assert len(executor.processes) == 1
        result = await jobs.read(session.id, job.job_id)
        assert result["status"] == "completed"
        assert result["progress"] == 1
        assert result["finished_at"]
        assert not await Dispatcher(jobs, executor).once(session.id)
    finally:
        executor.close()


@pytest.mark.integration
async def test_live_job_handles_keep_identity_and_session_scope(store):
    from test_drafts import fixture_draft
    from zagent.jobs import JobStore
    from zagent.store import NotFound

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs = JobStore(drafts.clinical)
    before = await store.snapshot(session.id)
    handle = before.artifacts[-1].spec.props["handle"]
    assert (await jobs.read_handle(session.id, handle))["jobs"][0]["status"] == "pending"
    lease = await jobs.claim(uuid4(), session_id=session.id)
    await jobs.ingest(lease, next(execution_records(lease.snapshot)))
    current = await jobs.read_handle(session.id, handle)
    assert current["jobs"][0]["job_id"] == job.job_id
    assert current["jobs"][0]["status"] == "running"
    assert (await store.snapshot(session.id)).seq == before.seq
    other = await store.create_session()
    with pytest.raises(NotFound):
        await jobs.read_handle(other.id, handle)


@pytest.mark.integration
async def test_jobs_mcp_inspection_retrieval_and_corrected_rerun(store):
    from test_drafts import fixture_draft
    from zagent.evals.local_knowledge import local_broker
    from zagent.identity import CallerSigner
    from zagent.job_tools import JobsTools
    from zagent.jobs import JobStore
    from zagent.tools import ClinicalTools

    session, drafts, draft = await fixture_draft(store)
    first = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs = JobStore(drafts.clinical)
    lease = await jobs.claim(uuid4(), session_id=session.id)
    for record in execution_records(lease.snapshot):
        await jobs.ingest(lease, record)
    await jobs.finish(lease, 2)
    turn = await store.begin_conversation_turn(
        session.id, "Explain the failure and prepare a correction"
    )
    tools = JobsTools(drafts.clinical)
    result = await tools.dispatch(
        session.id, turn.conversation_turn_id, "get_job", {"job_id": first.job_id}
    )
    assert result["status"] == "failed"
    assert result["logs"][-1]["code"] == "genotype_concordance_failed"
    knowledge = local_broker(store.privacy)
    context = CallerSigner.configured().mint(
        session_id=session.id,
        turn_id=turn.conversation_turn_id,
        site="northgate",
        persona="analyst",
    )
    found = await knowledge.dispatch(
        session.id,
        turn.conversation_turn_id,
        "search_knowledge",
        {"query": "genotype concordance failure verified identity", "doc_types": ["sop"]},
        context,
    )
    assert found["matches"][0]["document"] == "sop-identity-001-v1"
    excerpt = await knowledge.dispatch(
        session.id,
        turn.conversation_turn_id,
        "read_document",
        {"document": "sop-identity-001-v1", "start_line": 12, "end_line": 23},
        context,
    )
    assert 'identity="verified"' in excerpt["text"]
    clinical = ClinicalTools(drafts.clinical)
    patient = await clinical.dispatch(session.id, "find_patients", {"mrn": "NGC-0041872"})
    selection = await clinical.dispatch(
        session.id,
        "find_specimens",
        {
            "patient_handle": patient["handle"],
            "identity": "verified",
            "received_within": "P7D",
        },
    )
    corrected = await drafts.update(
        session.id,
        app_id="somatic-snv",
        specimen_handle=selection["handle"],
        conversation_turn_id=turn.conversation_turn_id,
    )
    assert not corrected.validation
    assert len((await store.snapshot(session.id)).jobs) == 1
    second = await drafts.confirm(session.id, corrected.draft_id, corrected.content_hash)
    lease = await jobs.claim(uuid4(), session_id=session.id)
    records = list(execution_records(lease.snapshot))
    assert records[-1].attributes["job.state"] == "completed"
    assert second.job_id != first.job_id
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
async def test_mcp_app_resources_and_public_reads_are_bound_to_published_artifact(
    database_url,
):
    import httpx
    from test_drafts import fixture_draft
    from zagent.agent import ScriptedAgent
    from zagent.app import Settings, create_app

    app = create_app(Settings(database_url=database_url), ScriptedAgent(delay_scale=0))
    async with app.router.lifespan_context(app):
        session, drafts, draft = await fixture_draft(app.state.store, app_id="readqc")
        job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
        snapshot = await app.state.store.snapshot(session.id)
        artifact = snapshot.artifacts[-1]
        assert job.artifact_id == artifact.id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://bff"
        ) as client:
            path = f"/sessions/{session.id}/artifacts/{artifact.id}"
            assert (
                await client.get(f"/sessions/{session.id}/views/{artifact.id}/app")
            ).status_code == 404
            resource = await client.get(path + "/app")
            assert resource.status_code == 200
            assert resource.json()["resource_uri"] == "ui://jobs/card"
            assert "Execution log" in resource.json()["html"]
            data = await client.get(path + "/data")
            assert data.status_code == 200
            assert data.json()["jobs"][0]["job_id"] == job.job_id
            other = await app.state.store.create_session()
            assert (
                await client.get(f"/sessions/{other.id}/artifacts/{artifact.id}/app")
            ).status_code == 404
            assert (await app.state.store.snapshot(session.id)).seq == snapshot.seq
        async with app.state.jobs_client.connection() as mcp:
            resources = await mcp.list_resources()
            assert {str(item.uri) for item in resources.resources} == {
                "ui://jobs/card",
                "ui://jobs/grid",
            }
            tools = await mcp.list_tools()
            read = next(item for item in tools.tools if item.name == "read_jobs")
            assert read.meta["ui"]["visibility"] == ["app"]
            assert not any("submit" in item.name or "confirm" in item.name for item in tools.tools)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("ZAGENT_DOCKER_TESTS") != "1", reason="Opt-in real Docker execution"
)
async def test_docker_monitor_restart_reattaches_to_one_execution(store):
    from test_drafts import fixture_draft
    from zagent.dispatcher import Dispatcher
    from zagent.executors import DockerExecutor
    from zagent.jobs import JobStore

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs = JobStore(drafts.clinical)
    first = await jobs.claim(uuid4(), session_id=session.id)
    executor = DockerExecutor(project="zagent-plan4", step_seconds=0.1)
    try:
        await executor.ensure(first)
        original = executor.client.containers.get(first.execution_name).id
        await store.pool.execute(
            "UPDATE job_queue SET lease_until=clock_timestamp()-interval '1 second' "
            "WHERE session_id=$1",
            session.id,
        )
        replacement = DockerExecutor(project="zagent-plan4", step_seconds=0.1)
        try:
            assert await Dispatcher(jobs, replacement, interval=0.02).once(session.id)
            assert replacement.client.containers.get(first.execution_name).id == original
            state = await jobs.read(session.id, job.job_id)
            assert state["status"] == "completed"
            assert len(state["attempts"]) == 1
        finally:
            replacement.close()
    finally:
        executor.client.containers.get(first.execution_name).remove(force=True)
        executor.close()


@pytest.mark.integration
async def test_evicted_execution_has_one_visible_retry(store, tmp_path):
    from test_drafts import fixture_draft
    from zagent.dispatcher import Dispatcher
    from zagent.executors import ProcessExecutor
    from zagent.jobs import JobStore

    session, drafts, draft = await fixture_draft(store, mrn="NGC-0041876", app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs, executor = JobStore(drafts.clinical), ProcessExecutor(tmp_path)
    dispatcher = Dispatcher(jobs, executor, interval=0.01)
    try:
        await dispatcher.once(session.id)
        assert (await jobs.read(session.id, job.job_id))["status"] == "retrying"
        await dispatcher.once(session.id)
        current = await jobs.read(session.id, job.job_id)
        assert current["status"] == "completed"
        assert [attempt["status"] for attempt in current["attempts"]] == ["evicted", "completed"]
        assert len(executor.processes) == 2
    finally:
        executor.close()


def test_worker_records_keep_originating_conversation_trace():
    snapshot = worker_input(app="readqc")
    snapshot["trace_context"] = {"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"}
    assert {record.traceId for record in execution_records(snapshot)} == {"a" * 32}


@pytest.mark.integration
async def test_confirmed_execution_preserves_originating_trace_context(store):
    from test_drafts import fixture_draft

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    context = {"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"}
    await store.pool.execute(
        "UPDATE conversation_turns SET trace_context=$2 WHERE session_id=$1", session.id, context
    )
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    snapshot = await store.pool.fetchval(
        "SELECT snapshot FROM privacy.job_inputs WHERE session_id=$1 AND job_id=$2",
        session.id,
        job.job_id,
    )
    assert snapshot["trace_context"] == context


@pytest.mark.integration
async def test_cleanup_failure_keeps_job_claim_recoverable(store, tmp_path):
    from test_drafts import fixture_draft
    from zagent.dispatcher import Dispatcher
    from zagent.executors import ProcessExecutor
    from zagent.jobs import JobStore

    class InterruptedCleanup(ProcessExecutor):
        async def finalize(self, claimed):
            raise RuntimeError("Cleanup scheduling interrupted")

    class Recovering(ProcessExecutor):
        ensured = 0

        async def ensure(self, claimed):
            self.ensured += 1

        async def finalize(self, claimed):
            pass

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    executor = InterruptedCleanup(tmp_path)
    recovered = Recovering(tmp_path / "recovered")
    jobs = JobStore(drafts.clinical)
    try:
        with pytest.raises(RuntimeError, match="Cleanup scheduling interrupted"):
            await Dispatcher(jobs, executor, interval=0.01).once(session.id)
        assert await store.pool.fetchval(
            "SELECT completed_at IS NULL FROM job_queue WHERE session_id=$1", session.id
        )
        assert (
            await store.pool.fetchval(
                "SELECT terminal_exit_code FROM job_queue WHERE session_id=$1", session.id
            )
            == 0
        )
        await store.pool.execute(
            "UPDATE job_queue SET lease_until=clock_timestamp()-interval '1 second' "
            "WHERE session_id=$1",
            session.id,
        )
        assert await Dispatcher(jobs, recovered).once(session.id)
        assert recovered.ensured == 0
        result = await jobs.read(session.id, job.job_id)
        assert result["status"] == "completed"
        assert len(result["attempts"]) == 1
        assert await jobs.claim(uuid4(), session_id=session.id) is None
    finally:
        executor.close()
        recovered.close()
