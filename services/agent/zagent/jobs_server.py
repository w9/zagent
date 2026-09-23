import os
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from zagent.cohort import ClinicalStore, configured_clock
from zagent.job_tools import JOB_DESCRIPTIONS, JOB_INPUTS, JobsTools
from zagent.jobs import JobStore
from zagent.store import DEFAULT_DATABASE_URL, Store

UI_RESOURCES = {"job_card": "ui://jobs/card", "job_grid": "ui://jobs/grid"}


def create_jobs_server(clinical: ClinicalStore) -> FastMCP:
    server = FastMCP("zagent-jobs", host="0.0.0.0", stateless_http=True, json_response=True)
    backend = JobsTools(clinical)

    def register(name):
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict,
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            async def execute_once():
                return await backend.dispatch(
                    UUID(session_id), UUID(conversation_turn_id), name, arguments
                )

            if operation_id:
                return await clinical.store.tool_operation(
                    UUID(session_id),
                    UUID(conversation_turn_id),
                    operation_id,
                    name,
                    arguments,
                    execute_once,
                )
            return await execute_once()

        server.add_tool(
            invoke,
            name=name,
            description=JOB_DESCRIPTIONS[name],
            annotations=ToolAnnotations(readOnlyHint=name != "show_jobs", destructiveHint=False),
            meta={"ui": {"resourceUri": "ui://jobs/grid"}} if name == "show_jobs" else None,
        )

    for name in JOB_INPUTS:
        register(name)

    @server.tool(
        name="read_jobs",
        annotations=ToolAnnotations(readOnlyHint=True),
        meta={"ui": {"resourceUri": "ui://jobs/grid", "visibility": ["app"]}},
    )
    async def read_jobs(
        session_id: str, handle: str | None = None, job_id: str | None = None
    ) -> dict[str, Any]:
        if bool(handle) == bool(job_id):
            raise ValueError("Exactly one published job binding is required")
        jobs = JobStore(clinical)
        return (
            await jobs.read_handle(UUID(session_id), handle)
            if handle
            else {"jobs": [await jobs.read(UUID(session_id), job_id)]}
        )

    for uri in UI_RESOURCES.values():

        def resource() -> str:
            return files("zagent").joinpath("resources/jobs.html").read_text()

        server.resource(
            uri,
            mime_type="text/html;profile=mcp-app",
            meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}},
        )(resource)
    return server


def create_jobs_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = await Store.open(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
        try:
            server = create_jobs_server(ClinicalStore(store, configured_clock()))
            app.mount("/", server.streamable_http_app())
            app.state.store = store
            async with server.session_manager.run():
                yield
        finally:
            await store.close()

    app = FastAPI(title="Zagent jobs MCP", lifespan=lifespan)

    @app.get("/health")
    async def health():
        await app.state.store.pool.fetchval("SELECT 1")
        return {"status": "ok"}

    return app


app = create_jobs_app()
