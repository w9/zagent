import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from zagent.agent import ScriptedAgent
from zagent.events import Event, EventDraft, Projection, project, reduce_event
from zagent.runtime import Runtime
from zagent.views import ViewSpec


def table_spec(**props):
    return {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Specimens received in the last 24 hours",
            "columns": [{"key": "specimen_id", "label": "Specimen", "type": "string"}],
            "rows": [["SPC-0001"]],
            "row_count": 14,
            **props,
        },
    }


@pytest.mark.parametrize("rows,row_count", [([["SPC-0001"]], 14), ([], 0), ([[None]], 1)])
def test_table_schema_accepts_complete_empty_and_truncated_data(rows, row_count):
    spec = table_spec(rows=rows, row_count=row_count)
    draft = EventDraft(type="view_pushed", payload={"view_id": "table-1", "spec": spec})
    assert draft.payload["spec"] == spec


@pytest.mark.parametrize(
    "props",
    [
        {"rows": [["SPC-0001", "extra"]]},
        {"rows": [[12]]},
        {"rows": [{"specimen_id": "SPC-0001"}]},
        {"row_count": -1},
        {"row_count": 0},
        {"columns": []},
        {"columns": [{"key": "x", "label": "X", "type": "markup"}]},
        {"handle": "query-1"},
        {"onclick": "alert(1)"},
    ],
)
def test_invalid_specs_are_rejected_at_the_event_boundary(props):
    with pytest.raises(ValidationError, match="View schema error"):
        EventDraft(type="view_pushed", payload={"view_id": "table-1", "spec": table_spec(**props)})


def test_view_identity_and_version_are_required():
    with pytest.raises(ValidationError):
        EventDraft(type="view_pushed", payload={"spec": table_spec()})
    for kind, version in [("unknown", 1), ("table", 2)]:
        spec = {**table_spec(), "kind": kind, "version": version}
        with pytest.raises(ValidationError, match="unsupported"):
            ViewSpec.model_validate(spec)


def test_handle_and_inline_rows_are_alternative_sources():
    spec = table_spec()
    spec["props"].pop("rows")
    with pytest.raises(ValidationError):
        ViewSpec.model_validate(spec)
    spec["props"]["handle"] = "query-1"
    assert ViewSpec.model_validate(spec).props["handle"] == "query-1"
    spec["props"]["rows"] = []
    with pytest.raises(ValidationError):
        ViewSpec.model_validate(spec)


def test_column_keys_are_unique_and_booleans_are_not_numbers():
    spec = table_spec()
    spec["props"]["columns"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        ViewSpec.model_validate(spec)
    spec = table_spec(rows=[[True]])
    spec["props"]["columns"][0]["type"] = "number"
    original = copy.deepcopy(spec)
    with pytest.raises(ValidationError, match="cell"):
        ViewSpec.model_validate(spec)
    assert spec == original


def test_view_and_step_replay_agrees_for_every_shared_prefix():
    fixture = json.loads(
        (Path(__file__).parents[3] / "evals/fixtures/view-replay.json").read_text()
    )
    session_id, turn_id = uuid4(), uuid4()
    events = [
        Event(
            **draft,
            seq=index + 1,
            session_id=session_id,
            conversation_turn_id=turn_id,
            created_at=datetime.now(UTC),
        )
        for index, draft in enumerate(fixture["events"])
    ]
    state = Projection(session_id=session_id)
    for index, event in enumerate(events):
        previous = state.model_copy(deep=True)
        state = reduce_event(state, event)
        assert [view.id for view in state.views] == fixture["prefix_view_ids"][index]
        assert state == project(session_id, events[: index + 1])
        assert reduce_event(state, event) == state
        assert previous == project(session_id, events[:index])
        restored = Projection.model_validate_json(state.model_dump_json())
        for remaining in events[index + 1 :]:
            restored = reduce_event(restored, remaining)
        assert restored == project(session_id, events)
    assert [view.seq for view in state.views] == [4, 8]
    assert [(step.seq, step.status) for step in state.steps] == [(3, "complete"), (7, "complete")]
    assert state.steps[0].detail == "14 specimens; 1 displayed."
    assert state.messages[-1].seq == 5


@pytest.mark.integration
async def test_invalid_scripted_view_fails_turn_without_changing_surface(store, tmp_path):
    import yaml

    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "First")
    await store.append(
        session.id,
        turn.conversation_turn_id,
        EventDraft(type="view_pushed", payload={"view_id": "existing", "spec": table_spec()}),
    )
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    original_views = (await store.snapshot(session.id)).views
    script = tmp_path / "invalid.yaml"
    script.write_text(
        yaml.safe_dump(
            {
                "steps": [
                    {
                        "event": {
                            "type": "step_started",
                            "payload": {"step_id": "invalid", "title": "Invalid fixture"},
                        }
                    },
                    {
                        "event": {
                            "type": "view_pushed",
                            "payload": {"view_id": "bad", "spec": table_spec(row_count=-1)},
                        }
                    },
                ]
            }
        )
    )
    runtime = Runtime(store, ScriptedAgent(script, delay_scale=0))
    turn = await store.begin_conversation_turn(session.id, "Invalid view")
    await runtime._run_turn(turn)
    snapshot = await store.snapshot(session.id)
    assert snapshot.conversation_turn.status == "failed"
    assert "View schema error" in snapshot.conversation_turn.error
    assert snapshot.views == original_views
    assert snapshot.steps[-1].status == "failed"
    assert (await store.events_after(session.id, 0))[-1].type == "conversation_turn_failed"


@pytest.mark.integration
async def test_store_revalidates_mutated_view_before_allocating_sequence(store):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Hello")
    draft = EventDraft(type="view_pushed", payload={"view_id": "view", "spec": table_spec()})
    draft.payload["spec"]["props"]["row_count"] = -1
    with pytest.raises(ValidationError, match="View schema error"):
        await store.append(session.id, turn.conversation_turn_id, draft)
    assert (await store.get_session(session.id)).seq == 1
