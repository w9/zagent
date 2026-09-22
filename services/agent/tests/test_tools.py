import json

import pytest
from hypothesis import given, strategies
from jsonschema import Draft202012Validator
from zagent.cohort import FROZEN_NOW, ClinicalStore
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
    name=strategies.sampled_from(list(INPUTS)),
    rows=strategies.lists(strategies.dictionaries(strategies.text(), strategies.integers())),
    field=strategies.sampled_from(["rows", "data", "records", "values"]),
)
def test_no_tool_response_schema_permits_row_data(name, rows, field):
    validator = Draft202012Validator(RESPONSE_SCHEMAS[name])
    valid = (
        {"ok": True, "handle": "query-0001"}
        if name == "push_view"
        else {"handle": "query-0001", "count": 1, "schema": COLUMNS["patients"]}
    )
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
    assert (await gateway.execute(turn, "push_view", json.dumps({"spec": spec})))["ok"]
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
    )
    assert result["ok"]
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
    assert (await backend.dispatch(session.id, "push_view", {"spec": inline}))["error"][
        "code"
    ] == "invalid_view"
