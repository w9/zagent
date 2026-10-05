import ast
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from zknowledge.server import SNAPSHOT_META, create_server
from zknowledge.snapshot import SnapshotStore, build_snapshot, corpus_root

PACKAGE = Path(__file__).parents[1]


@pytest.fixture
def published(tmp_path):
    return SnapshotStore(tmp_path), build_snapshot(corpus_root() / "legacy", tmp_path)


async def call(server, name, arguments, meta=None):
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(name, arguments, meta=meta)
    assert not result.isError
    return result.structuredContent


async def test_tools_serve_the_current_or_requested_snapshot(published, tmp_path):
    store, version = published
    server = create_server(store)
    found = await call(server, "search_knowledge", {"query": "genotype concordance"})
    assert found["version"] == version and found["matches"]
    match = found["matches"][0]
    excerpt = await call(
        server,
        "read_document",
        {**{key: match[key] for key in ("document", "start_line", "end_line")}, "version": version},
    )
    assert excerpt["text"] == match["text"]
    changed = tmp_path / "changed"
    changed.mkdir()
    (changed / "read-quality.md").write_text("Coverage below 40x fails.\n")
    newer = build_snapshot(changed, store.directory)
    assert (await call(server, "search_knowledge", {"query": "coverage"}))["version"] == newer
    pinned = await call(server, "search_knowledge", {"query": "coverage"}, {SNAPSHOT_META: version})
    assert pinned["version"] == version


async def test_tool_errors_are_structured(published):
    store, version = published
    server = create_server(store)
    missing = await call(
        server, "search_knowledge", {"query": "coverage"}, {SNAPSHOT_META: "b" * 64}
    )
    assert missing["error"]["code"] == "unavailable"
    mismatch = await call(
        server,
        "read_document",
        {"document": "read-quality", "start_line": 1, "end_line": 2, "version": "c" * 64},
    )
    assert mismatch == {
        "error": {
            "code": "invalid_arguments",
            "message": "Knowledge version mismatch; search the current index again",
        }
    }


async def test_published_contract_matches_the_served_tools(published):
    store, _version = published
    async with create_connected_server_and_client_session(create_server(store)) as client:
        tools = (await client.list_tools()).tools
    served = [
        {"name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema}
        for tool in sorted(tools, key=lambda tool: tool.name)
    ]
    assert served == json.loads((PACKAGE / "contract.json").read_text())
    assert all(
        tool.annotations.readOnlyHint and not tool.annotations.openWorldHint for tool in tools
    )


def test_the_knowledge_package_does_not_import_the_agent():
    imported = set()
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert "zagent" not in imported
