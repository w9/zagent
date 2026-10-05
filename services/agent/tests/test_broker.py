import json
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from zagent.broker import KnowledgeBroker, create_broker_server
from zagent.evals.local_knowledge import current_snapshot, local_broker
from zagent.kb_tools import KB_CONTRACT_SHA256, contract_hash
from zagent.privacy import Tokenized
from zagent.store import AgentSession
from zagent.tools import McpToolClient

ROOT = Path(__file__).parents[3]


class RecordingTokenizer:
    def __init__(self):
        self.calls = []

    async def tokenize(self, session_id, raw, *, path, schema=None, external=False):
        self.calls.append((path, external))
        return Tokenized(value=raw.value)


def agent_session():
    return AgentSession(id=uuid4(), conversation_turn_id=uuid4(), message="Find the identity SOP")


def fake_upstream(result: dict[str, Any]) -> FastMCP:
    server = FastMCP("fake-knowledge")

    @server.tool(name="search_knowledge")
    def search_knowledge(query: Annotated[str, Field(min_length=1)]) -> dict[str, Any]:
        return result

    return server


def test_the_pinned_contract_matches_the_published_knowledge_contract():
    tools = json.loads((ROOT / "services/knowledge/contract.json").read_text())
    assert contract_hash({item["name"]: item["inputSchema"] for item in tools}) == (
        KB_CONTRACT_SHA256
    )


async def test_runtime_reads_knowledge_through_the_broker_with_external_tokenization():
    tokenizer = RecordingTokenizer()
    client = McpToolClient(server=create_broker_server(local_broker(tokenizer)))
    session = agent_session()
    found = await client.call(session, "search_knowledge", {"query": "genotype concordance"})
    assert found["version"] == current_snapshot() and found["matches"]
    match = found["matches"][0]
    location = {key: match[key] for key in ("document", "start_line", "end_line")}
    excerpt = await client.call(session, "read_document", {**location, "version": found["version"]})
    assert excerpt["text"] == match["text"]
    stale = await client.call(session, "read_document", {**location, "version": "a" * 64})
    assert stale == {
        "error": {
            "code": "invalid_arguments",
            "message": "Knowledge version mismatch; search the current index again",
        }
    }
    assert tokenizer.calls == [("retrieved_document", True)] * 3


async def test_knowledge_tools_are_unavailable_without_a_broker():
    client = McpToolClient(server=FastMCP("clinical-only"))
    result = await client.call(agent_session(), "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unavailable"


async def test_a_changed_upstream_contract_disables_the_knowledge_tools():
    broker = KnowledgeBroker(
        McpToolClient(server=fake_upstream({"version": "a" * 64, "matches": []})),
        RecordingTokenizer(),
    )
    result = await broker.dispatch(uuid4(), "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unavailable"
    assert "contract" in result["error"]["message"]


async def test_invalid_upstream_results_never_pass_the_broker():
    upstream = McpToolClient(
        server=fake_upstream({"version": "a" * 64, "matches": [], "rows": [{"mrn": "x"}]})
    )
    broker = KnowledgeBroker(
        upstream,
        RecordingTokenizer(),
        contract=contract_hash(await upstream.tool_schemas()),
    )
    result = await broker.dispatch(uuid4(), "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unsafe_result"


async def test_an_unreachable_knowledge_service_fails_closed():
    broker = KnowledgeBroker(
        McpToolClient(url="http://127.0.0.1:9/mcp"), RecordingTokenizer(), timeout=2
    )
    result = await broker.dispatch(uuid4(), "search_knowledge", {"query": "coverage"})
    assert result == {
        "error": {"code": "unavailable", "message": "Knowledge service is unavailable"}
    }


@pytest.mark.integration
async def test_identifiers_in_knowledge_results_are_tokenized_by_the_broker(store, tmp_path):
    from zknowledge.snapshot import build_snapshot

    source = tmp_path / "incidents"
    source.mkdir()
    (source / "incident.md").write_text(
        "Specimen swap reported for NGC-0041872 during intake review.\n"
    )
    build_snapshot(source, tmp_path / "snapshots")
    session = await store.create_session()
    result = await local_broker(store.privacy, tmp_path / "snapshots").dispatch(
        session.id, "search_knowledge", {"query": "specimen swap"}
    )
    assert "NGC-0041872" not in json.dumps(result)
    assert "[PT_" in result["matches"][0]["text"]
