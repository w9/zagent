import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from zagent.faults import enabled
from zagent.identity import (
    CALLER_CONTEXT_META,
    PERSONAS,
    CallerContext,
    CallerRejected,
    CallerVerifier,
)
from zagent.kb_tools import (
    KB_CONTRACT_SHA256,
    KB_DESCRIPTIONS,
    KB_INPUTS,
    KB_OUTPUTS,
    KB_SNAPSHOT_META,
    contract_hash,
)
from zagent.privacy import Raw
from zagent.privacy_client import PrivacyClient, Tokenizer
from zagent.tools import McpToolClient, failure

SNAPSHOT_META = "zknowledge/snapshot"
CALLER_META = "zknowledge/caller"
SNAPSHOT_ID = re.compile(r"[a-f0-9]{64}")
CONTRACT_TTL_SECONDS = 60
SERVICE_ROLES = tuple(sorted({role for persona in PERSONAS.values() for role in persona.roles}))
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
        verifier: CallerVerifier | None = None,
        snapshot: str | None = None,
        timeout: float = 10,
        contract: str = KB_CONTRACT_SHA256,
    ):
        self.upstream = upstream
        self.tokenizer = tokenizer
        self.verifier = verifier or CallerVerifier.configured()
        self.snapshot = snapshot
        self.timeout = timeout
        self.contract = contract
        self.verified_at: float | None = None

    async def verify_contract(self) -> None:
        if enabled("skip_contract_pin"):
            return
        if self.verified_at and time.monotonic() - self.verified_at < CONTRACT_TTL_SECONDS:
            return
        observed = contract_hash(await self.upstream.tool_schemas())
        if observed != self.contract:
            self.verified_at = None
            logger.error("Knowledge contract changed: expected %s, got %s", self.contract, observed)
            raise ContractChanged(observed)
        self.verified_at = time.monotonic()

    def upstream_meta(self, caller: CallerContext, pinned: str | None = None) -> dict:
        """Request metadata for the knowledge service: the verified caller, never model input."""
        roles = SERVICE_ROLES if enabled("acl_off") else caller.roles
        meta: dict = {CALLER_META: {"site": caller.site, "roles": list(roles)}}
        snapshot = self.snapshot or (None if enabled("ignore_snapshot_pin") else pinned)
        if snapshot:
            meta[SNAPSHOT_META] = snapshot
        return meta

    async def dispatch(
        self,
        session_id: UUID,
        turn_id: UUID,
        name: str,
        arguments: dict,
        caller_context: str | None = None,
        snapshot: str | None = None,
    ) -> dict:
        try:
            params = KB_INPUTS[name].model_validate(arguments)
        except (KeyError, ValidationError):
            return failure("invalid_arguments", "Arguments do not match the knowledge tool schema")
        try:
            caller = self.verifier.verify(caller_context, session_id=session_id, turn_id=turn_id)
        except CallerRejected as error:
            logger.warning("Knowledge call rejected: %s", error)
            result = failure(
                "unavailable", "Knowledge access could not be verified for this conversation turn"
            )
        else:
            pinned = (
                snapshot if isinstance(snapshot, str) and SNAPSHOT_ID.fullmatch(snapshot) else None
            )
            result = await self.fetch(name, params.model_dump(exclude_none=True), caller, pinned)
        if enabled("broker_tokenize_off"):
            return result
        return (
            await self.tokenizer.tokenize(
                session_id, Raw(value=result), path="retrieved_document", external=True
            )
        ).value

    async def fetch(
        self, name: str, arguments: dict, caller: CallerContext, pinned: str | None = None
    ) -> dict:
        try:
            async with asyncio.timeout(self.timeout):
                await self.verify_contract()
                result = await self.upstream.invoke(
                    name, arguments, meta=self.upstream_meta(caller, pinned)
                )
        except ContractChanged:
            return failure(
                "unavailable",
                "Knowledge tools are disabled until the upstream contract is reviewed",
            )
        except Exception:
            return failure("unavailable", "Knowledge service is unavailable")
        if "error" in result:
            error = result["error"] if isinstance(result["error"], dict) else {}
            code = error.get("code")
            return failure(
                code if code in {"invalid_arguments", "not_found"} else "unavailable",
                str(error.get("message") or "Knowledge request failed"),
            )
        try:
            KB_OUTPUTS[name].model_validate(result)
        except ValidationError:
            return failure("unsafe_result", "Knowledge service returned an invalid result")
        return result


def create_broker_server(broker: KnowledgeBroker) -> FastMCP:
    server = FastMCP("zagent-broker", host="0.0.0.0", stateless_http=True, json_response=True)

    def register(name: str) -> None:
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict[str, Any],
            ctx: Context,
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            meta = ctx.request_context.meta
            extra = (meta.model_extra or {}) if meta else {}
            return await broker.dispatch(
                UUID(session_id),
                UUID(conversation_turn_id),
                name,
                arguments,
                caller_context=extra.get(CALLER_CONTEXT_META),
                snapshot=extra.get(KB_SNAPSHOT_META),
            )

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
