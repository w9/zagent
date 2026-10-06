import json
import shutil
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from zagent.broker import KnowledgeBroker, create_broker_server
from zagent.evals.local_knowledge import current_snapshot, local_broker
from zagent.identity import CallerSigner
from zagent.kb_tools import KB_CONTRACT_SHA256, contract_hash
from zagent.privacy import Tokenized
from zagent.store import AgentSession
from zagent.tools import McpToolClient

ROOT = Path(__file__).parents[3]
EMPTY_SEARCH = {"snapshot": "a" * 64, "expanded_terms": [], "matches": [], "counts": {}}


class RecordingTokenizer:
    def __init__(self):
        self.calls = []

    async def tokenize(self, session_id, raw, *, path, schema=None, external=False):
        self.calls.append((path, external))
        return Tokenized(value=raw.value)


def agent_session(persona="analyst", session_id=None):
    session_id, turn_id = session_id or uuid4(), uuid4()
    return AgentSession(
        id=session_id,
        conversation_turn_id=turn_id,
        message="Find the identity SOP",
        caller_context=CallerSigner.configured().mint(
            session_id=session_id, turn_id=turn_id, site="northgate", persona=persona
        ),
    )


async def dispatch(broker, name, arguments, session=None):
    session = session or agent_session()
    return await broker.dispatch(
        session.id, session.conversation_turn_id, name, arguments, session.caller_context
    )


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


def test_detector_matches_in_the_knowledge_corpus_are_only_the_planted_identifiers(tmp_path):
    from zagent.privacy import Detector
    from zknowledge.index import IndexStore, build_index
    from zknowledge.snapshot import corpus_root

    build_index(corpus_root(), tmp_path)
    index = IndexStore(tmp_path).open()
    try:
        detector = Detector()
        matched = {
            document
            for document, text in index.connection.execute("SELECT document, text FROM lines")
            if detector.matches(text)
        }
    finally:
        index.close()
    # Rule-matched text elsewhere would be tokenized inside quotes and break citations.
    assert matched == {"inc-0142", "inc-0151"}


async def test_runtime_reads_knowledge_through_the_broker_with_external_tokenization():
    tokenizer = RecordingTokenizer()
    client = McpToolClient(server=create_broker_server(local_broker(tokenizer)))
    session = agent_session()
    found = await client.call(session, "search_knowledge", {"query": "genotype concordance"})
    assert found["snapshot"] == current_snapshot() and found["matches"]
    match = found["matches"][0]
    location = {key: match[key] for key in ("document", "start_line", "end_line")}
    excerpt = await client.call(session, "read_document", location)
    assert excerpt["version"] == match["version"]
    assert match["snippet"].splitlines()[0] in excerpt["text"]
    outline = await client.call(session, "get_document", {"document": match["document"]})
    assert outline["line_count"] >= excerpt["end_line"]
    term = await client.call(session, "lookup_term", {"term": "VAF"})
    assert term["term"] == "Variant allele frequency"
    rows = await client.call(
        session, "query_reference", {"table": "gene_panels", "filters": {"gene": "TP53"}}
    )
    assert rows["rows"] and all(row["gene"] == "TP53" for row in rows["rows"])
    missing = await client.call(session, "get_document", {"document": "sop-qc-001-v4"})
    assert missing["error"]["code"] == "not_found"
    assert tokenizer.calls == [("retrieved_document", True)] * 6


async def test_the_turn_pin_selects_the_snapshot_and_never_comes_from_model_input(tmp_path):
    from zknowledge.index import build_index
    from zknowledge.snapshot import corpus_root

    pinned, _ = build_index(corpus_root(), tmp_path / "snapshots")
    shutil.copytree(corpus_root(), tmp_path / "corpus")
    page = tmp_path / "corpus/wiki/pages/40218.xhtml"
    page.write_text(page.read_text() + "\n<p>Republished for review.</p>\n")
    newer, _ = build_index(tmp_path / "corpus", tmp_path / "snapshots")
    broker = local_broker(RecordingTokenizer(), tmp_path / "snapshots")
    session = agent_session()
    query = {"query": "tumor coverage minimum"}

    async def search(snapshot=None):
        return await broker.dispatch(
            session.id,
            session.conversation_turn_id,
            "search_knowledge",
            query,
            session.caller_context,
            snapshot,
        )

    assert (await search())["snapshot"] == newer
    assert (await search(pinned))["snapshot"] == pinned
    assert (await search("not-a-snapshot"))["snapshot"] == newer
    unknown = await search("f" * 64)
    assert unknown["error"]["code"] == "unavailable"
    smuggled = await dispatch(broker, "search_knowledge", {**query, "snapshot": pinned})
    assert smuggled["error"]["code"] == "invalid_arguments"


async def test_knowledge_tools_are_unavailable_without_a_broker():
    client = McpToolClient(server=FastMCP("clinical-only"))
    result = await client.call(agent_session(), "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unavailable"


async def test_a_changed_upstream_contract_disables_the_knowledge_tools():
    broker = KnowledgeBroker(
        McpToolClient(server=fake_upstream(EMPTY_SEARCH)),
        RecordingTokenizer(),
    )
    result = await dispatch(broker, "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unavailable"
    assert "contract" in result["error"]["message"]


async def test_invalid_upstream_results_never_pass_the_broker():
    upstream = McpToolClient(server=fake_upstream({**EMPTY_SEARCH, "rows": [{"mrn": "x"}]}))
    broker = KnowledgeBroker(
        upstream,
        RecordingTokenizer(),
        contract=contract_hash(await upstream.tool_schemas()),
    )
    result = await dispatch(broker, "search_knowledge", {"query": "coverage"})
    assert result["error"]["code"] == "unsafe_result"


async def test_an_unreachable_knowledge_service_fails_closed():
    broker = KnowledgeBroker(
        McpToolClient(url="http://127.0.0.1:9/mcp"), RecordingTokenizer(), timeout=2
    )
    result = await dispatch(broker, "search_knowledge", {"query": "coverage"})
    assert result == {
        "error": {"code": "unavailable", "message": "Knowledge service is unavailable"}
    }


@pytest.mark.integration
async def test_identifiers_in_knowledge_results_are_tokenized_by_the_broker(store):
    session = await store.create_session()
    result = await dispatch(
        local_broker(store.privacy),
        "read_document",
        {"document": "inc-0142", "start_line": 1, "end_line": 16},
        agent_session(session_id=session.id),
    )
    assert "NGC-0041872" not in json.dumps(result)
    assert "[PT_" in result["text"]
