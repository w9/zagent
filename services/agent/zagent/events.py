from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zagent.artifacts import ArtifactPublished, ArtifactSpec
from zagent.drafts import DraftState, JobState
from zagent.scope import Refusal

EventType = Literal[
    "user_message",
    "conversation_turn_started",
    "conversation_turn_finished",
    "conversation_turn_failed",
    "text_delta",
    "message_done",
    "message_dropped",
    "step_started",
    "step_finished",
    "tool_call",
    "tool_result",
    "artifact_published",
    "refused",
    "draft_updated",
    "privacy_alert",
    "job_submitted",
    "session_updated",
]


class MessageRef(BaseModel):
    message_id: str = Field(min_length=1)


class MessageText(MessageRef):
    text: str


class UserMessage(MessageText):
    retry_of: UUID | None = None


class Failure(BaseModel):
    error: str


class StepStarted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=4000)


class StepFinished(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    status: Literal["complete", "failed"] = "complete"
    detail: str | None = Field(default=None, max_length=4000)


class ToolCalled(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    arguments: str = Field(max_length=16384)


class ToolReturned(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    result: dict[str, Any]


class EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> "EventDraft":
        if self.type == "user_message":
            UserMessage.model_validate(self.payload)
        elif self.type == "text_delta":
            MessageText.model_validate(self.payload)
        elif self.type in {"message_done", "message_dropped"}:
            MessageRef.model_validate(self.payload)
        elif self.type == "conversation_turn_failed":
            Failure.model_validate(self.payload)
        elif self.type == "artifact_published":
            ArtifactPublished.model_validate(self.payload)
        elif self.type == "step_started":
            StepStarted.model_validate(self.payload)
        elif self.type == "step_finished":
            StepFinished.model_validate(self.payload)
        elif self.type == "tool_call":
            ToolCalled.model_validate(self.payload)
        elif self.type == "tool_result":
            ToolReturned.model_validate(self.payload)
        elif self.type == "refused":
            Refusal.model_validate(self.payload)
        elif self.type == "draft_updated" and "draft_id" in self.payload.get("draft", {}):
            DraftState.model_validate(self.payload["draft"])
        elif self.type == "job_submitted":
            JobState.model_validate(self.payload["job"])
        elif self.type == "privacy_alert":
            if self.payload != {
                "code": "egress_identifier",
                "message": "Privacy tripwire blocked the model request.",
            }:
                raise ValueError("Invalid privacy alert")
        return self


def renamed_key(value: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    return {(new if key == old else key): item for key, item in value.items()}


class Event(EventDraft):
    schema_version: Literal[3] = 3
    session_id: UUID
    seq: int = Field(gt=0)
    conversation_turn_id: UUID
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_event(cls, value: Any) -> Any:
        """Stored events are immutable, so older schema versions are translated on read."""
        if not isinstance(value, dict) or value.get("schema_version") not in {1, 2}:
            return value
        value = dict(value)
        if value["schema_version"] == 1:
            if "run_id" in value:
                value["conversation_turn_id"] = value.pop("run_id")
            legacy_types = {
                "run_started": "conversation_turn_started",
                "run_finished": "conversation_turn_finished",
                "run_failed": "conversation_turn_failed",
            }
            value["type"] = legacy_types.get(value["type"], value["type"])
        value["schema_version"] = 3
        payload = value.get("payload")
        if value.get("type") == "view_pushed":
            value["type"] = "artifact_published"
            if isinstance(payload, dict):
                value["payload"] = renamed_key(payload, "view_id", "artifact_id")
        elif (
            value.get("type") == "draft_updated"
            and isinstance(payload, dict)
            and isinstance(payload.get("draft"), dict)
        ):
            value["payload"] = {
                **payload,
                "draft": renamed_key(payload["draft"], "view_id", "artifact_id"),
            }
        return value


class ChatMessage(BaseModel):
    id: str
    seq: int = 0
    role: Literal["user", "assistant"]
    text: str = ""
    status: Literal["streaming", "complete", "failed"] = "complete"


class ConversationTurnState(BaseModel):
    id: UUID
    status: Literal["running", "finished", "failed"]
    error: str | None = None


class PublishedArtifact(BaseModel):
    id: str
    seq: int
    spec: ArtifactSpec


class ToolActivity(BaseModel):
    call_id: str
    name: str
    arguments: str
    result: dict[str, Any] | None = None


class StepState(BaseModel):
    id: str
    seq: int
    title: str
    detail: str = ""
    status: Literal["running", "complete", "failed"] = "running"
    tools: list[ToolActivity] = Field(default_factory=list)


class RefusedState(Refusal):
    id: str
    seq: int


class Projection(BaseModel):
    session_id: UUID
    seq: int = 0
    messages: list[ChatMessage] = Field(default_factory=list)
    artifacts: list[PublishedArtifact] = Field(default_factory=list)
    steps: list[StepState] = Field(default_factory=list)
    refusals: list[RefusedState] = Field(default_factory=list)
    drafts: dict[str, DraftState] = Field(default_factory=dict)
    jobs: dict[str, JobState] = Field(default_factory=dict)
    conversation_turn: ConversationTurnState | None = None


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
        question = next((item for item in reversed(result.messages) if item.role == "user"), None)
        if (
            question is not None
            and result.conversation_turn is not None
            and payload.get("retry_of") == str(result.conversation_turn.id)
        ):
            # A retry keeps the question and hides the attempt it replaces.
            result.messages = [item for item in result.messages if item.seq <= question.seq]
            result.steps = [item for item in result.steps if item.seq < question.seq]
            result.refusals = [item for item in result.refusals if item.seq < question.seq]
        else:
            result.messages.append(
                ChatMessage(
                    id=payload["message_id"], seq=event.seq, role="user", text=payload["text"]
                )
            )
        result.conversation_turn = ConversationTurnState(
            id=event.conversation_turn_id, status="running"
        )
    elif event.type == "conversation_turn_started":
        result.conversation_turn = ConversationTurnState(
            id=event.conversation_turn_id, status="running"
        )
    elif event.type == "text_delta":
        message = next((item for item in result.messages if item.id == payload["message_id"]), None)
        if message is None:
            message = ChatMessage(
                id=payload["message_id"], seq=event.seq, role="assistant", status="streaming"
            )
            result.messages.append(message)
        message.text += payload["text"]
    elif event.type == "message_done":
        for message in result.messages:
            if message.id == payload["message_id"]:
                message.status = "complete"
    elif event.type == "message_dropped":
        result.messages = [item for item in result.messages if item.id != payload["message_id"]]
    elif event.type == "refused":
        identity = str(event.conversation_turn_id)
        if not any(item.id == identity for item in result.refusals):
            result.refusals.append(RefusedState(id=identity, seq=event.seq, **payload))
    elif event.type == "draft_updated" and "draft_id" in payload.get("draft", {}):
        draft = DraftState.model_validate(payload["draft"])
        result.drafts[draft.draft_id] = draft
    elif event.type == "job_submitted":
        job = JobState.model_validate(payload["job"])
        result.jobs[job.job_id] = job
    elif event.type == "artifact_published":
        if not any(artifact.id == payload["artifact_id"] for artifact in result.artifacts):
            result.artifacts.append(
                PublishedArtifact(
                    id=payload["artifact_id"],
                    seq=event.seq,
                    spec=ArtifactSpec.model_validate(payload["spec"]),
                )
            )
    elif event.type == "step_started":
        if not any(step.id == payload["step_id"] for step in result.steps):
            result.steps.append(
                StepState(
                    id=payload["step_id"],
                    seq=event.seq,
                    title=payload["title"],
                    detail=payload.get("detail", ""),
                )
            )
    elif event.type == "tool_call":
        for step in result.steps:
            if step.id == payload["step_id"]:
                if not any(tool.call_id == payload["call_id"] for tool in step.tools):
                    step.tools.append(
                        ToolActivity(
                            call_id=payload["call_id"],
                            name=payload["name"],
                            arguments=payload["arguments"],
                        )
                    )
    elif event.type == "tool_result":
        for step in result.steps:
            if step.id == payload["step_id"]:
                for tool in step.tools:
                    if tool.call_id == payload["call_id"]:
                        tool.result = payload["result"]
    elif event.type == "step_finished":
        for step in result.steps:
            if step.id == payload["step_id"]:
                step.status = payload.get("status", "complete")
                if payload.get("detail") is not None:
                    step.detail = payload["detail"]
    elif event.type in {"conversation_turn_finished", "conversation_turn_failed"}:
        failed = event.type == "conversation_turn_failed"
        result.conversation_turn = ConversationTurnState(
            id=event.conversation_turn_id,
            status="failed" if failed else "finished",
            error=payload.get("error") if failed else None,
        )
        for message in result.messages:
            if message.status == "streaming":
                message.status = "failed" if failed else "complete"
        for step in result.steps:
            if step.status == "running":
                step.status = "failed" if failed else "complete"
    return result


def project(session_id: UUID, events: list[Event]) -> Projection:
    state = Projection(session_id=session_id)
    for event in events:
        state = reduce_event(state, event)
    return state


def without_retried(events: list[Event]) -> list[Event]:
    """The conversation the model continues: a retried turn's exchange is left out, but the
    artifacts, drafts and jobs it created remain."""
    retried = {
        event.payload["retry_of"]
        for event in events
        if event.type == "user_message" and event.payload.get("retry_of")
    }
    return [
        event
        for event in events
        if str(event.conversation_turn_id) not in retried
        or event.type in {"artifact_published", "draft_updated", "job_submitted", "session_updated"}
    ]


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
        identity = (event.conversation_turn_id, event.payload.get("message_id"))
        if event.type == "text_delta" and previous_delta == identity:
            normalized[-1]["payload"]["text"] += event.payload["text"]
        else:
            normalized.append({"type": event.type, "payload": clean(event.payload)})
        previous_delta = identity if event.type == "text_delta" else None
    return normalized
