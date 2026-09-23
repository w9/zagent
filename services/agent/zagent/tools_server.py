import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from zagent.cohort import ClinicalStore, configured_clock
from zagent.store import DEFAULT_DATABASE_URL, Store
from zagent.tools import create_mcp_server


def create_tools_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = await Store.open(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        simulator = None
        try:
            await store.migrate()
            clinical = ClinicalStore(store, configured_clock())
            await clinical.seed()
            server = create_mcp_server(clinical)
            app.mount("/", server.streamable_http_app())
            app.state.store = store
            if os.environ.get("ZAGENT_LLM_MODE", "replay") != "replay" and not os.environ.get(
                "ZAGENT_FROZEN_TIME"
            ):
                simulator = asyncio.create_task(clinical.simulate(), name="cohort-simulator")
            async with server.session_manager.run():
                yield
        finally:
            if simulator is not None:
                simulator.cancel()
                await asyncio.gather(simulator, return_exceptions=True)
            await store.close()

    app = FastAPI(title="Zagent clinical MCP tools", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-tools", app)

    @app.get("/health")
    async def health():
        await app.state.store.pool.fetchval("SELECT 1")
        return {"status": "ok"}

    return app


app = create_tools_app()
