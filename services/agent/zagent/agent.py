import asyncio
import re
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field, model_validator

from zagent.events import EventDraft, EventType
from zagent.store import AgentSession

Emit = Callable[[EventDraft], Awaitable[None]]


class Agent(Protocol):
    async def run_turn(self, session: AgentSession, emit: Emit) -> None: ...


class ScriptEvent(BaseModel):
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)


class ScriptStep(BaseModel):
    delay_ms: int = Field(default=0, ge=0)
    event: ScriptEvent | None = None
    raise_error: str | None = None

    @model_validator(mode="after")
    def check_action(self) -> "ScriptStep":
        if (self.event is None) == (self.raise_error is None):
            raise ValueError("Each step must emit an event or raise an error")
        if self.event and self.event.type in {
            "user_message",
            "conversation_turn_started",
            "conversation_turn_finished",
            "conversation_turn_failed",
        }:
            raise ValueError("The runtime owns lifecycle events")
        return self


class Script(BaseModel):
    word_delay_ms: int = Field(default=65, ge=0)
    steps: list[ScriptStep]


class ScriptedAgent:
    def __init__(self, script: Path | None = None, *, delay_scale: float = 1):
        self.script = self.load(script or files("zagent").joinpath("scripts/default.yaml"))
        self.failure = self.load(files("zagent").joinpath("scripts/failure.yaml"))
        self.invalid_view = self.load(files("zagent").joinpath("scripts/invalid-view.yaml"))
        self.delay_scale = delay_scale

    @staticmethod
    def load(path) -> Script:
        return Script.model_validate(yaml.safe_load(path.read_text()))

    async def run_turn(self, session: AgentSession, emit: Emit) -> None:
        script = {"/fail": self.failure, "/invalid-view": self.invalid_view}.get(
            session.message.strip(), self.script
        )
        for step in script.steps:
            await asyncio.sleep(step.delay_ms * self.delay_scale / 1000)
            if step.raise_error is not None:
                raise RuntimeError(step.raise_error)
            event = step.event.model_copy(deep=True)
            for key in ("message_id", "view_id", "step_id"):
                if key in event.payload:
                    event.payload[key] = f"{session.conversation_turn_id}:{event.payload[key]}"
            if event.type == "text_delta":
                for word in re.findall(r"\S+\s*|\s+", event.payload["text"]):
                    await asyncio.sleep(script.word_delay_ms * self.delay_scale / 1000)
                    await emit(
                        EventDraft(type="text_delta", payload={**event.payload, "text": word})
                    )
            else:
                await emit(EventDraft(type=event.type, payload=event.payload))
