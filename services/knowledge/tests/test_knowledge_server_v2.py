import json
from pathlib import Path

from knowledge_fixtures import *  # noqa: F403
from mcp.shared.memory import create_connected_server_and_client_session
from zknowledge.server import SNAPSHOT_META
from zknowledge.server_v2 import CALLER_META, create_server_v2

PACKAGE = Path(__file__).parents[1]
ANALYST = {CALLER_META: {"site": "northgate", "roles": ["analyst"]}}
QA = {CALLER_META: {"site": "northgate", "roles": ["qa-officer"]}}


async def call(server, name, arguments, meta=None):
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(name, arguments, meta=meta)
    assert not result.isError, result.content
    return result.structuredContent


async def test_v2_tools_apply_caller_context_from_request_metadata(published_index):
    store, identifier, _warnings = published_index
    server = create_server_v2(store)
    found = await call(
        server,
        "search_knowledge",
        {"query": "tumor minimum coverage", "sources": ["qms"], "applies_to": "readqc"},
        ANALYST,
    )
    assert found["snapshot"] == identifier
    assert found["matches"][0]["document"] == "sop-qc-001-v3"
    assert all(match["source"] == "qms" for match in found["matches"])
    draft = {"document": "sop-qc-001-v4"}
    assert (await call(server, "get_document", draft, ANALYST))["error"]["code"] == "not_found"
    assert (await call(server, "get_document", draft, QA))["status"] == "draft"
    anonymous = await call(server, "get_document", draft)
    assert anonymous == await call(server, "get_document", {"document": "no-such-document"})
    section = await call(
        server, "read_document", {"document": "sop-qc-001-v3", "section": "2"}, ANALYST
    )
    assert "at least 40x" in section["text"]
    term = await call(server, "lookup_term", {"term": "VAF"}, ANALYST)
    assert term["term"] == "Variant allele frequency"
    rows = await call(
        server,
        "query_reference",
        {"table": "fusion_targets", "filters": {"five_prime": "EWSR1"}},
        ANALYST,
    )
    assert rows["total"] == 3
    pinned = await call(
        server, "search_knowledge", {"query": "coverage"}, {**ANALYST, SNAPSHOT_META: "f" * 64}
    )
    assert pinned["error"]["code"] == "unavailable"


async def test_v2_contract_matches_the_served_tools(published_index):
    store, _identifier, _warnings = published_index
    async with create_connected_server_and_client_session(create_server_v2(store)) as client:
        tools = (await client.list_tools()).tools
    served = [
        {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
        for tool in sorted(tools, key=lambda tool: tool.name)
    ]
    assert served == json.loads((PACKAGE / "contract-v2.json").read_text())
    assert all(
        "site" not in json.dumps(tool.inputSchema) and "roles" not in json.dumps(tool.inputSchema)
        for tool in tools
    )
