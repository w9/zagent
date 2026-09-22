from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EventType = Literal[
    "user_message",
    "run_started",
    "run_finished",
    "run_failed",
    "text_delta",
    "message_done",
    "message_dropped",
    "step_started",
    "step_finished",
    "tool_call",
    "tool_result",
    "view_pushed",
    "refused",
    "draft_updated",
]


class MessageRef(BaseModel):
    message_id: str = Field(min_length=1)


class MessageText(MessageRef):
    text: str


class Failure(BaseModel):
    error: str


class EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> "EventDraft":
        if self.type in {"user_message", "text_delta"}:
            MessageText.model_validate(self.payload)
        elif self.type in {"message_done", "message_dropped"}:
            MessageRef.model_validate(self.payload)
        elif self.type == "run_failed":
            Failure.model_validate(self.payload)
        return self


class Event(EventDraft):
    schema_version: Literal[1] = 1
    session_id: UUID
    seq: int = Field(gt=0)
    run_id: UUID
    created_at: datetime


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str = ""
    status: Literal["streaming", "complete", "failed"] = "complete"


class RunState(BaseModel):
    id: UUID
    status: Literal["running", "finished", "failed"]
    error: str | None = None


class Projection(BaseModel):
    session_id: UUID
    seq: int = 0
    messages: list[ChatMessage] = Field(default_factory=list)
    run: RunState | None = None


def reduce_event(state: Projection, event: Event) -> Projection:
    if event.session_id != state.session_id:
        raise ValueError("Event belongs to a different session")
    if event.seq <= state.seq:
        return state
    if event.seq != state.seq + 1:
        raise ValueError(f"Event gap: expected {state.seq + 1}, received {event.seq}")

    result = state.model_copy(deep=True)
    result.seq = event.seq
    payload = event.payload
    if event.type == "user_message":
        result.messages.append(
            ChatMessage(id=payload["message_id"], role="user", text=payload["text"])
        )
        result.run = RunState(id=event.run_id, status="running")
    elif event.type == "run_started":
        result.run = RunState(id=event.run_id, status="running")
    elif event.type == "text_delta":
        message = next((item for item in result.messages if item.id == payload["message_id"]), None)
        if message is None:
            message = ChatMessage(id=payload["message_id"], role="assistant", status="streaming")
            result.messages.append(message)
        message.text += payload["text"]
    elif event.type == "message_done":
        for message in result.messages:
            if message.id == payload["message_id"]:
                message.status = "complete"
    elif event.type == "message_dropped":
        result.messages = [item for item in result.messages if item.id != payload["message_id"]]
    elif event.type in {"run_finished", "run_failed"}:
        failed = event.type == "run_failed"
        result.run = RunState(
            id=event.run_id,
            status="failed" if failed else "finished",
            error=payload.get("error") if failed else None,
        )
        for message in result.messages:
            if message.status == "streaming":
                message.status = "failed" if failed else "complete"
    return result


def project(session_id: UUID, events: list[Event]) -> Projection:
    state = Projection(session_id=session_id)
    for event in events:
        state = reduce_event(state, event)
    return state


def normalize_transcript(events: list[Event]) -> list[dict[str, Any]]:
    volatile = {
        "id",
        "timestamp",
        "created_at",
        "started_at",
        "finished_at",
        "duration",
        "duration_ms",
        "duration_s",
    }

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in volatile and not key.endswith("_id")
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    normalized: list[dict[str, Any]] = []
    previous_delta = None
    for event in events:
        identity = (event.run_id, event.payload.get("message_id"))
        if event.type == "text_delta" and previous_delta == identity:
            normalized[-1]["payload"]["text"] += event.payload["text"]
        else:
            normalized.append({"type": event.type, "payload": clean(event.payload)})
        previous_delta = identity if event.type == "text_delta" else None
    return normalized
