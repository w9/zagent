from uuid import uuid4

import pytest
from zagent.jobs import JobLease
from zagent.kubernetes_executor import execution_name, job_manifest


def lease(attempt=1):
    return JobLease(
        session_id=uuid4(),
        job_id="job-0001",
        owner=uuid4(),
        revision=1,
        attempt=attempt,
        execution_name="compose-attempt-name",
        snapshot={
            "app_id": "readqc",
            "parameters": {},
            "specimens": [],
            "libraries": [],
            "job_id": "job-0001",
        },
    )


def test_kubernetes_job_identity_and_retry_policy_do_not_duplicate_units():
    first = lease()
    retried = first.model_copy(update={"attempt": 2})
    manifest = job_manifest(first, image="zagent-cluster:plan9")
    assert execution_name(first) == execution_name(retried)
    assert len(manifest["metadata"]["name"]) <= 63
    assert manifest["spec"]["backoffLimit"] == 1
    assert manifest["spec"]["podFailurePolicy"]["rules"][0]["onExitCodes"]["values"] == [2]
    assert "ttlSecondsAfterFinished" not in manifest["spec"]


def test_kubernetes_worker_has_no_runtime_or_provider_capabilities():
    pod = job_manifest(lease(), image="zagent-cluster:plan9")["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["restartPolicy"] == "Never"
    worker = pod["containers"][0]
    assert worker["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert worker["securityContext"]["readOnlyRootFilesystem"]
    assert {entry["name"] for entry in worker["env"]} == {
        "ZAGENT_JOB_INPUT",
        "ZAGENT_JOB_STEP_SECONDS",
        "ZAGENT_JOB_POD_UID",
        "ZAGENT_JOB_DATABASE_URL",
    }


@pytest.mark.parametrize("first_output", ["", "Traceback: startup failed\nnot-json\n"])
def test_kubernetes_poll_records_eviction_without_container_status(first_output):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from test_jobs import worker_input
    from zagent.job_worker import JobRecord, execution_records
    from zagent.kubernetes_executor import KubernetesExecutor

    records = list(execution_records(worker_input(app="readqc"), attempt=2))
    first = SimpleNamespace(
        metadata=SimpleNamespace(name="first", creation_timestamp=1),
        status=SimpleNamespace(phase="Failed", container_statuses=None),
    )
    second = SimpleNamespace(
        metadata=SimpleNamespace(name="second", creation_timestamp=2),
        status=SimpleNamespace(phase="Succeeded", container_statuses=None),
    )
    batch, core = Mock(), Mock()
    batch.read_namespaced_job.return_value.status.conditions = [
        SimpleNamespace(type="Complete", status="True")
    ]
    core.list_namespaced_pod.return_value.items = [second, first]
    core.read_namespaced_pod_log.side_effect = [
        first_output,
        "".join(item.model_dump_json() + "\n" for item in records),
    ]
    lines, exit_code = KubernetesExecutor(batch=batch, core=core)._poll("job", 0)
    result = [JobRecord.model_validate_json(line) for line in lines]
    assert exit_code == 0
    assert result[0].attributes["job.code"] == "pod_terminated"
    assert result[0].attributes["job.state"] == "retrying"
    assert result[0].attributes["job.attempt"] == 1
    assert result[-1].attributes["job.state"] == "completed"
    assert all(item.attributes["job.attempt"] == 2 for item in result[1:])


async def test_kubernetes_job_create_race_reattaches_and_checks_input():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from kubernetes.client.exceptions import ApiException
    from zagent.kubernetes_executor import KubernetesExecutor

    claimed = lease()
    manifest = job_manifest(claimed, image="worker")
    existing = SimpleNamespace(
        metadata=SimpleNamespace(annotations=manifest["metadata"]["annotations"])
    )
    batch = Mock()
    batch.read_namespaced_job.side_effect = [ApiException(status=404), existing]
    batch.create_namespaced_job.side_effect = ApiException(status=409)
    executor = KubernetesExecutor(batch=batch, core=Mock())
    await executor.ensure(claimed)
    assert executor.names[claimed.execution_name] == execution_name(claimed)
    batch.read_namespaced_job.side_effect = None
    batch.read_namespaced_job.return_value = SimpleNamespace(
        metadata=SimpleNamespace(annotations={})
    )
    with pytest.raises(ValueError, match="confirmed execution input"):
        await executor.ensure(claimed)


def test_worker_records_keep_originating_conversation_trace():
    from test_jobs import worker_input
    from zagent.job_worker import execution_records

    snapshot = worker_input(app="readqc")
    snapshot["trace_context"] = {"traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01"}
    assert {record.traceId for record in execution_records(snapshot)} == {"a" * 32}


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


@pytest.mark.integration
async def test_cleanup_failure_keeps_job_claim_recoverable(store, tmp_path):
    from unittest.mock import Mock

    from kubernetes.client.exceptions import ApiException
    from test_drafts import fixture_draft
    from zagent.dispatcher import Dispatcher
    from zagent.executors import ProcessExecutor
    from zagent.jobs import JobStore
    from zagent.kubernetes_executor import KubernetesExecutor

    class InterruptedCleanup(ProcessExecutor):
        async def finalize(self, claimed):
            raise RuntimeError("Cleanup scheduling interrupted")

    session, drafts, draft = await fixture_draft(store, app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    executor = InterruptedCleanup(tmp_path)
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
        batch, core = Mock(), Mock()
        batch.patch_namespaced_job.side_effect = ApiException(status=404)
        recovered = KubernetesExecutor(batch=batch, core=core)
        assert await Dispatcher(jobs, recovered).once(session.id)
        batch.create_namespaced_job.assert_not_called()
        batch.read_namespaced_job.assert_not_called()
        core.list_namespaced_pod.assert_not_called()
        result = await jobs.read(session.id, job.job_id)
        assert result["status"] == "completed"
        assert len(result["attempts"]) == 1
        assert await jobs.claim(uuid4(), session_id=session.id) is None
    finally:
        executor.close()


@pytest.mark.parametrize("mode", ["replay", "live"])
def test_cluster_manifests_deny_direct_agent_access_and_limit_worker_egress(mode):
    import runpy
    from pathlib import Path

    manifests = runpy.run_path(str(Path(__file__).parents[3] / "deploy/cluster/manifests.py"))
    objects = manifests["resources"](mode=mode)
    policies = [item for item in objects if item["kind"] == "NetworkPolicy"]
    assert len([item for item in policies if item["metadata"]["name"] == "default-deny"]) == 3
    flows = manifests["FLOWS"]
    assert ("agent-runtime", "postgres", 5432) not in flows
    assert ("agent-runtime", "privacy", 8003) not in flows
    assert ("agent-runtime", "privacy", 8006) in flows
    assert [(target, port) for source, target, port in flows if source == "analysis-worker"] == [
        ("postgres", 5432)
    ]
    internet = [
        item["metadata"]["name"]
        for item in policies
        if any(
            entry.get("ipBlock", {}).get("cidr") == "0.0.0.0/0"
            for rule in item["spec"].get("egress", [])
            for entry in rule.get("to", [])
        )
    ]
    assert internet == ["allow-llm-gateway"]
    pods = [item["spec"]["template"]["spec"] for item in objects if item["kind"] == "Deployment"]
    assert sum(pod["automountServiceAccountToken"] for pod in pods) == 1
    gateway = next(
        container
        for pod in pods
        for container in pod["containers"]
        if container["name"] == "llm-gateway"
    )
    model = next(entry["value"] for entry in gateway["env"] if entry["name"] == "ZAGENT_MODEL")
    assert model == "openai/gpt-6-luna"
    for pod in pods:
        for container in pod["containers"]:
            command = container["command"]
            if command[0] == "uvicorn":
                assert command[command.index("--timeout-graceful-shutdown") + 1] == "2"


def test_cluster_bootstrap_artifacts_are_excluded_from_builds_and_git():
    from pathlib import Path

    root = Path(__file__).parents[3]
    assert ".cluster/" in (root / ".gitignore").read_text().splitlines()
    assert ".cluster" in (root / ".dockerignore").read_text().splitlines()
    tilt = (root / "Tiltfile").read_text()
    assert "match_in_env_vars=True" in tilt
    assert "docker_prune_settings(disable=True)" in tilt


def test_bootstrap_does_not_rotate_missing_existing_cluster_credentials(monkeypatch, tmp_path):
    import json
    from pathlib import Path
    from unittest.mock import Mock

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3] / "deploy/cluster"))
    import control

    run = Mock(return_value=json.dumps([{"name": "zagent-plan9", "serversRunning": 1}]))
    monkeypatch.setattr(control, "STATE", tmp_path)
    monkeypatch.setattr(control, "run", run)
    with pytest.raises(SystemExit, match="Existing cluster credentials are missing"):
        control.bootstrap()
    run.assert_called_once_with("k3d", "cluster", "list", "-o", "json", capture=True)
    assert not list(tmp_path.iterdir())


def test_agent_zone_scope_job_selects_only_database_free_cases():
    import fnmatch
    import runpy
    from pathlib import Path

    from zagent.evals.schema import load_suite

    root = Path(__file__).parents[3]
    checks = runpy.run_path(str(root / "deploy/cluster/run_checks.py"))
    selected = [
        case
        for case in load_suite(root / "evals").cases
        if fnmatch.fnmatchcase(case.id, checks["SCOPE_FILTER"])
    ]
    assert len(selected) == 300
    assert all(case.agent.startswith("guard:") for case in selected)


def test_deployed_workflows_include_all_ordinary_real_agent_cases():
    import runpy
    from pathlib import Path

    from zagent.evals.schema import load_suite

    root = Path(__file__).parents[3]
    workflow = runpy.run_path(str(root / "deploy/cluster/workflows.py"))
    selected = workflow["deployed_cases"](root / "evals")
    assert {case.id for case in selected} == {
        case.id
        for case in load_suite(root / "evals").cases
        if case.agent.startswith("llm:")
        and case.execution is None
        and case.simulator is None
        and case.adversarial is None
    }
    assert {"DRAFT-CONFIRM", "PRIVACY-001", "JOBS-VIEWS"} <= {case.id for case in selected}


def test_network_probe_requires_matching_positive_and_negative_results(monkeypatch):
    from zagent.cluster_probe import probe

    def refused(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr("socket.create_connection", refused)
    target = {"name": "probe", "host": "example.invalid", "port": 443, "allowed": True}
    assert not probe(target)["passed"]
    assert probe({**target, "allowed": False})["passed"]


def test_calico_policy_is_programmed_before_container_startup():
    import json
    import runpy
    from pathlib import Path

    network = runpy.run_path(str(Path(__file__).parents[3] / "deploy/cluster/network.py"))
    configured = network["configure"](
        [{"kind": "ConfigMap", "metadata": {"name": "calico-config"}, "data": {}}]
    )
    plugin = json.loads(configured[0]["data"]["cni_network_config"])["plugins"][0]
    assert plugin["policy_setup_timeout_seconds"] == 30
    assert plugin["endpoint_status_dir"] == "/var/run/calico/endpoint-status"
    assert plugin["policy"] == {"type": "k8s"}


@pytest.mark.integration
async def test_worker_admission_and_platform_retries_keep_one_job(store):
    from test_drafts import fixture_draft
    from zagent.job_worker import execution_records
    from zagent.jobs import JobStore

    session, drafts, draft = await fixture_draft(store, mrn="NGC-0041876", app_id="readqc")
    job = await drafts.confirm(session.id, draft.draft_id, draft.content_hash)
    jobs = JobStore(drafts.clinical)
    claimed = await jobs.claim(uuid4(), session_id=session.id)
    pod = uuid4()
    async with store.pool.acquire() as connection, connection.transaction():
        await connection.execute("SET LOCAL ROLE zagent_worker")
        for _repeat in range(2):
            assert (
                await connection.fetchval(
                    "SELECT register_worker_pod($1,$2,$3)",
                    claimed.snapshot["execution_id"],
                    pod,
                    claimed.snapshot["worker_token"],
                )
                == 1
            )
        assert (
            await connection.fetchval(
                "SELECT register_worker_pod($1,$2,$3)",
                claimed.snapshot["execution_id"],
                uuid4(),
                claimed.snapshot["worker_token"],
            )
            == 2
        )
    for attempt in (1, 2):
        for record in execution_records(claimed.snapshot, attempt):
            await jobs.ingest(claimed, record, platform_retries=True)
    await jobs.finish(claimed, 0, platform_retries=True)
    result = await jobs.read(session.id, job.job_id)
    assert result["status"] == "completed"
    assert result["attempt"] == 2
    assert [item["status"] for item in result["attempts"]] == ["evicted", "completed"]
    assert await jobs.claim(uuid4(), session_id=session.id) is None


async def test_tokenize_only_listener_has_no_resolution_endpoints():
    import httpx
    from zagent.privacy_server import create_privacy_app

    app = create_privacy_app(master=b"test-master", backend=object(), allow_resolution=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://tokenizer"
    ) as http:
        for path in ("/resolve", "/bindings"):
            assert (await http.post(path, json={})).status_code == 404
        assert (await http.get("/health")).status_code == 200
        routes = (await http.get("/openapi.json")).json()["paths"]
        assert {"/tokenize", "/tripwire"} <= routes.keys()
        assert "/resolve" not in routes


async def test_neutral_knowledge_service_needs_no_database():
    from zagent.kb_server import create_kb_server
    from zagent.store import AgentSession
    from zagent.tools import McpToolClient

    tools = McpToolClient(server=create_kb_server())
    session = AgentSession(
        id=uuid4(), conversation_turn_id=uuid4(), message="Find the identity SOP"
    )
    result = await tools.call(session, "search_knowledge", {"query": "genotype concordance"})
    assert result["matches"]
    match = result["matches"][0]
    excerpt = await tools.call(
        session,
        "read_document",
        {
            key: value
            for key, value in {**match, "version": result["version"]}.items()
            if key != "text"
        },
    )
    assert excerpt["text"] == match["text"]


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
