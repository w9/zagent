import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator


def load_schemas() -> dict[tuple[str, int], Draft202012Validator]:
    schemas = {}
    for path in files("zagent").joinpath("artifact_schemas").iterdir():
        if path.name.endswith(".json"):
            schema = json.loads(path.read_text())
            Draft202012Validator.check_schema(schema)
            identity = (
                schema["properties"]["kind"]["const"],
                schema["properties"]["version"]["const"],
            )
            if identity in schemas:
                raise ValueError(f"Duplicate artifact schema: {identity}")
            schemas[identity] = Draft202012Validator(schema)
    return schemas


ARTIFACT_SCHEMAS = load_schemas()


# Validation messages still say "View schema error": push_view failures return them to the
# model, so changing them would change recorded model requests.
class ArtifactSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    version: int = Field(strict=True, ge=1)
    props: dict[str, Any]

    @model_validator(mode="after")
    def validate_schema(self) -> "ArtifactSpec":
        validator = ARTIFACT_SCHEMAS.get((self.kind, self.version))
        if validator is None:
            raise ValueError(f"View schema error: unsupported {self.kind} v{self.version}")
        error = next(validator.iter_errors(self.model_dump()), None)
        if error:
            location = ".".join(str(part) for part in error.absolute_path) or "spec"
            raise ValueError(f"View schema error at {location}: {error.message}")
        if self.kind == "table":
            validate_table(self.props)
        return self


def validate_table(props: dict[str, Any]) -> None:
    columns = props["columns"]
    keys = [column["key"] for column in columns]
    if len(set(keys)) != len(keys):
        raise ValueError("View schema error: table column keys must be unique")
    rows = props.get("rows", [])
    if props["row_count"] < len(rows):
        raise ValueError("View schema error: row_count is smaller than the supplied rows")
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("View schema error: each row must match the number of columns")
        for cell, column in zip(row, columns, strict=True):
            if cell is None:
                continue
            valid = {
                "string": isinstance(cell, str),
                "number": type(cell) in (int, float),
                "boolean": isinstance(cell, bool),
            }[column["type"]]
            if not valid:
                raise ValueError(f"View schema error: cell does not match column {column['key']}")


class ArtifactPublished(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    spec: ArtifactSpec
