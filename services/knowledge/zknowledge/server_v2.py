from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from zknowledge.index import Caller, IndexStore, NotFound
from zknowledge.server import READ_ONLY, SNAPSHOT_META, failure
from zknowledge.snapshot import SnapshotUnavailable

CALLER_META = "zknowledge/caller"
DocumentId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)]
Source = Literal["qms", "wiki", "ticketing", "reference", "wikipedia"]


def create_server_v2(store: IndexStore) -> FastMCP:
    server = FastMCP("zknowledge-v2", host="0.0.0.0", stateless_http=True, json_response=True)

    def run(context: Context, action) -> dict[str, Any]:
        meta = context.request_context.meta
        extra = (meta.model_extra or {}) if meta else {}
        pinned = extra.get(SNAPSHOT_META)
        claims = extra.get(CALLER_META) if isinstance(extra.get(CALLER_META), dict) else {}
        site = claims.get("site") if isinstance(claims.get("site"), str) else None
        roles = [role for role in claims.get("roles", []) if isinstance(role, str)]
        try:
            index = store.open(pinned if isinstance(pinned, str) else None)
        except SnapshotUnavailable as error:
            return failure("unavailable", str(error))
        try:
            return action(index, Caller(site, roles))
        except NotFound as error:
            return failure("not_found", str(error))
        except ValueError as error:
            return failure("invalid_arguments", str(error))
        finally:
            index.close()

    @server.tool(
        name="search_knowledge",
        description=(
            "Search published knowledge at passage level with synonym expansion. Inactive "
            "(draft, superseded, retired, archived) documents are excluded unless requested."
        ),
        annotations=READ_ONLY,
    )
    def search_knowledge(
        query: Annotated[str, Field(min_length=1, max_length=200)],
        ctx: Context,
        sources: Annotated[list[Source] | None, Field(max_length=5)] = None,
        doc_types: Annotated[list[str] | None, Field(max_length=10)] = None,
        applies_to: Annotated[str | None, Field(max_length=40)] = None,
        include_inactive: bool = False,
        limit: Annotated[int, Field(ge=1, le=8)] = 5,
    ) -> dict[str, Any]:
        return run(
            ctx,
            lambda index, caller: index.search(
                caller,
                query,
                sources=sources,
                doc_types=doc_types,
                applies_to=applies_to,
                include_inactive=include_inactive,
                limit=limit,
            ),
        )

    @server.tool(
        name="get_document",
        description="Document metadata, visible versions and a section outline with line ranges.",
        annotations=READ_ONLY,
    )
    def get_document(document: DocumentId, ctx: Context) -> dict[str, Any]:
        return run(ctx, lambda index, caller: index.get_document(caller, document))

    @server.tool(
        name="read_document",
        description="Read one outline section or a line range: at most 30 lines.",
        annotations=READ_ONLY,
    )
    def read_document(
        document: DocumentId,
        ctx: Context,
        section: Annotated[str | None, Field(pattern=r"^[0-9]+(?:\.[0-9]+)*$")] = None,
        start_line: Annotated[int | None, Field(ge=1)] = None,
        end_line: Annotated[int | None, Field(ge=1)] = None,
    ) -> dict[str, Any]:
        return run(
            ctx,
            lambda index, caller: index.read_document(
                caller, document, section=section, start_line=start_line, end_line=end_line
            ),
        )

    @server.tool(
        name="lookup_term",
        description="Glossary definition, synonyms and the cited source of a term.",
        annotations=READ_ONLY,
    )
    def lookup_term(
        term: Annotated[str, Field(min_length=1, max_length=80)], ctx: Context
    ) -> dict[str, Any]:
        return run(ctx, lambda index, caller: index.lookup_term(caller, term))

    @server.tool(
        name="query_reference",
        description="Rows of one reference table filtered by exact column values, with sources.",
        annotations=READ_ONLY,
    )
    def query_reference(
        table: Annotated[str, Field(pattern=r"^[a-z_]+$", max_length=40)],
        ctx: Context,
        filters: Annotated[dict[str, str | int | float | bool] | None, Field(max_length=6)] = None,
        limit: Annotated[int, Field(ge=1, le=25)] = 10,
    ) -> dict[str, Any]:
        return run(ctx, lambda index, caller: index.query_reference(caller, table, filters, limit))

    return server
