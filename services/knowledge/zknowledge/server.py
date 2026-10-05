from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from zknowledge.snapshot import Snapshot, SnapshotStore, SnapshotUnavailable

SNAPSHOT_META = "zknowledge/snapshot"
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def failure(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message[:500]}}


def create_server(snapshots: SnapshotStore) -> FastMCP:
    server = FastMCP("zknowledge", host="0.0.0.0", stateless_http=True, json_response=True)

    @contextmanager
    def requested(context: Context) -> Iterator[Snapshot]:
        meta = context.request_context.meta
        pinned = (meta.model_extra or {}).get(SNAPSHOT_META) if meta else None
        snapshot = snapshots.open(pinned if isinstance(pinned, str) else None)
        try:
            yield snapshot
        finally:
            snapshot.close()

    def guarded(action) -> dict[str, Any]:
        try:
            return action()
        except SnapshotUnavailable as error:
            return failure("unavailable", str(error))
        except ValueError as error:
            return failure("invalid_arguments", str(error))

    @server.tool(
        name="search_knowledge",
        description="Search published knowledge. Returns line matches and the snapshot version.",
        annotations=READ_ONLY,
    )
    def search_knowledge(
        query: Annotated[str, Field(min_length=1, max_length=200)], ctx: Context
    ) -> dict[str, Any]:
        def action():
            with requested(ctx) as snapshot:
                return snapshot.search(query)

        return guarded(action)

    @server.tool(
        name="read_document",
        description="Read at most 30 lines of a document from the snapshot named by version.",
        annotations=READ_ONLY,
    )
    def read_document(
        document: Annotated[str, Field(pattern=r"^[a-z0-9-]+$", max_length=100)],
        start_line: Annotated[int, Field(ge=1)],
        end_line: Annotated[int, Field(ge=1)],
        version: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")],
        ctx: Context,
    ) -> dict[str, Any]:
        def action():
            with requested(ctx) as snapshot:
                return snapshot.read(document, start_line, end_line, version)

        return guarded(action)

    return server
