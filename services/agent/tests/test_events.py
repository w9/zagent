from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from zagent.events import Event, EventDraft, Projection, normalize_transcript, project, reduce_event

SESSION_ID = uuid4()
RUN_ID = uuid4()


def event(seq, kind, **payload):
    return Event(
        session_id=SESSION_ID,
        seq=seq,
        run_id=RUN_ID,
        type=kind,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def test_replay_is_idempotent_and_supports_removal():
    started = event(1, "run_started")
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
        reduce_event(state, event(2, "run_started"))
    with pytest.raises(ValueError, match="different session"):
        reduce_event(Projection(session_id=uuid4()), event(1, "run_started"))


def test_failure_ends_partial_messages():
    state = project(
        SESSION_ID,
        [
            event(1, "run_started"),
            event(2, "text_delta", message_id="answer", text="partial"),
            event(3, "run_failed", error="Scripted failure"),
        ],
    )
    assert state.run.status == "failed"
    assert state.run.error == "Scripted failure"
    assert state.messages[0].status == "failed"


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
        ("run_failed", {}),
        ("unknown_event", {}),
    ],
)
def test_invalid_events_are_rejected(kind, payload):
    with pytest.raises(ValidationError):
        EventDraft(type=kind, payload=payload)
