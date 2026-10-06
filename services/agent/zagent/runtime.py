import asyncio
import logging

from opentelemetry import trace
from opentelemetry.propagate import extract
from pydantic import ValidationError

from zagent.agent import Agent, Emit
from zagent.events import EventDraft
from zagent.privacy import EgressBlocked
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
    def __init__(self, store: Store, agent: Agent, coalesce_seconds: float = 0.18, titles=None):
        self.store = store
        self.agent = agent
        self.coalesce_seconds = coalesce_seconds
        self.tasks: dict = {}
        self.titles = titles
        self.resumable = bool(getattr(agent, "resumable", False))

    def start(self, session: AgentSession) -> None:
        if session.conversation_turn_id in self.tasks:
            return
        task = asyncio.create_task(
            self._run_turn(session), name=f"conversation_turn:{session.conversation_turn_id}"
        )
        self.tasks[session.conversation_turn_id] = task
        task.add_done_callback(lambda finished: self._finished(session, finished))

    async def recover(self) -> None:
        rows = await self.store.pool.fetch(
            """SELECT turns.session_id AS id, turns.id AS conversation_turn_id,
               events.payload->>'text' AS message, sessions.site_id, turns.caller_context
               FROM conversation_turns AS turns JOIN sessions ON sessions.id=turns.session_id
               JOIN events ON events.conversation_turn_id=turns.id AND events.type='user_message'
               WHERE turns.status='running' ORDER BY events.created_at"""
        )
        for row in rows:
            self.start(AgentSession.model_validate(dict(row)))

    def _finished(self, session: AgentSession, task: asyncio.Task) -> None:
        self.tasks.pop(session.conversation_turn_id, None)
        if not task.cancelled() and task.exception():
            logger.error(
                "Could not persist conversation turn %s outcome",
                session.conversation_turn_id,
                exc_info=task.exception(),
            )

    async def _run_turn(self, session: AgentSession) -> None:
        from zagent.telemetry import carrier

        saved = await self.store.pool.fetchval(
            "SELECT trace_context FROM conversation_turns WHERE id=$1", session.conversation_turn_id
        )
        with trace.get_tracer("zagent.runtime").start_as_current_span(
            "conversation.turn",
            context=extract(saved) if saved else None,
            attributes={
                "session.id": str(session.id),
                "conversation_turn.id": str(session.conversation_turn_id),
            },
            record_exception=False,
            set_status_on_exception=False,
        ):
            context = carrier()
            if context:
                await self.store.pool.execute(
                    "UPDATE conversation_turns SET trace_context=$2 WHERE id=$1",
                    session.conversation_turn_id,
                    context,
                )
            await self._execute_turn(session)

    async def _execute_turn(self, session: AgentSession) -> None:
        async def append(event: EventDraft) -> None:
            await self.store.append(session.id, session.conversation_turn_id, event)

        coalescer = DeltaCoalescer(append, self.coalesce_seconds)
        try:
            try:
                history = await self.store.snapshot_events(session.id)
                if not any(
                    event.type == "conversation_turn_started"
                    and event.conversation_turn_id == session.conversation_turn_id
                    for event in history
                ):
                    await append(EventDraft(type="conversation_turn_started"))
                await self.agent.run_turn(session, coalescer.emit)
            finally:
                await coalescer.close()
        except asyncio.CancelledError:
            if not self.resumable:
                await self.store.finish_conversation_turn(
                    session.id,
                    session.conversation_turn_id,
                    "Agent service stopped before the conversation turn completed.",
                )
            raise
        except Exception as error:
            detail = str(error) or type(error).__name__
            if isinstance(error, ValidationError):
                detail = "Invalid event payload: " + "; ".join(
                    issue["msg"] for issue in error.errors(include_input=False, include_url=False)
                )
            logger.warning(
                "Conversation turn %s failed: %s",
                session.conversation_turn_id,
                type(error).__name__,
            )
            if isinstance(error, EgressBlocked):
                await append(
                    EventDraft(
                        type="privacy_alert",
                        payload={
                            "code": "egress_identifier",
                            "message": "Privacy tripwire blocked the model request.",
                        },
                    )
                )
            await self.store.finish_conversation_turn(
                session.id, session.conversation_turn_id, detail
            )
        else:
            await self.store.finish_conversation_turn(session.id, session.conversation_turn_id)
            if self.titles is not None:
                self.titles.start(session)

    async def close(self) -> None:
        if self.titles is not None:
            await self.titles.close()
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
