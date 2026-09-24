import asyncio
import json
import sqlite3
from functools import partial

import httpx
import pytest
from zagent.agent import LlmAgent, conversation_messages
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.llm import (
    AssistantMessage,
    CassetteMiss,
    Completion,
    CompletionRequest,
    GatewayError,
    LlmGateway,
    ModelRoute,
    normalized_request,
    provider_key,
    request_hash,
)
from zagent.runtime import Runtime
from zagent.tools import COLUMNS, McpToolClient, ToolsGateway, create_mcp_server


def request(text="Hello", **kwargs):
    return CompletionRequest(
        messages=[{"role": "system", "content": "Be helpful."}, {"role": "user", "content": text}],
        **kwargs,
    )


@pytest.mark.parametrize(
    ("mode", "model"),
    [
        ("live", "openai/gpt-6-luna"),
        ("replay", "deepseek/deepseek-v4.1-flash"),
        ("record", "deepseek/deepseek-v4.1-flash"),
    ],
)
def test_default_model_preserves_replay_and_explicit_overrides(tmp_path, monkeypatch, mode, model):
    from zagent.gateway import configured_gateway

    monkeypatch.delenv("ZAGENT_MODEL", raising=False)
    monkeypatch.delenv("ZAGENT_MODEL_ROUTES", raising=False)
    monkeypatch.setenv("ZAGENT_LLM_MODE", mode)
    assert configured_gateway().routes["default"].model == model
    assert LlmGateway(tmp_path, mode=mode).routes["default"].model == model
    monkeypatch.setenv("ZAGENT_MODEL", "")
    assert configured_gateway().routes["default"].model == model
    monkeypatch.setenv("ZAGENT_LLM_MODE", "live")
    assert configured_gateway(mode).routes["default"].model == model
    monkeypatch.setenv("ZAGENT_MODEL", "explicit-model")
    assert configured_gateway(mode).routes["default"].model == "explicit-model"
    monkeypatch.setenv("ZAGENT_MODEL_ROUTES", '{"default":{"model":"explicit-route"}}')
    assert configured_gateway(mode).routes["default"].model == "explicit-route"


async def test_replay_miss_is_loud_and_never_uses_network(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def unexpected_call(_request):
        pytest.fail("Replay attempted internet egress")

    gateway = LlmGateway(tmp_path, transport=httpx.MockTransport(unexpected_call))
    digest = request_hash(request(), ModelRoute())
    with pytest.raises(CassetteMiss, match=f"{digest}.*ZAGENT_LLM_MODE=record"):
        await gateway.complete(request())


async def test_record_replays_keylessly_and_does_not_store_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    calls = []

    def provider(incoming):
        calls.append(incoming)
        assert incoming.headers["authorization"] == "Bearer test-private-credential"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Hello there."}}],
                "usage": {"total_tokens": 12, "cost": 0.00001},
            },
        )

    transport = httpx.MockTransport(provider)
    recorded = await LlmGateway(tmp_path, mode="record", transport=transport).complete(request())
    monkeypatch.delenv("OPENROUTER_API_KEY")
    replayed = await LlmGateway(tmp_path, transport=transport).complete(request())
    assert recorded == replayed
    assert len(calls) == 1
    cassette = next(tmp_path.glob("*.json")).read_text()
    assert "test-private-credential" not in cassette
    assert "authorization" not in cassette.lower()
    assert json.loads(cassette)["request"]["prompt_hash"]


async def test_concurrent_recordings_are_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    gateway = LlmGateway(
        tmp_path,
        mode="record",
        transport=httpx.MockTransport(
            lambda _incoming: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "Recorded."}}],
                },
            )
        ),
    )
    completions = await asyncio.gather(*(gateway.complete(request()) for _index in range(8)))
    assert len(list(tmp_path.iterdir())) == 1
    assert await LlmGateway(tmp_path).complete(request()) == completions[0]


async def test_recorded_trials_are_independent_and_replay_separately(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    calls = []

    def provider(incoming):
        calls.append(incoming)
        assert "sample" not in json.loads(incoming.content)
        assert "metadata" not in json.loads(incoming.content)
        assert json.loads(incoming.content)["reasoning"] == {"enabled": False}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"Independent response {len(calls)}",
                        }
                    }
                ]
            },
        )

    gateway = LlmGateway(
        tmp_path / "cassettes",
        mode="record",
        transport=httpx.MockTransport(provider),
        audit_path=tmp_path / "audit.db",
    )
    requests = [
        request(
            sample=index,
            reasoning="disabled",
            metadata={
                "purpose": "scope_guard",
                "conversation_turn_id": "one-turn",
                "ignored_secret": "must-not-be-audited",
            },
        )
        for index in range(3)
    ]
    recorded = await asyncio.gather(*(gateway.complete(item) for item in requests))
    assert len(calls) == 3
    assert len(list((tmp_path / "cassettes").glob("*.json"))) == 1
    gateway.mode = "replay"
    assert await asyncio.gather(*(gateway.complete(item) for item in requests)) == recorded
    with pytest.raises(CassetteMiss, match="sample 3"):
        await gateway.complete(request(sample=3, reasoning="disabled"))
    audits = gateway.audit_for_turn("one-turn")
    assert len(audits) == 6
    assert sum(item["provider_calls"] for item in audits) == 3
    assert all(item["purpose"] == "scope_guard" for item in audits)
    assert "test-private-credential" not in json.dumps(audits)
    assert "must-not-be-audited" not in json.dumps(audits)
    assert "Independent response" not in json.dumps(audits)
    assert len(calls) == 3
    with sqlite3.connect(tmp_path / "audit.db") as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT entry FROM gateway_audit WHERE conversation_turn_id = ?",
            ("one-turn",),
        ).fetchall()
    assert "gateway_audit_turn" in str(plan)


def test_hash_normalizes_transport_metadata_but_preserves_meaning():
    first = request(" Hello\r\n", metadata={"request_id": "first", "timestamp": "yesterday"})
    second = request(metadata={"request_id": "second", "timestamp": "today"})
    assert request_hash(first, ModelRoute()) == request_hash(second, ModelRoute())
    assert request_hash(first, ModelRoute()) != request_hash(request("Goodbye"), ModelRoute())
    assert request_hash(first, ModelRoute()) != request_hash(first, ModelRoute(model="other"))
    changed = second.model_copy(deep=True)
    changed.messages[0]["content"] = "A new prompt."
    assert (
        normalized_request(first, ModelRoute())["prompt_hash"]
        != normalized_request(changed, ModelRoute())["prompt_hash"]
    )


def test_hash_normalizes_tool_call_ids_and_json_argument_whitespace_without_mutation():
    first = request()
    first.messages.extend(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "provider-random-id",
                        "type": "function",
                        "function": {"name": "find_specimens", "arguments": '{ "b": 2, "a": 1 }'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "provider-random-id", "content": "{}"},
        ]
    )
    second = first.model_copy(deep=True)
    second.messages[-2]["tool_calls"][0]["id"] = "different-id"
    second.messages[-2]["tool_calls"][0]["function"]["arguments"] = '{"a":1,"b":2}'
    second.messages[-1]["tool_call_id"] = "different-id"
    original = first.model_dump()
    assert request_hash(first, ModelRoute()) == request_hash(second, ModelRoute())
    assert first.model_dump() == original


async def test_provider_errors_do_not_echo_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    gateway = LlmGateway(
        tmp_path,
        mode="live",
        transport=httpx.MockTransport(
            lambda incoming: httpx.Response(401, text=incoming.headers["authorization"])
        ),
    )
    with pytest.raises(GatewayError, match="^Model provider returned HTTP 401$"):
        await gateway.complete(request())
    assert not list(tmp_path.iterdir())


async def test_evaluation_budget_is_persistent_and_blocks_before_provider_calls(
    tmp_path, monkeypatch
):
    from zagent.evals.budget import BudgetExceeded, ProviderBudget

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    prices = {ModelRoute().model: {"prompt": "0.0000001", "completion": "0.0000005"}}
    calls = []

    def provider(incoming):
        calls.append(incoming)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Done"}}]})

    budget = ProviderBudget(tmp_path / "budget.json", dollars=0.01, prices=prices, max_calls=1)
    gateway = LlmGateway(
        tmp_path / "cassettes",
        mode="record",
        before_provider=budget.reserve,
        transport=httpx.MockTransport(provider),
        audit_path=tmp_path / "audit.db",
    )
    await gateway.complete(request("first", metadata={"conversation_turn_id": "turn"}))
    restored = ProviderBudget(tmp_path / "budget.json", dollars=0.01, prices=prices, max_calls=1)
    gateway.before_provider = restored.reserve
    with pytest.raises(BudgetExceeded, match="budget exhausted"):
        await gateway.complete(request("second", metadata={"conversation_turn_id": "turn"}))
    assert len(calls) == 1
    assert gateway.audit_for_turn("turn")[-1]["provider_calls"] == 0
    assert len(list((tmp_path / "cassettes").glob("*.json"))) == 1
    ledger = (tmp_path / "budget.json").read_text()
    assert "test-private-credential" not in ledger and '"first"' not in ledger
    with pytest.raises(BudgetExceeded, match="approved evaluation budget"):
        await budget.reserve(request(), ModelRoute(model="unapproved"))


@pytest.mark.parametrize("reason", ["length", "content_filter"])
@pytest.mark.parametrize("mode", ["live", "record"])
async def test_interrupted_completion_keeps_safe_diagnostics_without_retry(
    tmp_path, monkeypatch, reason, mode
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    calls = []

    def provider(incoming):
        calls.append(incoming)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": reason,
                        "message": {
                            "content": "Arin Vellorin",
                            "tool_calls": [{"function": {"arguments": "{"}}],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 5000,
                    "completion_tokens": 1200,
                    "total_tokens": 6200,
                    "cost": 0.001,
                    "completion_tokens_details": {
                        "reasoning_tokens": 1100,
                        "private_text": "Arin Vellorin",
                    },
                    "private_text": "test-private-credential",
                },
            },
        )

    gateway = LlmGateway(
        tmp_path / "cassettes",
        mode=mode,
        transport=httpx.MockTransport(provider),
        audit_path=tmp_path / "audit.db",
    )
    incoming = request(metadata={"session_id": "session", "conversation_turn_id": "turn"})
    for current_mode in ["record", "replay"] if mode == "record" else ["live"]:
        gateway.mode = current_mode
        with pytest.raises(GatewayError, match=f"Model completion interrupted: {reason}"):
            await gateway.complete(incoming)
    assert len(calls) == 1
    audits = gateway.requests_for_session("session")
    assert len(audits) == (2 if mode == "record" else 1)
    for item in audits:
        assert item["audit"]["outcome"] == "failed"
        assert item["audit"]["finish_reason"] == reason
        assert item["audit"]["usage"] == {
            "prompt_tokens": 5000,
            "completion_tokens": 1200,
            "total_tokens": 6200,
            "cost": 0.001,
            "reasoning_tokens": 1100,
        }
    stored = json.dumps(audits) + "".join(
        path.read_text() for path in (tmp_path / "cassettes").glob("*.json")
    )
    assert "Arin Vellorin" not in stored
    assert "test-private-credential" not in stored


async def test_egress_hook_blocks_before_provider_access(tmp_path):
    def blocked(_request):
        raise GatewayError("Egress blocked")

    with pytest.raises(GatewayError, match="Egress blocked"):
        await LlmGateway(tmp_path, mode="live", egress_check=blocked).complete(request())


async def test_provider_failure_is_recorded_and_replayed_without_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    calls = []

    def unavailable(incoming):
        calls.append(incoming)
        raise httpx.ConnectError("private provider detail", request=incoming)

    gateway = LlmGateway(tmp_path, mode="record", transport=httpx.MockTransport(unavailable))
    for mode in ("record", "replay"):
        gateway.mode = mode
        with pytest.raises(GatewayError, match="check gateway connectivity"):
            await gateway.complete(request(sample=4))
    assert len(calls) == 1
    cassette = next(tmp_path.glob("*.json")).read_text()
    assert "private provider detail" not in cassette
    assert "test-private-credential" not in cassette
    assert "gateway_error" in cassette


async def test_default_recording_does_not_replace_independent_samples(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    gateway = LlmGateway(
        tmp_path,
        mode="record",
        transport=httpx.MockTransport(
            lambda _incoming: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Allowed",
                            }
                        }
                    ]
                },
            )
        ),
    )
    await gateway.complete(request(sample=0))
    await gateway.complete(request())
    await gateway.complete(request(sample=1))
    gateway.mode = "replay"
    for sample in (None, 0, 1):
        assert (await gateway.complete(request(sample=sample))).message.content == "Allowed"


async def test_record_missing_preserves_existing_errors_and_calls_only_for_missing_samples(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    calls = []

    def provider(incoming):
        calls.append(incoming)
        return httpx.Response(503)

    gateway = LlmGateway(tmp_path, mode="record", transport=httpx.MockTransport(provider))
    gateway.record_missing = True
    for sample in (0, 0, 1):
        with pytest.raises(GatewayError, match="HTTP 503"):
            await gateway.complete(request(sample=sample))
    assert len(calls) == 2
    gateway.mode = "replay"
    with pytest.raises(CassetteMiss):
        await gateway.complete(request(sample=2))
    assert len(calls) == 2


async def test_concurrent_record_missing_samples_do_not_race_with_atomic_writes(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    gateway = LlmGateway(
        tmp_path,
        mode="record",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Recorded sample",
                            }
                        }
                    ]
                },
            )
        ),
    )
    gateway.record_missing = True
    await asyncio.gather(*(gateway.complete(request(sample=index)) for index in range(24)))
    gateway.mode = "replay"
    results = await asyncio.gather(
        *(gateway.complete(request(sample=index)) for index in range(24))
    )
    assert all(result.message.content == "Recorded sample" for result in results)


async def test_corrupt_cassette_and_unknown_route_fail_closed(tmp_path):
    gateway = LlmGateway(tmp_path)
    with pytest.raises(GatewayError, match="Unknown model route"):
        await gateway.complete(request(route="missing"))
    digest = request_hash(request(), ModelRoute())
    (tmp_path / f"{digest}.json").write_text('{"version":1}')
    with pytest.raises(GatewayError, match="Invalid cassette"):
        await gateway.complete(request())


def tool_completion(name, arguments, call_id="call-1"):
    return Completion(
        message=AssistantMessage(
            tool_calls=[
                {
                    "id": call_id,
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ]
        )
    )


class SequenceCompleter:
    def __init__(self, completions):
        self.completions = iter(completions)
        self.requests = []

    async def complete(self, incoming):
        self.requests.append(incoming.model_copy(deep=True))
        return next(self.completions)


@pytest.mark.parametrize("mode,expected", [("live", 4096), ("record", 1200), ("replay", 1200)])
def test_live_budget_increases_without_changing_recorded_request_contracts(
    monkeypatch, mode, expected
):
    from zagent.app import Settings

    monkeypatch.setenv("ZAGENT_LLM_MODE", mode)
    monkeypatch.delenv("ZAGENT_AGENT_MAX_TOKENS", raising=False)
    assert Settings().agent_max_tokens == expected
    monkeypatch.setenv("ZAGENT_AGENT_MAX_TOKENS", "2048")
    assert Settings().agent_max_tokens == 2048
    monkeypatch.setenv("ZAGENT_AGENT_MAX_TOKENS", "4097")
    with pytest.raises(ValueError):
        Settings()


@pytest.mark.integration
@pytest.mark.parametrize("max_tokens", [1200, 4096])
async def test_agent_corrects_arguments_and_reconstructs_context_without_rows(store, max_tokens):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    tools = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    completer = SequenceCompleter(
        [
            tool_completion("scope_decision", {"decision": "allow"}),
            tool_completion("find_patients", {"site_id": "lakeside"}, "bad"),
            tool_completion("find_patients", {"mrn": "NGC-0041872"}, "patients"),
            tool_completion("find_specimens", {"patient_handle": "query-0001"}, "specimens"),
            Completion(message=AssistantMessage(content="Found 3 specimens.")),
            tool_completion("scope_decision", {"decision": "allow"}),
            tool_completion("find_libraries", {"specimen_handle": "query-0002"}, "libraries"),
            Completion(message=AssistantMessage(content="Those specimens have 3 libraries.")),
        ]
    )
    runtime = Runtime(store, LlmAgent(store, completer, tools, max_tokens=max_tokens))
    session = await store.create_session()
    first = await store.begin_conversation_turn(session.id, "Find specimens for NGC-0041872")
    await runtime._run_turn(first)
    assert (await store.snapshot(session.id)).conversation_turn.status == "finished"
    second = await store.begin_conversation_turn(session.id, "What libraries belong to those?")
    await runtime._run_turn(second)
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "finished"
    assert snapshot.steps[0].tools[0].result["error"]["code"] == "invalid_arguments"
    assert snapshot.steps[1].tools[0].name == "find_patients"
    followup_context = completer.requests[6].messages
    assert any(message.get("content") == "Found 3 specimens." for message in followup_context)
    assert any("query-0002" in message.get("content", "") for message in followup_context)
    history = conversation_messages(await store.snapshot_events(session.id))
    assert "SPC-northgate" not in json.dumps(history)
    assert all(
        '"rows"' not in message["content"] for message in history if message["role"] == "tool"
    )
    assert all(
        incoming.max_tokens
        == (256 if incoming.metadata["purpose"] == "scope_guard" else max_tokens)
        for incoming in completer.requests
    )


@pytest.mark.integration
async def test_iteration_cap_produces_clean_terminal_failure(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    tools = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    completer = SequenceCompleter(
        [tool_completion("scope_decision", {"decision": "allow"})]
        + [tool_completion("not_allowed", {}, f"call-{index}") for index in range(2)]
    )
    runtime = Runtime(store, LlmAgent(store, completer, tools, max_iterations=2))
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Keep working")
    await runtime._run_turn(turn)
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "failed"
    assert "iteration cap reached (2)" in snapshot.conversation_turn.error
    assert len(completer.requests) == 3
    assert all(step.status != "running" for step in snapshot.steps)
    assert (await store.snapshot_events(session.id))[-1].type == "conversation_turn_failed"


@pytest.mark.integration
async def test_model_receives_persisted_view_receipt_and_chat_remains_free_form(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    tools = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    explanation = (
        'See "Recent specimens" in the working surface. '
        "Which receipt window should we use next?\n\n"
        "| Window | Meaning |\n|---|---|\n| P1D | Last 24 hours |"
    )
    spec = {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Recent specimens",
            "handle": "query-0001",
            "columns": COLUMNS["specimens"],
            "row_count": 29,
        },
    }
    completer = SequenceCompleter(
        [
            tool_completion("scope_decision", {"decision": "allow"}),
            tool_completion("find_specimens", {}, "specimens"),
            tool_completion("push_view", {"spec": spec}, "view"),
            Completion(message=AssistantMessage(content=explanation)),
        ]
    )
    runtime = Runtime(store, LlmAgent(store, completer, tools))
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Show recent specimens")
    await runtime._run_turn(turn)
    events = await store.snapshot_events(session.id)
    view_event = next(event for event in events if event.type == "view_pushed")
    result_event = next(
        event
        for event in events
        if event.type == "tool_result" and event.payload["name"] == "push_view"
    )
    receipt = result_event.payload["result"]
    assert receipt == {
        "ok": True,
        "view_id": view_event.payload["view_id"],
        "kind": "table",
        "title": "Recent specimens",
    }
    assert view_event.seq < result_event.seq
    assert json.loads(completer.requests[-1].messages[-1]["content"]) == receipt
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "finished"
    assert len(snapshot.views) == 1
    assert snapshot.messages[-1].text == explanation
    audit = await store.pool.fetchval(
        "SELECT result FROM tool_audit WHERE conversation_turn_id = $1 AND tool = 'push_view'",
        turn.conversation_turn_id,
    )
    assert audit == receipt


@pytest.mark.integration
async def test_gateway_miss_is_visible_as_turn_failure(store, tmp_path):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    tools = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    runtime = Runtime(store, LlmAgent(store, LlmGateway(tmp_path), tools))
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Unrecorded question")
    await runtime._run_turn(turn)
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "failed"
    assert "Cassette miss:" in snapshot.conversation_turn.error
    assert snapshot.steps == []


def test_provider_key_file_must_be_private(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / "provider.key"
    path.write_text("test-private-credential\n")
    path.chmod(0o644)
    monkeypatch.setenv("OPENROUTER_API_KEY_FILE", str(path))
    with pytest.raises(GatewayError, match="owner-only"):
        provider_key("OPENROUTER_API_KEY")
    path.chmod(0o600)
    assert provider_key("OPENROUTER_API_KEY") == "test-private-credential"


async def test_gateway_http_replay_failure_contains_hash_not_credentials(tmp_path):
    from zagent.gateway import create_gateway_app

    gateway = LlmGateway(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_gateway_app(gateway)), base_url="http://gateway"
    ) as client:
        response = await client.post("/complete", json=request().model_dump())
        assert response.status_code == 502
        assert request_hash(request(), ModelRoute()) in response.json()["detail"]


@pytest.mark.integration
async def test_http_handle_resolution_checks_site_session_and_expiry(database_url):
    from zagent.agent import ScriptedAgent
    from zagent.evals.environment import local_api
    from zagent.tools import ClinicalTools

    async with local_api(database_url, ScriptedAgent(delay_scale=0)) as environment:
        store = environment.app.state.store
        clinical = environment.app.state.clinical
        assert (await environment.client.get("/health")).json() == {
            "status": "ok",
            "mode": "scripted",
        }
        await clinical.seed()
        session = await store.create_session()
        result = await ClinicalTools(clinical).dispatch(session.id, "find_specimens", {})
        path = f"/sessions/{session.id}/handles/{result['handle']}"
        response = await environment.client.get(path)
        assert response.status_code == 200
        assert response.json()["row_count"] == result["count"]
        assert response.json()["rows"]
        other = await store.create_session("lakeside")
        assert (await environment.client.get(f"/sessions/{other.id}/snapshot")).status_code == 404
        assert (
            await environment.client.get(f"/sessions/{other.id}/handles/{result['handle']}")
        ).status_code == 404
        await store.pool.execute(
            "UPDATE query_handles SET expires_at = $2 WHERE session_id = $1",
            session.id,
            clinical.clock(),
        )
        response = await environment.client.get(path)
        assert response.status_code == 410
        assert "expired" in response.json()["detail"]


async def test_gateway_fixed_ingress_forwards_tcp_without_protocol_changes():
    from zagent.gateway import forward_connection

    async def echo(reader, writer):
        writer.write(await reader.readexactly(4))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async with await asyncio.start_server(echo, "127.0.0.1", 0) as backend:
        target_port = backend.sockets[0].getsockname()[1]
        handler = partial(forward_connection, host="127.0.0.1", port=target_port)
        async with await asyncio.start_server(handler, "127.0.0.1", 0) as ingress:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", ingress.sockets[0].getsockname()[1]
            )
            writer.write(b"ping")
            await writer.drain()
            assert await reader.readexactly(4) == b"ping"
            writer.close()
            await writer.wait_closed()
