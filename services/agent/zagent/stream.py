import asyncio
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from uuid import UUID

import asyncpg
from fastapi import Request

from zagent.display import SessionDisplay
from zagent.store import NOTIFY_CHANNEL, Store


class Notifications:
    def __init__(self, connection: asyncpg.Connection):
        self.connection = connection
        self.subscribers: dict[str, set[asyncio.Event]] = defaultdict(set)

    @classmethod
    async def open(cls, database_url: str) -> "Notifications":
        instance = cls(await asyncpg.connect(database_url))
        await instance.connection.add_listener(NOTIFY_CHANNEL, instance.on_notify)
        return instance

    def on_notify(self, connection, pid, channel, payload) -> None:
        for signal in self.subscribers.get(payload, ()):
            signal.set()

    @asynccontextmanager
    async def subscribe(self, session_id: UUID):
        key = str(session_id)
        signal = asyncio.Event()
        self.subscribers[key].add(signal)
        try:
            yield signal
        finally:
            self.subscribers[key].discard(signal)
            if not self.subscribers[key]:
                del self.subscribers[key]

    async def close(self) -> None:
        await self.connection.close()


async def tail_events(
    request: Request,
    store: Store,
    notifications: Notifications,
    session_id: UUID,
    cursor: int,
    *,
    follow: bool,
    poll_seconds: float,
    display: SessionDisplay | None = None,
):
    yield "retry: 1000\n\n"
    async with notifications.subscribe(session_id) as signal:
        announced = None
        while not await request.is_disconnected():
            signal.clear()
            events = await store.events_after(session_id, cursor)
            for event in events:
                rendered = await display.event(event) if display is not None else event
                yield f"id: {event.seq}\nevent: log\ndata: {rendered.model_dump_json()}\n\n"
                cursor = event.seq
            if events:
                continue
            head, active = await store.head(session_id)
            if head > cursor:
                continue
            if announced != (head, active):
                data = json.dumps({"seq": head, "active": active})
                yield f"event: caught_up\ndata: {data}\n\n"
                announced = (head, active)
            if not follow and head > 0 and not active:
                return
            try:
                await asyncio.wait_for(signal.wait(), timeout=poll_seconds)
            except TimeoutError:
                yield ": keep-alive\n\n"
