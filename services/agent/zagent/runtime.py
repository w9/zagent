import asyncio
import logging

from zagent.agent import Agent, Emit
from zagent.events import EventDraft
from zagent.store import AgentSession, Store

logger = logging.getLogger(__name__)


class DeltaCoalescer:
    def __init__(self, append: Emit, interval: float):
        self.append = append
        self.interval = interval
        self.pending: EventDraft | None = None
        self.lock = asyncio.Lock()
        self.timer = asyncio.create_task(self._tick())

    async def _flush(self) -> None:
        if self.pending is not None:
            await self.append(self.pending)
            self.pending = None

    def _check_timer(self) -> None:
        if self.timer.done():
            self.timer.result()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            async with self.lock:
                await self._flush()

    async def emit(self, event: EventDraft) -> None:
        async with self.lock:
            self._check_timer()
            if event.type == "text_delta":
                if (
                    self.pending
                    and self.pending.payload["message_id"] != event.payload["message_id"]
                ):
                    await self._flush()
                if self.pending:
                    self.pending.payload["text"] += event.payload["text"]
                else:
                    self.pending = event.model_copy(deep=True)
            else:
                await self._flush()
                await self.append(event)

    async def close(self) -> None:
        try:
            async with self.lock:
                try:
                    self._check_timer()
                    await self._flush()
                finally:
                    self.timer.cancel()
        finally:
            await asyncio.gather(self.timer, return_exceptions=True)


class Runtime:
    def __init__(self, store: Store, agent: Agent, coalesce_seconds: float = 0.18):
        self.store = store
        self.agent = agent
        self.coalesce_seconds = coalesce_seconds
        self.tasks: dict = {}

    def start(self, session: AgentSession) -> None:
        task = asyncio.create_task(
            self._run_turn(session), name=f"conversation_turn:{session.conversation_turn_id}"
        )
        self.tasks[session.conversation_turn_id] = task
        task.add_done_callback(lambda finished: self._finished(session, finished))

    def _finished(self, session: AgentSession, task: asyncio.Task) -> None:
        self.tasks.pop(session.conversation_turn_id, None)
        if not task.cancelled() and task.exception():
            logger.error(
                "Could not persist conversation turn %s outcome",
                session.conversation_turn_id,
                exc_info=task.exception(),
            )

    async def _run_turn(self, session: AgentSession) -> None:
        async def append(event: EventDraft) -> None:
            await self.store.append(session.id, session.conversation_turn_id, event)

        coalescer = DeltaCoalescer(append, self.coalesce_seconds)
        try:
            try:
                await append(EventDraft(type="conversation_turn_started"))
                await self.agent.run_turn(session, coalescer.emit)
            finally:
                await coalescer.close()
        except asyncio.CancelledError:
            await self.store.finish_conversation_turn(
                session.id,
                session.conversation_turn_id,
                "Agent service stopped before the conversation turn completed.",
            )
            raise
        except Exception as error:
            logger.warning("Conversation turn %s failed: %s", session.conversation_turn_id, error)
            await self.store.finish_conversation_turn(
                session.id, session.conversation_turn_id, str(error) or type(error).__name__
            )
        else:
            await self.store.finish_conversation_turn(session.id, session.conversation_turn_id)

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
