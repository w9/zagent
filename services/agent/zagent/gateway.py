import asyncio
import json
import os
from contextlib import AsyncExitStack, asynccontextmanager
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from zagent.llm import (
    DEFAULT_MODEL,
    Completion,
    CompletionRequest,
    GatewayError,
    LlmGateway,
    ModelRoute,
)
from zagent.privacy import EgressBlocked, PrivacyError
from zagent.privacy_client import GatewayPrivacy, PrivacyClient


async def forward_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, host: str, port: int
) -> None:
    remote_writer = None
    transfers = []

    async def copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        while chunk := await source.read(65536):
            destination.write(chunk)
            await destination.drain()
        if destination.can_write_eof():
            destination.write_eof()

    try:
        async with asyncio.timeout(10):
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        transfers = [
            asyncio.create_task(copy(reader, remote_writer)),
            asyncio.create_task(copy(remote_reader, writer)),
        ]
        await asyncio.gather(*transfers)
    except (OSError, TimeoutError):
        pass
    finally:
        for transfer in transfers:
            transfer.cancel()
        await asyncio.gather(*transfers, return_exceptions=True)
        writers = [writer] + ([remote_writer] if remote_writer is not None else [])
        for destination in writers:
            destination.close()
        await asyncio.gather(
            *(destination.wait_closed() for destination in writers), return_exceptions=True
        )


def configured_gateway(
    mode: str | None = None, *, egress_check=None, protect_response=None
) -> LlmGateway:
    routes = {
        name: ModelRoute.model_validate(route)
        for name, route in json.loads(os.environ.get("ZAGENT_MODEL_ROUTES") or "{}").items()
    } or {"default": ModelRoute(model=os.environ.get("ZAGENT_MODEL", DEFAULT_MODEL))}
    if os.environ.get("ZAGENT_PRIVACY_URL"):
        privacy = GatewayPrivacy(PrivacyClient.configured("gateway"))
        egress_check = privacy.check
        protect_response = privacy.protect_response
    elif egress_check is None:

        def unconfigured(_request):
            raise PrivacyError("Configure the privacy service before model access")

        egress_check = unconfigured
    return LlmGateway(
        Path(os.environ.get("ZAGENT_CASSETTE_DIR", str(files("zagent").joinpath("cassettes")))),
        mode=mode or os.environ.get("ZAGENT_LLM_MODE", "replay"),
        routes=routes,
        egress_check=egress_check,
        protect_response=protect_response,
        audit_path=Path(
            os.environ.get(
                "ZAGENT_GATEWAY_AUDIT",
                str(
                    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
                    / "zagent/gateway-audit.sqlite3"
                ),
            )
        ),
    )


def create_gateway_app(gateway: LlmGateway | None = None) -> FastAPI:
    gateway = gateway or configured_gateway()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        connections: set[asyncio.Task] = set()

        def handler(host: str, port: int):
            async def forward(reader, writer):
                task = asyncio.current_task()
                connections.add(task)
                try:
                    await forward_connection(reader, writer, host=host, port=port)
                finally:
                    connections.discard(task)

            return forward

        async with AsyncExitStack() as resources:
            if os.environ.get("ZAGENT_LOCAL_INGRESS") == "1":
                for host, port in (("web", 5173), ("bff", 8000), ("postgres", 5432)):
                    listener = await asyncio.start_server(handler(host, port), "0.0.0.0", port)
                    await resources.enter_async_context(listener)
            try:
                yield
            finally:
                pending = list(connections)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

    app = FastAPI(title="Zagent model gateway", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-llm-gateway", app)

    @app.exception_handler(PrivacyError)
    async def privacy_error(_request: Request, error: PrivacyError):
        return JSONResponse(
            status_code=502,
            content={
                "code": "egress_identifier"
                if isinstance(error, EgressBlocked)
                else "privacy_unavailable",
                "detail": str(error),
            },
        )

    @app.exception_handler(GatewayError)
    async def gateway_error(_request: Request, error: GatewayError):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": gateway.mode}

    @app.post("/complete", response_model=Completion)
    async def complete(request: CompletionRequest):
        return await gateway.complete(request)

    @app.get("/sessions/{session_id}/model-requests")
    async def model_requests(session_id: str):
        return await asyncio.to_thread(gateway.requests_for_session, session_id)

    return app


app = create_gateway_app()
