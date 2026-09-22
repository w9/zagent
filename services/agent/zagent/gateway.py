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


def configured_gateway(mode: str | None = None) -> LlmGateway:
    routes = {
        name: ModelRoute.model_validate(route)
        for name, route in json.loads(os.environ.get("ZAGENT_MODEL_ROUTES") or "{}").items()
    } or {"default": ModelRoute(model=os.environ.get("ZAGENT_MODEL", DEFAULT_MODEL))}
    return LlmGateway(
        Path(os.environ.get("ZAGENT_CASSETTE_DIR", str(files("zagent").joinpath("cassettes")))),
        mode=mode or os.environ.get("ZAGENT_LLM_MODE", "replay"),
        routes=routes,
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
                for host, port in (("web", 5173), ("agent", 8000), ("postgres", 5432)):
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

    @app.exception_handler(GatewayError)
    async def gateway_error(_request: Request, error: GatewayError):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": gateway.mode}

    @app.post("/complete", response_model=Completion)
    async def complete(request: CompletionRequest):
        return await gateway.complete(request)

    return app


app = create_gateway_app()
