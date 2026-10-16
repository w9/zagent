from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from zagent.events import (
    Event,
    EventDraft,
    Projection,
    normalize_transcript,
    project,
    reduce_event,
    without_retried,
)
from zagent.scope import REFUSAL_MESSAGES

SESSION_ID = uuid4()
CONVERSATION_TURN_ID = uuid4()


def event(seq, kind, **payload):
    return Event(
        session_id=SESSION_ID,
        seq=seq,
        conversation_turn_id=CONVERSATION_TURN_ID,
        type=kind,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def test_replay_is_idempotent_and_supports_removal():
    started = event(1, "conversation_turn_started")
    delta = event(2, "text_delta", message_id="answer", text="partial")
    state = project(SESSION_ID, [started, delta])
    assert reduce_event(state, delta) == state
    removed = reduce_event(state, event(3, "message_dropped", message_id="answer"))
    assert removed.messages == []
    assert state.messages[0].text == "partial"
    replaced = reduce_event(removed, event(4, "text_delta", message_id="new", text="replacement"))
    done = reduce_event(replaced, event(5, "message_done", message_id="new"))
    assert done.messages[0].status == "complete"
    assert done.messages[0].text == "replacement"


def test_gaps_and_cross_session_events_are_rejected():
    state = Projection(session_id=SESSION_ID)
    with pytest.raises(ValueError, match="Event gap"):
        reduce_event(state, event(2, "conversation_turn_started"))
    with pytest.raises(ValueError, match="different session"):
        reduce_event(Projection(session_id=uuid4()), event(1, "conversation_turn_started"))


def test_failure_ends_partial_messages():
    state = project(
        SESSION_ID,
        [
            event(1, "conversation_turn_started"),
            event(2, "text_delta", message_id="answer", text="partial"),
            event(3, "conversation_turn_failed", error="Scripted failure"),
        ],
    )
    assert state.conversation_turn.status == "failed"
    assert state.conversation_turn.error == "Scripted failure"
    assert state.messages[0].status == "failed"


def test_retry_hides_the_replaced_attempt_from_the_transcript_and_the_model():
    first, second, retry = uuid4(), uuid4(), uuid4()

    def turn(turn_id, seq, kind, **payload):
        return event(seq, kind, **payload).model_copy(update={"conversation_turn_id": turn_id})

    spec = {
        "kind": "table",
        "version": 1,
        "props": {
            "title": "Rows",
            "columns": [{"key": "id", "label": "Id", "type": "string"}],
            "rows": [],
            "row_count": 0,
        },
    }
    log = [
        turn(first, 1, "user_message", message_id="q1", text="Hello"),
        turn(first, 2, "text_delta", message_id="a1", text="Hi."),
        turn(first, 3, "conversation_turn_finished"),
        turn(second, 4, "user_message", message_id="q2", text="Chart it"),
        turn(second, 5, "step_started", step_id="s2", title="Agent step 1"),
        turn(second, 6, "view_pushed", view_id="view-0001", spec=spec),
        turn(second, 7, "refused", code="out_of_domain", message=REFUSAL_MESSAGES["out_of_domain"]),
        turn(second, 8, "conversation_turn_finished"),
        turn(retry, 9, "user_message", message_id="q3", text="Chart it", retry_of=str(second)),
        turn(retry, 10, "text_delta", message_id="a3", text="Done."),
        turn(retry, 11, "conversation_turn_finished"),
    ]
    state = project(SESSION_ID, log)
    assert [(message.id, message.text) for message in state.messages] == [
        ("q1", "Hello"),
        ("a1", "Hi."),
        ("q2", "Chart it"),
        ("a3", "Done."),
    ]
    assert state.steps == []
    assert state.refusals == []
    assert [view.id for view in state.views] == ["view-0001"]
    assert state.conversation_turn.id == retry
    assert [item.seq for item in without_retried(log)] == [1, 2, 3, 6, 9, 10, 11]


def test_retry_of_an_older_turn_is_an_ordinary_message():
    stale = event(2, "user_message", message_id="q2", text="Again", retry_of=str(uuid4()))
    state = project(SESSION_ID, [event(1, "user_message", message_id="q1", text="Hello"), stale])
    assert [message.id for message in state.messages] == ["q1", "q2"]


def test_normalizer_redacts_metadata_and_ignores_coalescing_boundaries():
    split = [
        event(1, "text_delta", message_id="answer", text="Hello "),
        event(2, "text_delta", message_id="answer", text="world."),
        event(3, "message_done", message_id="answer", duration_ms=150),
    ]
    combined = [
        event(1, "text_delta", message_id="different", text="Hello world."),
        event(2, "message_done", message_id="different", duration_ms=999),
    ]
    assert (
        normalize_transcript(split)
        == normalize_transcript(combined)
        == [
            {"type": "text_delta", "payload": {"text": "Hello world."}},
            {"type": "message_done", "payload": {}},
        ]
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("text_delta", {"message_id": "answer"}),
        ("message_dropped", {}),
        ("conversation_turn_failed", {}),
        ("unknown_event", {}),
    ],
)
def test_invalid_events_are_rejected(kind, payload):
    with pytest.raises(ValidationError):
        EventDraft(type=kind, payload=payload)


@pytest.mark.parametrize("kind", ["started", "finished", "failed"])
def test_legacy_events_replay_with_conversation_turn_names(kind):
    legacy = {
        "schema_version": 1,
        "session_id": SESSION_ID,
        "seq": 1,
        "run_id": CONVERSATION_TURN_ID,
        "type": f"run_{kind}",
        "payload": {"error": "Scripted failure"} if kind == "failed" else {},
        "created_at": datetime.now(UTC),
    }
    upgraded = Event.model_validate(legacy)
    serialized = upgraded.model_dump(mode="json")
    assert serialized["schema_version"] == 2
    assert serialized["conversation_turn_id"] == str(CONVERSATION_TURN_ID)
    assert serialized["type"] == f"conversation_turn_{kind}"
    assert "run_id" not in serialized
    assert legacy["schema_version"] == 1
    state = project(SESSION_ID, [upgraded])
    assert state.conversation_turn.id == CONVERSATION_TURN_ID
    assert "run" not in state.model_dump()


def test_legacy_names_are_not_accepted_for_new_events():
    with pytest.raises(ValidationError):
        EventDraft(type="run_started")
