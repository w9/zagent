from contextlib import asynccontextmanager

from fastapi import FastAPI

from zknowledge.index import IndexStore
from zknowledge.server import create_server
from zknowledge.snapshot import snapshot_directory
from zknowledge.telemetry import configure_telemetry


def create_app(store: IndexStore | None = None) -> FastAPI:
    store = store or IndexStore(snapshot_directory())
    server = create_server(store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with server.session_manager.run():
            yield

    app = FastAPI(title="Knowledge MCP", lifespan=lifespan)
    configure_telemetry("zknowledge", app)

    @app.get("/health")
    async def health():
        index = store.open()
        try:
            return {"status": "ok", "snapshot": index.snapshot}
        finally:
            index.close()

    app.mount("/", server.streamable_http_app())
    return app


app = create_app()
