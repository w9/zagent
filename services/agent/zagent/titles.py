import asyncio
import logging

from zagent.llm import Completer, CompletionRequest
from zagent.store import AgentSession, Store

TITLE_PROMPT = """Write a short plain-text topic title for this genomics workbench conversation.
Return only the title, at most 60 characters. Describe the activity, not patient identities.
Do not include identifiers, privacy tokens, query handles, quotes, or Markdown.
"""
logger = logging.getLogger(__name__)


class SessionTitles:
    def __init__(self, store: Store, gateway: Completer):
        self.store = store
        self.gateway = gateway
        self.tasks: set[asyncio.Task] = set()

    def start(self, session: AgentSession) -> None:
        task = asyncio.create_task(self.generate(session), name=f"session-title:{session.id}")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def generate(self, session: AgentSession) -> None:
        try:
            events = [
                event
                for event in await self.store.snapshot_events(session.id)
                if event.conversation_turn_id == session.conversation_turn_id
            ]
            if any(event.type == "refused" for event in events) or not any(
                event.type == "message_done" for event in events
            ):
                return
            user = next(event.payload["text"] for event in events if event.type == "user_message")
            assistant = "".join(
                event.payload["text"] for event in events if event.type == "text_delta"
            )[:2000]
            if not user.strip() or not assistant.strip():
                return
            if not await self.store.claim_title(session.id):
                return
            async with asyncio.timeout(15):
                result = await self.gateway.complete(
                    CompletionRequest(
                        messages=[
                            {"role": "system", "content": TITLE_PROMPT},
                            {"role": "user", "content": user},
                            {"role": "assistant", "content": assistant},
                        ],
                        max_tokens=80,
                        reasoning="disabled",
                        metadata={
                            "session_id": str(session.id),
                            "conversation_turn_id": str(session.conversation_turn_id),
                            "purpose": "session_title",
                        },
                    )
                )
            text = (result.message.content or "").strip().strip('"')
            if result.message.tool_calls or not text or len(text) > 60 or "\n" in text:
                return
            from zagent.privacy import TOKEN

            if TOKEN.search(text) or "query-" in text or "view-" in text:
                return
            await self.store.rename_session(session.id, text, automatic=True)
        except Exception as error:
            logger.info("Optional session title unavailable: %s", type(error).__name__)

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
