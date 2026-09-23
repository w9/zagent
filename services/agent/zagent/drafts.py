import hashlib
import json
from importlib.resources import files
from typing import Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field

AppId = Literal["readqc", "somatic-snv", "rna-fusion", "germline-panel"]


class CatalogApp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: AppId
    title: str
    parameters: dict[str, Any]
    layout: list[str]
    required_prep: str | None = None
    execution_image: str = "zagent-job:plan8"
    execution_command: list[str] = Field(
        default_factory=lambda: ["python", "-m", "zagent.job_worker"]
    )


def load_catalog() -> dict[str, CatalogApp]:
    data = json.loads(files("zagent").joinpath("catalog.json").read_text())
    catalog = {}
    allowed = {"type", "title", "description", "default", "minimum", "maximum", "enum"}
    for source in data:
        app = CatalogApp.model_validate(source)
        Draft202012Validator.check_schema(app.parameters)
        schema = app.parameters
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError("Application parameters must be a closed object")
        if schema.keys() - {"type", "additionalProperties", "properties", "required"}:
            raise ValueError("Unsupported generated-form schema")
        properties = schema["properties"]
        if set(app.layout) != set(properties) or len(app.layout) != len(properties):
            raise ValueError("Application layout must name each parameter once")
        for field in properties.values():
            if field.keys() - allowed or field.get("type") not in {
                "number",
                "integer",
                "boolean",
                "string",
            }:
                raise ValueError("Unsupported generated-form schema")
            if "enum" in field and (
                field["type"] != "string"
                or not all(isinstance(item, str) for item in field["enum"])
            ):
                raise ValueError("Generated-form enums must contain strings")
            if "default" in field:
                Draft202012Validator(field).validate(field["default"])
        if app.id in catalog:
            raise ValueError("Duplicate application ID")
        catalog[app.id] = app
    return catalog


CATALOG = load_catalog()


class DraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    app_id: AppId
    specimen_handle: str | None = Field(default=None, pattern=r"^query-[0-9]{4,}$")
    parameters: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=20)


class DraftIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    field: str
    message: str


class DraftState(DraftContent):
    draft_id: str = Field(pattern=r"^draft-[0-9]{4,}$")
    view_id: str = Field(pattern=r"^view-[0-9]{4,}$")
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["editing", "submitted"] = "editing"
    validation: list[DraftIssue] = Field(default_factory=list, max_length=30)
    job_id: str | None = None


class JobState(DraftContent):
    job_id: str = Field(pattern=r"^job-[0-9]{4,}$")
    draft_id: str
    confirmed_version: int
    content_hash: str
    status: Literal["pending"] = "pending"


def default_parameters(app_id: AppId) -> dict[str, Any]:
    return {
        key: schema["default"]
        for key, schema in CATALOG[app_id].parameters["properties"].items()
        if "default" in schema
    }


def content_hash(content: DraftContent) -> str:
    value = content.model_dump()
    value["parameters"] = {
        key: int(item) if isinstance(item, float) and item.is_integer() else item
        for key, item in value["parameters"].items()
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def validate_draft(
    content: DraftContent, specimens: list[dict], libraries: list[dict]
) -> list[DraftIssue]:
    issues = []

    def issue(code: str, field: str, message: str) -> None:
        issues.append(DraftIssue(code=code, field=field, message=message))

    app = CATALOG[content.app_id]
    for error in Draft202012Validator(app.parameters).iter_errors(content.parameters):
        field = ".".join(["parameters", *(str(part) for part in error.path)])
        message = f"Parameter does not satisfy {error.validator} constraint."
        if error.validator == "additionalProperties":
            unknown = sorted(content.parameters.keys() - app.parameters["properties"].keys())
            message = "Remove unsupported parameter(s): " + ", ".join(unknown)[:200] + "."
        issue("invalid_parameter", field, message)
    if not content.specimen_handle:
        issue(
            "missing_selection", "specimen_handle", "Select a specimen query before confirmation."
        )
    elif not specimens:
        issue("empty_selection", "specimen_handle", "The selected query contains no specimens.")
    elif content.app_id == "somatic-snv":
        patients = {record["patient_id"] for record in specimens}
        if len(patients) != 1:
            issue(
                "patient_mismatch",
                "specimen_handle",
                "Somatic calling requires one patient's specimens.",
            )
        kinds = {record["kind"] for record in specimens}
        if "tumor" not in kinds:
            issue("missing_tumor", "specimen_handle", "Select a tumor specimen.")
        if "normal" not in kinds:
            issue(
                "missing_matched_normal", "specimen_handle", "A matched normal specimen is missing."
            )
    elif content.app_id == "rna-fusion" and (
        any(record["kind"] != "RNA" for record in specimens)
        or any(record["prep"] != "RNA-seq" for record in libraries)
    ):
        issue(
            "rna_only",
            "specimen_handle",
            "RNA fusion requires RNA specimens and RNA-seq libraries.",
        )
    if specimens and content.app_id in {"rna-fusion", "germline-panel"}:
        if {record["id"] for record in specimens} - {record["specimen_id"] for record in libraries}:
            issue(
                "missing_library",
                "specimen_handle",
                "Every selected specimen needs a prepared library.",
            )
    if specimens and content.app_id == "germline-panel":
        if any(record["prep"] != app.required_prep for record in libraries):
            issue(
                "incompatible_prep",
                "specimen_handle",
                "Library preparation is incompatible with this panel.",
            )
    return issues


def draft_changes(previous: DraftContent, current: DraftContent) -> list[dict]:
    before = {
        "app_id": previous.app_id,
        "specimen_handle": previous.specimen_handle,
        **{f"parameters.{key}": value for key, value in previous.parameters.items()},
    }
    after = {
        "app_id": current.app_id,
        "specimen_handle": current.specimen_handle,
        **{f"parameters.{key}": value for key, value in current.parameters.items()},
    }
    return [
        {"field": key, "before": before.get(key), "after": after.get(key)}
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    ]
