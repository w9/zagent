import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

import httpx
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from zagent.cohort import MAX_RESULT_ROWS, ClinicalStore, HandleError
from zagent.draft_store import DraftConflict, DraftStore
from zagent.drafts import AppId, DraftState
from zagent.job_tools import JOB_DESCRIPTIONS, JOB_INPUTS, JOB_OUTPUTS, JobsTools
from zagent.privacy import PrivacyError, Raw, Tokenized
from zagent.store import AgentSession, ConversationTurnConflict, NotFound, Store
from zagent.views import ViewSpec

MAX_TOOL_RESULT_BYTES = 8192
Handle = Annotated[str, Field(pattern=r"^query-[0-9]{4,}$", max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindPatients(StrictModel):
    mrn: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        json_schema_extra={"x-identifier": "PT"},
    )


class FindSpecimens(StrictModel):
    patient_handle: Handle | None = None
    received_within: Literal["P1D", "P7D", "P30D"] = "P1D"
    kind: Literal["tumor", "normal", "RNA"] | None = None
    identity: Literal["reported", "verified"] = "reported"


class FindLibraries(StrictModel):
    specimen_handle: Handle
    qc_status: Literal["passed", "review", "failed"] | None = None


class PushView(StrictModel):
    spec: ViewSpec


class UpdateDraft(StrictModel):
    draft_id: str | None = Field(default=None, pattern=r"^draft-[0-9]{4,}$")
    app_id: AppId | None = None
    specimen_handle: Handle | None = None
    parameters: dict[str, float | int | bool | str | None] = Field(
        default_factory=dict, max_length=20
    )


class DraftResult(StrictModel):
    ok: Literal[True] = True
    draft: DraftState
    view_id: str
    kind: Literal["draft_form"] = "draft_form"
    title: str


class Column(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=100)
    type: Literal["string", "number", "boolean"]


class QueryResult(StrictModel):
    handle: Handle
    count: int = Field(ge=0, le=MAX_RESULT_ROWS)
    columns: list[Column] = Field(alias="schema", min_length=1, max_length=30)


class ViewReceipt(StrictModel):
    ok: Literal[True]
    view_id: str = Field(pattern=r"^view-[0-9]{4,}$", max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)


class ErrorDetail(StrictModel):
    code: Literal[
        "unknown_tool",
        "invalid_arguments",
        "invalid_handle",
        "invalid_view",
        "unavailable",
        "unsafe_result",
    ]
    message: str = Field(min_length=1, max_length=500)


class ToolFailure(StrictModel):
    error: ErrorDetail


INPUTS = {
    "find_patients": FindPatients,
    "find_specimens": FindSpecimens,
    "find_libraries": FindLibraries,
    "push_view": PushView,
    "update_draft": UpdateDraft,
    **JOB_INPUTS,
}
DESCRIPTIONS = {
    **JOB_DESCRIPTIONS,
    "find_patients": (
        "Find patients by exact MRN, or all patients at this site. Returns a handle only."
    ),
    "find_specimens": (
        "Find specimens for a patient handle, optionally all patients, within P1D, P7D or P30D. "
        "P1D means the last 24 hours. Optional kind selects tumor, normal, or RNA specimens. "
        "identity=verified selects assay-verified specimen roles for a corrected identity draft; "
        "the default reported roles preserve the original manifest. "
        "Returns a handle, count and columns, never rows."
    ),
    "find_libraries": "Find libraries for a specimen handle, optionally filtered by QC status.",
    "push_view": (
        "Publish a table or chart in the working surface, with data bound to a query handle. "
        "Success returns a receipt identifying the published view: view_id, kind and title. "
        "Use the title and kind to refer to it in chat; let the view present the query results. "
        "No inline data. Table v1 props: title, handle, columns (copy the schema's complete "
        "key/label/type objects), row_count (from count). "
        "Chart v1 props: title, handle, mark (bar/line/point), encoding with x/y "
        "and optional color; "
        "each channel has field, type (nominal/ordinal/quantitative/temporal), optional aggregate "
        "(count/sum/mean/min/max). Use only columns from the handle schema."
    ),
    "update_draft": (
        "Create or edit a pending job draft, never submit it. New drafts require app_id; "
        "use specimen_handle from find_specimens. Existing drafts require draft_id; patch only "
        "the fields the user changes. Set a parameter to null to remove an incorrect parameter. "
        "specimen_handle is a top-level query handle, not a parameter or individual specimen ID. "
        "Somatic drafts need one query containing both tumor and normal specimens from the same "
        "patient: omit kind in find_specimens. There is no matched_normal parameter. "
        "Publishes a form automatically, returns version/hash and "
        "deterministic validation. Apps: readqc(min_coverage=30, check_identity=true); "
        "somatic-snv(min_vaf=0.05, min_depth=20); "
        "rna-fusion(min_support=5, filter_artifacts=true); "
        "germline-panel(panel=predisposition|extended, min_coverage=30). "
        "Missing/invalid fields stay in the draft for clarification. Only the human Confirm "
        "control can submit. Do not call push_view for the draft form."
    ),
}
RESPONSE_SCHEMAS = {
    name: TypeAdapter(
        (JOB_OUTPUTS[name] | ToolFailure)
        if name in JOB_OUTPUTS
        else (DraftResult | ToolFailure)
        if name == "update_draft"
        else (ViewReceipt | ToolFailure)
        if name == "push_view"
        else (QueryResult | ToolFailure)
    ).json_schema()
    for name in INPUTS
}
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": DESCRIPTIONS[name],
            "parameters": model.model_json_schema(),
        },
    }
    for name, model in INPUTS.items()
]
COLUMNS = {
    "patients": [
        {"key": "id", "label": "Patient", "type": "string"},
        {"key": "mrn", "label": "MRN", "type": "string"},
        {"key": "display_name", "label": "Name", "type": "string"},
    ],
    "specimens": [
        {"key": "id", "label": "Specimen", "type": "string"},
        {"key": "kind", "label": "Type", "type": "string"},
        {"key": "purity", "label": "Purity", "type": "number"},
        {"key": "received_at", "label": "Received", "type": "string"},
    ],
    "libraries": [
        {"key": "id", "label": "Library", "type": "string"},
        {"key": "specimen_id", "label": "Specimen", "type": "string"},
        {"key": "prep", "label": "Preparation", "type": "string"},
        {"key": "coverage", "label": "Coverage", "type": "number"},
        {"key": "qc_status", "label": "QC status", "type": "string"},
    ],
}


def failure(code: str, message: str) -> dict:
    return ToolFailure(error={"code": code, "message": message[:500]}).model_dump()


class ClinicalTools:
    def __init__(self, clinical: ClinicalStore):
        self.clinical = clinical

    async def dispatch(
        self,
        session_id: UUID,
        name: str,
        arguments: dict,
        *,
        conversation_turn_id: UUID | None = None,
        operation_id: str | None = None,
    ) -> dict:
        if operation_id is not None:

            async def execute_once():
                return await self.dispatch(
                    session_id, name, arguments, conversation_turn_id=conversation_turn_id
                )

            return await self.clinical.store.tool_operation(
                session_id, conversation_turn_id, operation_id, name, arguments, execute_once
            )
        try:
            resolved = await self.clinical.store.privacy.resolve(
                session_id,
                Tokenized(value=arguments),
                strict=True,
            )
            if conversation_turn_id is not None:
                await self.clinical.store.pool.execute(
                    """INSERT INTO privacy.execution_audit
                              (session_id, conversation_turn_id, tool, arguments)
                              VALUES ($1, $2, $3, $4)""",
                    session_id,
                    conversation_turn_id,
                    name,
                    resolved.value,
                )
            result = await self._dispatch(
                session_id,
                name,
                resolved.value,
                conversation_turn_id=conversation_turn_id,
            )
            return (
                await self.clinical.store.privacy.tokenize(
                    session_id,
                    Raw(value=result),
                    path="tool_result",
                    schema=RESPONSE_SCHEMAS.get(name),
                )
            ).value
        except PrivacyError:
            return failure("invalid_arguments", "Unknown or inaccessible identifier token")

    async def _dispatch(
        self,
        session_id: UUID,
        name: str,
        arguments: dict,
        *,
        conversation_turn_id: UUID | None = None,
    ) -> dict:
        if name not in INPUTS:
            return failure("unknown_tool", "Tool is not allowlisted")
        try:
            params = INPUTS[name].model_validate(arguments)
            session = await self.clinical.store.get_session(session_id)
            if name in JOB_INPUTS:
                return await JobsTools(self.clinical).dispatch(
                    session_id, conversation_turn_id, name, arguments
                )
            if name == "update_draft":
                if conversation_turn_id is None:
                    return failure("invalid_arguments", "Draft updates require an active turn")
                from zagent.drafts import CATALOG

                draft = await DraftStore(self.clinical).update(
                    session_id,
                    conversation_turn_id=conversation_turn_id,
                    **params.model_dump(),
                )
                return DraftResult(
                    draft=draft, view_id=draft.view_id, title=CATALOG[draft.app_id].title
                ).model_dump()
            if name == "push_view":
                if conversation_turn_id is None:
                    return failure("invalid_view", "Publishing a view requires a conversation turn")
                return await self.push_view(session_id, conversation_turn_id, params.spec)
            identifiers = None
            if name == "find_specimens" and params.patient_handle:
                identifiers = (
                    await self.clinical.resolve(session_id, params.patient_handle, "patients")
                )["row_ids"]
            if name == "find_libraries":
                identifiers = (
                    await self.clinical.resolve(session_id, params.specimen_handle, "specimens")
                )["row_ids"]
            async with self.clinical.site_connection(session.site_id) as connection:
                if name == "find_patients":
                    entity = "patients"
                    records = await connection.fetch(
                        """SELECT * FROM patients WHERE ($1::text IS NULL OR mrn = $1)
                           ORDER BY id LIMIT 201""",
                        params.mrn,
                    )
                elif name == "find_specimens":
                    entity = "specimens"
                    now = self.clinical.clock()
                    days = {"P1D": 1, "P7D": 7, "P30D": 30}[params.received_within]
                    records = await connection.fetch(
                        """SELECT * FROM specimens
                           WHERE ($1::text[] IS NULL OR patient_id = ANY($1))
                           AND received_at >= $2 AND received_at <= $3
                          AND ($4::text IS NULL OR
                              CASE WHEN $5='verified' THEN assayed_kind ELSE kind END = $4)
                           ORDER BY received_at DESC, id LIMIT 201""",
                        identifiers,
                        now - timedelta(days=days),
                        now,
                        params.kind,
                        params.identity,
                    )
                else:
                    entity = "libraries"
                    records = await connection.fetch(
                        """SELECT * FROM libraries WHERE specimen_id = ANY($1::text[])
                           AND ($2::text IS NULL OR qc_status = $2) ORDER BY id LIMIT 201""",
                        identifiers,
                        params.qc_status,
                    )
            records = [dict(record) for record in records]
            if name == "find_specimens" and params.identity == "verified":
                records = [{**record, "kind": record["assayed_kind"]} for record in records]
            return await self.clinical.save_handle(session_id, entity, COLUMNS[entity], records)
        except ValidationError:
            return failure("invalid_arguments", "Arguments do not match the tool schema")
        except (NotFound, HandleError) as error:
            return failure("invalid_handle", str(error))
        except ConversationTurnConflict as error:
            return failure("invalid_view", str(error))
        except (DraftConflict, ValueError):
            return failure(
                "invalid_arguments",
                "The draft cannot be updated; use an editable draft and catalog values",
            )

    async def push_view(self, session_id: UUID, conversation_turn_id: UUID, spec: ViewSpec) -> dict:
        if spec.kind not in {"table", "chart"}:
            return failure("invalid_view", "Workflow views are published by their owning operation")
        handle = spec.props.get("handle")
        if not handle or "rows" in spec.props:
            return failure("invalid_view", "Views must bind data by handle, never inline rows")
        resolved = await self.clinical.resolve(session_id, handle)
        columns = {column["key"]: column for column in resolved["columns"]}
        if spec.kind == "table":
            if spec.props["row_count"] != resolved["row_count"]:
                return failure("invalid_view", "row_count must match the query count")
            for column in spec.props["columns"]:
                if column["key"] not in columns or column["type"] != columns[column["key"]]["type"]:
                    return failure("invalid_view", "Table columns must match the handle schema")
        elif spec.kind == "chart":
            for channel in spec.props["encoding"].values():
                column = columns.get(channel["field"])
                if column is None:
                    return failure("invalid_view", "Chart fields must belong to the handle schema")
                if (
                    channel.get("aggregate") != "count"
                    and (
                        channel["type"] == "quantitative"
                        or channel.get("aggregate") in {"sum", "mean", "min", "max"}
                    )
                    and column["type"] != "number"
                ):
                    return failure("invalid_view", "Quantitative channels require numeric fields")
        event = await self.clinical.store.publish_view(session_id, conversation_turn_id, spec)
        return ViewReceipt(
            ok=True,
            view_id=event.payload["view_id"],
            kind=spec.kind,
            title=spec.props["title"],
        ).model_dump()


def create_mcp_server(clinical: ClinicalStore) -> FastMCP:
    backend = ClinicalTools(clinical)
    server = FastMCP("zagent-clinical", host="0.0.0.0", stateless_http=True, json_response=True)

    def register(name: str) -> None:
        async def invoke(
            session_id: str,
            conversation_turn_id: str,
            arguments: dict[str, Any],
            operation_id: str | None = None,
        ) -> dict[str, Any]:
            return await backend.dispatch(
                UUID(session_id),
                name,
                arguments,
                conversation_turn_id=UUID(conversation_turn_id),
                operation_id=operation_id,
            )

        server.add_tool(invoke, name=name, description=DESCRIPTIONS[name])

    for name in INPUTS:
        register(name)
    return server


class ToolCaller(Protocol):
    async def call(
        self, session: AgentSession, name: str, arguments: dict, *, operation_id: str | None = None
    ) -> dict: ...


class McpToolClient:
    def __init__(
        self, *, url: str | None = None, server: FastMCP | None = None, jobs_url: str | None = None
    ):
        if (url is None) == (server is None):
            raise ValueError("Provide either an MCP URL or an in-process MCP server")
        self.url = url
        self.server = server
        self.jobs_url = jobs_url

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[ClientSession]:
        if self.server is not None:
            async with create_connected_server_and_client_session(self.server) as client:
                yield client
        else:
            async with httpx.AsyncClient(timeout=30) as http:
                async with streamable_http_client(self.url, http_client=http) as (
                    reader,
                    writer,
                    _,
                ):
                    async with ClientSession(reader, writer) as client:
                        await client.initialize()
                        yield client

    async def call(
        self, session: AgentSession, name: str, arguments: dict, *, operation_id: str | None = None
    ) -> dict:
        if name in JOB_INPUTS and self.jobs_url:
            return await McpToolClient(url=self.jobs_url).call(
                session, name, arguments, operation_id=operation_id
            )
        async with self.connection() as client:
            result = await client.call_tool(
                name,
                {
                    "session_id": str(session.id),
                    "conversation_turn_id": str(session.conversation_turn_id),
                    "arguments": arguments,
                    "operation_id": operation_id,
                },
            )
        if result.isError or result.structuredContent is None:
            return failure("unavailable", "MCP tool execution failed")
        return result.structuredContent

    async def resource(self, uri: str) -> str:
        async with self.connection() as client:
            result = await client.read_resource(uri)
        if len(result.contents) != 1 or result.contents[0].mimeType != "text/html;profile=mcp-app":
            raise ValueError("Unsupported MCP app resource")
        return result.contents[0].text

    async def app_data(
        self, session_id: UUID, *, handle: str | None = None, job_id: str | None = None
    ) -> dict:
        arguments = {"session_id": str(session_id)}
        arguments.update({"handle": handle} if handle else {"job_id": job_id})
        async with self.connection() as client:
            result = await client.call_tool("read_jobs", arguments)
        if result.isError or result.structuredContent is None:
            raise ValueError("Published job data is unavailable or expired")
        return result.structuredContent


class ToolsGateway:
    def __init__(self, store: Store, client: ToolCaller):
        self.store = store
        self.client = client

    async def execute(
        self,
        session: AgentSession,
        name: str,
        raw_arguments: str,
        *,
        operation_id: str | None = None,
    ) -> dict:
        arguments: Any = {}
        try:
            if len(raw_arguments) > 16384:
                raise ValueError("Arguments exceed the size limit")
            arguments = json.loads(raw_arguments)
            model = INPUTS.get(name)
            if model is None:
                result = failure("unknown_tool", "Tool is not allowlisted")
            else:
                arguments = (
                    await self.store.privacy.tokenize(
                        session.id,
                        Raw(value=arguments),
                        path="tool_arguments",
                        schema=model.model_json_schema(),
                    )
                ).value
                params = model.model_validate(arguments)
                result = await self.client.call(
                    session,
                    name,
                    params.model_dump(mode="json", exclude_none=True),
                    **({"operation_id": operation_id} if operation_id else {}),
                )
                if len(
                    json.dumps(result).encode()
                ) > MAX_TOOL_RESULT_BYTES or not Draft202012Validator(
                    RESPONSE_SCHEMAS[name]
                ).is_valid(result):
                    result = failure(
                        "unsafe_result", "Tool returned an invalid or oversized result"
                    )
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}"
                for issue in error.errors(include_input=False, include_url=False)
            )
            result = failure("invalid_arguments", details)
        except (ValueError, TypeError):
            arguments = {}
            result = failure("invalid_arguments", "Arguments must be a bounded JSON object")
        except Exception:
            result = failure("unavailable", "Tool service is unavailable")
        result = (
            await self.store.privacy.tokenize(
                session.id,
                Raw(value=result),
                path="tool_result",
                schema=RESPONSE_SCHEMAS.get(name),
            )
        ).value
        await self.store.pool.execute(
            """INSERT INTO tool_audit (session_id, conversation_turn_id, tool, arguments, result)
               VALUES ($1, $2, $3, $4, $5)""",
            session.id,
            session.conversation_turn_id,
            name,
            arguments,
            result,
        )
        return result
