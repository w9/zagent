import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field, model_validator

from zagent.events import Event, EventDraft, EventType
from zagent.llm import Completer, CompletionRequest, canonical_json
from zagent.store import AgentSession, Store
from zagent.tools import TOOL_DEFINITIONS, ToolsGateway

Emit = Callable[[EventDraft], Awaitable[None]]


class Agent(Protocol):
    async def run_turn(self, session: AgentSession, emit: Emit) -> None: ...


SYSTEM_PROMPT = """You are the assistant in a synthetic genomics workbench.
Answer the user's question using the four available tools when clinical data is needed.
The session is already scoped to one hospital. Never invent patient or specimen details.
Data tools return only query handles, counts and column schemas. You cannot see row contents.
Use find_patients with an exact MRN, then find_specimens with that patient_handle.
Use received_within P1D for yesterday/the last 24 hours, P7D for the last week, or P30D.
Use find_libraries with a specimen_handle for library follow-ups such as "those".
Always display requested records by calling push_view with a handle-bound table or chart.
For tables, copy columns from schema and row_count from count. Never supply rows.
For charts, choose fields only from the returned schema; rendering resolves the data privately.
Treat a tool error as feedback: correct your arguments if possible. Do not repeat invalid calls.
Make numeric claims about cohort data only when supported by tool counts in this conversation.
Do not claim to have inspected individual values. Explain that row-level analysis would require
an explicit aggregate tool if the available counts and schemas cannot answer a question.
Keep answers concise. Do not claim that an analysis or job was run.
"""


def conversation_messages(events: list[Event]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    text_messages: dict[str, dict] = {}
    tool_messages: dict[str, dict] = {}
    for event in events:
        payload = event.payload
        if event.type == "user_message":
            messages.append({"role": "user", "content": payload["text"]})
        elif event.type == "text_delta":
            message_id = payload["message_id"]
            if message_id not in text_messages:
                text_messages[message_id] = {"role": "assistant", "content": ""}
                messages.append(text_messages[message_id])
            text_messages[message_id]["content"] += payload["text"]
        elif event.type == "message_dropped":
            dropped = text_messages.pop(payload["message_id"], None)
            if dropped is not None:
                messages = [message for message in messages if message is not dropped]
        elif event.type == "tool_call":
            step_id = payload["step_id"]
            if step_id not in tool_messages:
                tool_messages[step_id] = {"role": "assistant", "tool_calls": []}
                messages.append(tool_messages[step_id])
            tool_messages[step_id]["tool_calls"].append(
                {
                    "id": payload["call_id"],
                    "type": "function",
                    "function": {"name": payload["name"], "arguments": payload["arguments"]},
                }
            )
        elif event.type == "tool_result":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": payload["call_id"],
                    "content": canonical_json(payload["result"]),
                }
            )
    return messages


class LlmAgent:
    def __init__(
        self,
        store: Store,
        gateway: Completer,
        tools: ToolsGateway,
        *,
        max_iterations: int = 8,
        route: str = "default",
    ):
        if not 1 <= max_iterations <= 20:
            raise ValueError("max_iterations must be between 1 and 20")
        self.store = store
        self.gateway = gateway
        self.tools = tools
        self.max_iterations = max_iterations
        self.route = route

    async def run_turn(self, session: AgentSession, emit: Emit) -> None:
        messages = conversation_messages(await self.store.snapshot_events(session.id))
        for iteration in range(1, self.max_iterations + 1):
            step_id = f"{session.conversation_turn_id}:step-{iteration}"
            await emit(
                EventDraft(
                    type="step_started",
                    payload={
                        "step_id": step_id,
                        "title": f"Agent step {iteration}",
                    },
                )
            )
            completion = await self.gateway.complete(
                CompletionRequest(
                    route=self.route,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                )
            )
            message = completion.message
            messages.append(message.as_message())
            if message.content:
                message_id = f"{session.conversation_turn_id}:answer-{iteration}"
                for word in re.findall(r"\S+\s*|\s+", message.content):
                    await emit(
                        EventDraft(
                            type="text_delta",
                            payload={
                                "message_id": message_id,
                                "text": word,
                            },
                        )
                    )
                await emit(EventDraft(type="message_done", payload={"message_id": message_id}))
            for call in message.tool_calls:
                await emit(
                    EventDraft(
                        type="tool_call",
                        payload={
                            "step_id": step_id,
                            "call_id": call.id,
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    )
                )
                result = await self.tools.execute(
                    session, call.function.name, call.function.arguments
                )
                await emit(
                    EventDraft(
                        type="tool_result",
                        payload={
                            "step_id": step_id,
                            "call_id": call.id,
                            "name": call.function.name,
                            "result": result,
                        },
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": canonical_json(result),
                    }
                )
                if call.function.name == "push_view" and result.get("ok"):
                    spec = json.loads(call.function.arguments)["spec"]
                    await emit(
                        EventDraft(
                            type="view_pushed",
                            payload={
                                "view_id": f"{step_id}:{call.id}",
                                "spec": spec,
                            },
                        )
                    )
            await emit(
                EventDraft(
                    type="step_finished",
                    payload={
                        "step_id": step_id,
                        "detail": ", ".join(call.function.name for call in message.tool_calls)
                        if message.tool_calls
                        else "Response complete",
                    },
                )
            )
            if not message.tool_calls:
                if not message.content:
                    raise RuntimeError("Model returned neither text nor a tool call")
                return
        raise RuntimeError(f"Agent iteration cap reached ({self.max_iterations}); turn stopped.")


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
