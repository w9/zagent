from contextlib import asynccontextmanager

from fastapi import FastAPI

from zknowledge.server import create_server
from zknowledge.snapshot import SnapshotStore
from zknowledge.telemetry import configure_telemetry


def create_app(snapshots: SnapshotStore | None = None) -> FastAPI:
    snapshots = snapshots or SnapshotStore.configured()
    server = create_server(snapshots)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with server.session_manager.run():
            yield

    app = FastAPI(title="Knowledge MCP", lifespan=lifespan)
    configure_telemetry("zknowledge", app)

    @app.get("/health")
    async def health():
        snapshot = snapshots.open()
        try:
            return {"status": "ok", "snapshot": snapshot.version}
        finally:
            snapshot.close()

    app.mount("/", server.streamable_http_app())
    return app


app = create_app()
