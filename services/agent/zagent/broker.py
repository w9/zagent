import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from zagent.kb_tools import (
    KB_CONTRACT_SHA256,
    KB_DESCRIPTIONS,
    KB_INPUTS,
    KB_OUTPUTS,
    contract_hash,
)
from zagent.privacy import Raw
from zagent.privacy_client import PrivacyClient, Tokenizer
from zagent.tools import McpToolClient, failure

SNAPSHOT_META = "zknowledge/snapshot"
CONTRACT_TTL_SECONDS = 60
logger = logging.getLogger("zagent.broker")


class ContractChanged(Exception):
    pass


class KnowledgeBroker:
    """The only path from the agent zone to the knowledge service."""

    def __init__(
        self,
        upstream: McpToolClient,
        tokenizer: Tokenizer,
        *,
        snapshot: str | None = None,
        timeout: float = 10,
        contract: str = KB_CONTRACT_SHA256,
    ):
        self.upstream = upstream
        self.tokenizer = tokenizer
        self.snapshot = snapshot
        self.timeout = timeout
        self.contract = contract
        self.verified_at: float | None = None

    async def verify_contract(self) -> None:
        if self.verified_at and time.monotonic() - self.verified_at < CONTRACT_TTL_SECONDS:
            return
        observed = contract_hash(await self.upstream.tool_schemas())
        if observed != self.contract:
            self.verified_at = None
            logger.error("Knowledge contract changed: expected %s, got %s", self.contract, observed)
            raise ContractChanged(observed)
        self.verified_at = time.monotonic()

    async def dispatch(self, session_id: UUID, name: str, arguments: dict) -> dict:
        try:
            params = KB_INPUTS[name].model_validate(arguments)
        except (KeyError, ValidationError):
            return failure("invalid_arguments", "Arguments do not match the knowledge tool schema")
        try:
            async with asyncio.timeout(self.timeout):
                await self.verify_contract()
                result = await self.upstream.invoke(
                    name,
                    params.model_dump(),
                    meta={SNAPSHOT_META: self.snapshot} if self.snapshot else None,
                )
        except ContractChanged:
            result = failure(
                "unavailable",
                "Knowledge tools are disabled until the upstream contract is reviewed",
            )
        except Exception:
            result = failure("unavailable", "Knowledge service is unavailable")
        else:
            if "error" in result:
                error = result["error"] if isinstance(result["error"], dict) else {}
                code = error.get("code")
                result = failure(
                    code if code == "invalid_arguments" else "unavailable",
                    str(error.get("message") or "Knowledge request failed"),
                )
            else:
                try:
                    KB_OUTPUTS[name].model_validate(result)
                except ValidationError:
                    result = failure(
                        "unsafe_result", "Knowledge service returned an invalid result"
                    )
        return (
            await self.tokenizer.tokenize(
                session_id, Raw(value=result), path="retrieved_document", external=True
            )
        ).value


def create_broker_server(broker: KnowledgeBroker) -> FastMCP:
    server = FastMCP("zagent-broker", host="0.0.0.0", stateless_http=True, json_response=True)

    def register(name: str) -> None:
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict[str, Any],
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            return await broker.dispatch(UUID(session_id), name, arguments)

        server.add_tool(
            invoke,
            name=name,
            description=KB_DESCRIPTIONS[name],
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
            ),
        )

    for name in KB_INPUTS:
        register(name)
    return server


def create_broker_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broker = KnowledgeBroker(
            McpToolClient(url=os.environ.get("ZAGENT_KB_URL", "http://kb:8007/mcp")),
            PrivacyClient.configured(),
            snapshot=os.environ.get("ZAGENT_KB_SNAPSHOT") or None,
        )
        server = create_broker_server(broker)
        app.mount("/", server.streamable_http_app())
        async with server.session_manager.run():
            yield

    app = FastAPI(title="Zagent MCP broker", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-broker", app)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_broker_app()
