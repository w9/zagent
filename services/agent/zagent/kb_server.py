from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from zagent.job_tools import JOB_DESCRIPTIONS, ReadDocument, SearchKnowledge
from zagent.knowledge import KnowledgeBase


def create_kb_server() -> FastMCP:
    server = FastMCP("zagent-knowledge", host="0.0.0.0", stateless_http=True, json_response=True)

    def register(name, schema):
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict[str, Any],
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            params = schema.model_validate(arguments)
            knowledge = KnowledgeBase()
            try:
                return (
                    knowledge.search(params.query)
                    if name == "search_knowledge"
                    else knowledge.read(
                        params.document, params.start_line, params.end_line, params.version
                    )
                )
            finally:
                knowledge.close()

        server.add_tool(
            invoke,
            name=name,
            description=JOB_DESCRIPTIONS[name],
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
        )

    register("search_knowledge", SearchKnowledge)
    register("read_document", ReadDocument)
    return server


def create_kb_app() -> FastAPI:
    server = create_kb_server()

    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():
            yield

    app = FastAPI(title="Zagent immutable knowledge MCP", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-kb", app)

    @app.get("/health")
    async def health():
        knowledge = KnowledgeBase()
        try:
            return {"status": "ok", "version": knowledge.version}
        finally:
            knowledge.close()

    app.mount("/", server.streamable_http_app())
    return app


app = create_kb_app()
