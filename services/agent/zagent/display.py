from typing import Any
from uuid import UUID

from zagent.events import Event, Projection
from zagent.privacy import TOKEN, Detector, DisplayHoldback, SessionTokens, Tokenized, string_values
from zagent.privacy_client import Resolver


class SessionDisplay:
    def __init__(self, session_id: UUID, privacy: Resolver):
        self.session_id = session_id
        self.privacy = privacy
        self.vault = SessionTokens(Detector())
        self.buffers: dict[str, DisplayHoldback] = {}

    async def refresh(self) -> None:
        self.vault = SessionTokens(Detector(), await self.privacy.bindings(self.session_id))

    async def ensure_bindings(self, value: Any) -> None:
        tokens = {match.group() for text in string_values(value) for match in TOKEN.finditer(text)}
        if tokens - self.vault.by_token.keys():
            await self.refresh()

    def resolve_text(self, value: str) -> str:
        return self.vault.resolve(Tokenized(value=value)).value

    async def event(self, event: Event) -> Event:
        await self.ensure_bindings(event.payload)
        payload = self.vault.resolve(Tokenized(value=event.payload)).value
        if event.type == "text_delta":
            message_id = event.payload["message_id"]
            buffer = self.buffers.setdefault(message_id, DisplayHoldback(self.resolve_text))
            await self.ensure_bindings(buffer.pending + event.payload["text"])
            payload["text"] = buffer.feed(event.payload["text"])
        elif event.type in {"message_done", "message_dropped"}:
            self.buffers.pop(event.payload["message_id"], None)
        elif event.type in {"conversation_turn_finished", "conversation_turn_failed"}:
            self.buffers.clear()
        return event.model_copy(update={"payload": payload})

    async def projection(self, projection: Projection) -> Projection:
        source = projection.model_dump(mode="json")
        await self.ensure_bindings(source)
        displayed = self.vault.resolve(Tokenized(value=source)).value
        for original, message in zip(projection.messages, displayed["messages"], strict=True):
            message["text"] = DisplayHoldback(self.resolve_text).feed(original.text)
        return Projection.model_validate(displayed)
