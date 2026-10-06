from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from zknowledge.index import IndexStore
from zknowledge.server import create_server
from zknowledge.server_v2 import create_server_v2
from zknowledge.snapshot import SnapshotStore
from zknowledge.telemetry import configure_telemetry


def create_app(snapshots: SnapshotStore | None = None) -> FastAPI:
    snapshots = snapshots or SnapshotStore.configured()
    index = IndexStore(snapshots.directory / "v2")
    server = create_server(snapshots)
    server_v2 = create_server_v2(index)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(server.session_manager.run())
            await stack.enter_async_context(server_v2.session_manager.run())
            yield

    app = FastAPI(title="Knowledge MCP", lifespan=lifespan)
    configure_telemetry("zknowledge", app)

    @app.get("/health")
    async def health():
        legacy, current = snapshots.open(), index.open()
        try:
            return {"status": "ok", "snapshot": legacy.version, "snapshot_v2": current.snapshot}
        finally:
            legacy.close()
            current.close()

    app.mount("/v2", server_v2.streamable_http_app())
    app.mount("/", server.streamable_http_app())
    return app


app = create_app()
