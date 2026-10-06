import json

import pytest
from hypothesis import given, strategies
from jsonschema import Draft202012Validator
from zagent.cohort import FROZEN_NOW, ClinicalStore
from zagent.drafts import DraftContent, content_hash, default_parameters
from zagent.tools import (
    COLUMNS,
    INPUTS,
    RESPONSE_SCHEMAS,
    ClinicalTools,
    McpToolClient,
    ToolsGateway,
    create_mcp_server,
)


@given(
    # Reference rows are non-clinical: the documented exception to handles-only results.
    name=strategies.sampled_from([name for name in INPUTS if name != "query_reference"]),
    rows=strategies.lists(strategies.dictionaries(strategies.text(), strategies.integers())),
    field=strategies.sampled_from(["rows", "data", "records", "values"]),
)
def test_no_tool_response_schema_permits_row_data(name, rows, field):
    validator = Draft202012Validator(RESPONSE_SCHEMAS[name])
    valid = (
        {
            "ok": True,
            "draft": {
                "draft_id": "draft-0001",
                "view_id": "view-0001",
                "version": 1,
                "app_id": "readqc",
                "specimen_handle": "query-0001",
                "parameters": default_parameters("readqc"),
                "validation": [],
                "status": "editing",
                "job_id": None,
                "content_hash": content_hash(DraftContent(app_id="readqc")),
            },
            "view_id": "view-0001",
            "kind": "draft_form",
            "title": "Read quality control",
        }
        if name == "update_draft"
        else {"ok": True, "view_id": "view-0001", "kind": "table", "title": "Specimens"}
        if name == "push_view"
        else {"handle": "query-0001", "count": 1, "schema": COLUMNS["patients"]}
    )
    valid = {
        "show_jobs": {
            "ok": True,
            "view_id": "view-0001",
            "kind": "job_grid",
            "title": "Analysis jobs",
            "handle": "jobs-0001",
            "count": 1,
        },
        "get_job": {
            "job_id": "job-0001",
            "app_id": "readqc",
            "status": "running",
            "progress": 0.5,
            "attempt": 1,
            "parameters": {},
            "specimen_handle": "query-0001",
            "total_log_lines": 0,
            "logs": [],
            "history": [],
        },
        "search_knowledge": {
            "snapshot": "a" * 64,
            "expanded_terms": [],
            "matches": [],
            "counts": {},
        },
        "get_document": {
            "snapshot": "a" * 64,
            "document": "sop-qc-001-v3",
            "title": "Read quality",
            "source": "qms",
            "doc_type": "sop",
            "version": "3",
            "status": "effective",
            "effective_from": "2025-11-03",
            "effective_to": None,
            "applies_to": ["readqc"],
            "labels": [],
            "supersedes": None,
            "superseded_by": None,
            "versions": [],
            "provenance": {},
            "line_count": 1,
            "outline": [],
        },
        "read_document": {
            "snapshot": "a" * 64,
            "document": "sop-identity-001-v1",
            "title": "Specimen identity",
            "source": "qms",
            "doc_type": "sop",
            "version": "1",
            "status": "effective",
            "start_line": 1,
            "end_line": 1,
            "truncated": False,
            "text": "Specimen identity",
        },
        "lookup_term": {
            "snapshot": "a" * 64,
            "term": "TPM",
            "definition": "Transcripts per million.",
            "synonyms": [],
            "glossary": {"document": "ref-glossary", "start_line": 1, "end_line": 2},
            "source": None,
        },
    }.get(name, valid)
    assert validator.is_valid(valid)
    assert not validator.is_valid({**valid, field: rows})
    assert not validator.is_valid(
        {"error": {"code": "unavailable", "message": "error", field: rows}}
    )
    if "schema" in valid:
        valid["schema"] = [{**COLUMNS["patients"][0], field: rows}]
        assert not validator.is_valid(valid)


@pytest.mark.integration
async def test_mcp_tools_return_only_handles_and_support_followup_queries(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Find specimens")
    gateway = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    patients = await gateway.execute(turn, "find_patients", '{"mrn":"NGC-0041872"}')
    assert patients["count"] == 1
    specimens = await gateway.execute(
        turn, "find_specimens", json.dumps({"patient_handle": patients["handle"]})
    )
    assert specimens["count"] == 3
    libraries = await gateway.execute(
        turn, "find_libraries", json.dumps({"specimen_handle": specimens["handle"]})
    )
    assert libraries["count"] == 3
    assert all(
        set(result) == {"handle", "count", "schema"} for result in [patients, specimens, libraries]
    )
    spec = {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Specimens",
            "handle": specimens["handle"],
            "columns": specimens["schema"],
            "row_count": specimens["count"],
        },
    }
    receipt = await gateway.execute(turn, "push_view", json.dumps({"spec": spec}))
    assert receipt == {
        "ok": True,
        "view_id": "view-0001",
        "kind": "table",
        "title": "Specimens",
    }
    view = (await store.snapshot(session.id)).views[-1]
    assert (view.id, view.spec.kind, view.spec.props["title"]) == (
        receipt["view_id"],
        receipt["kind"],
        receipt["title"],
    )
    assert view.spec.props["handle"] == specimens["handle"]
    assert "rows" not in json.dumps(receipt)
    assert (
        await store.pool.fetchval(
            "SELECT count(*) FROM tool_audit WHERE session_id = $1", session.id
        )
        == 4
    )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
async def test_validation_allowlist_and_unsafe_responses_are_audited(store):
    class UnsafeClient:
        calls = 0

        async def call(self, *_arguments):
            self.calls += 1
            return {"handle": "query-0001", "count": 1, "schema": [], "rows": [["private"]]}

    client = UnsafeClient()
    gateway = ToolsGateway(store, client)
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Bad arguments")
    for name, arguments, code in [
        ("sql", "{}", "unknown_tool"),
        ("find_specimens", '{"received_within":"2026-01-01"}', "invalid_arguments"),
        ("find_patients", '{"site_id":"lakeside"}', "invalid_arguments"),
        ("find_patients", "not-json", "invalid_arguments"),
        ("find_patients", "{}", "unsafe_result"),
    ]:
        result = await gateway.execute(turn, name, arguments)
        assert result["error"]["code"] == code
        assert "private" not in json.dumps(result)
    assert client.calls == 1
    assert (
        await store.pool.fetchval(
            "SELECT count(*) FROM tool_audit WHERE session_id = $1", session.id
        )
        == 5
    )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
async def test_views_validate_handle_fields_and_reject_inline_data(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    backend = ClinicalTools(clinical)
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Chart specimen purity")
    specimens = await backend.dispatch(session.id, "find_specimens", {})
    result = await backend.dispatch(
        session.id,
        "push_view",
        {
            "spec": {
                "kind": "chart",
                "version": 1,
                "props": {
                    "title": "Purity",
                    "handle": specimens["handle"],
                    "mark": "bar",
                    "encoding": {
                        "x": {"field": "id", "type": "nominal"},
                        "y": {"field": "purity", "type": "quantitative"},
                    },
                },
            }
        },
        conversation_turn_id=turn.conversation_turn_id,
    )
    assert result == {"ok": True, "view_id": "view-0001", "kind": "chart", "title": "Purity"}
    assert (await store.snapshot(session.id)).views[-1].id == result["view_id"]
    inline = {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Inline",
            "rows": [],
            "columns": COLUMNS["specimens"],
            "row_count": 0,
        },
    }
    assert (
        await backend.dispatch(
            session.id,
            "push_view",
            {"spec": inline},
            conversation_turn_id=turn.conversation_turn_id,
        )
    )["error"]["code"] == "invalid_view"
    assert len((await store.snapshot(session.id)).views) == 1
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
async def test_view_receipts_require_a_valid_view_and_an_active_turn(store):
    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    backend = ClinicalTools(clinical)
    session = await store.create_session()
    specimens = await backend.dispatch(session.id, "find_specimens", {})
    spec = {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Recent specimens",
            "handle": specimens["handle"],
            "columns": specimens["schema"],
            "row_count": specimens["count"],
        },
    }
    no_turn = await backend.dispatch(session.id, "push_view", {"spec": spec})
    assert no_turn["error"]["code"] == "invalid_view"
    assert "view_id" not in no_turn
    turn = await store.begin_conversation_turn(session.id, "Show recent specimens")
    invalid = {**spec, "props": {**spec["props"], "row_count": 0}}
    rejected = await backend.dispatch(
        session.id,
        "push_view",
        {"spec": invalid},
        conversation_turn_id=turn.conversation_turn_id,
    )
    assert rejected["error"]["code"] == "invalid_view"
    assert (await store.snapshot(session.id)).views == []
    first = await backend.dispatch(
        session.id,
        "push_view",
        {"spec": spec},
        conversation_turn_id=turn.conversation_turn_id,
    )
    second = await backend.dispatch(
        session.id,
        "push_view",
        {"spec": spec},
        conversation_turn_id=turn.conversation_turn_id,
    )
    assert first["view_id"] == "view-0001"
    assert second["view_id"] == "view-0002"
    assert [view.id for view in (await store.snapshot(session.id)).views] == [
        first["view_id"],
        second["view_id"],
    ]
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    next_turn = await store.begin_conversation_turn(session.id, "A later request")
    stale = await backend.dispatch(
        session.id,
        "push_view",
        {"spec": spec},
        conversation_turn_id=turn.conversation_turn_id,
    )
    assert stale["error"]["code"] == "invalid_view"
    assert len((await store.snapshot(session.id)).views) == 2
    await store.finish_conversation_turn(session.id, next_turn.conversation_turn_id)
