import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any, get_args

from jsonschema import Draft202012Validator
from pydantic import Field, TypeAdapter, ValidationError

from zagent.evals.schema import Case, StrictModel, fixture_path
from zagent.events import Event, EventType, Projection, normalize_transcript, reduce_event
from zagent.tools import RESPONSE_SCHEMAS
from zagent.views import ViewPushed


@dataclass
class Evidence:
    events: list[Event]
    projection: Projection


def normalized_evidence(evidence: Evidence) -> dict[str, Any]:
    steps = []
    for step in evidence.projection.steps:
        normalized = step.model_dump(exclude={"id", "seq", "tools"})
        if step.tools:
            normalized["tools"] = [tool.model_dump(exclude={"call_id"}) for tool in step.tools]
        steps.append(normalized)
    return {
        "events": normalize_transcript(evidence.events),
        "messages": [
            message.model_dump(exclude={"id", "seq"}) for message in evidence.projection.messages
        ],
        "views": [view.spec.model_dump() for view in evidence.projection.views],
        "steps": steps,
        "conversation_turn": (
            evidence.projection.conversation_turn.model_dump(exclude={"id"})
            if evidence.projection.conversation_turn
            else None
        ),
    }


def render_transcript(evidence: Evidence) -> str:
    return (
        json.dumps(normalized_evidence(evidence), indent=2, sort_keys=True, ensure_ascii=True)
        + "\n"
    )


def transcript_diff(case_id: str, expected: str, actual: str, label: str = "golden") -> str:
    return "".join(
        unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"{case_id}/{label}",
            tofile=f"{case_id}/actual",
        )
    )


Assertion = Callable[[Evidence, Any, Path, str], str | None]
ASSERTIONS: dict[str, Assertion] = {}


def assertion(name: str):
    def register(function: Assertion) -> Assertion:
        if name in ASSERTIONS:
            raise ValueError(f"Assertion already registered: {name}")
        ASSERTIONS[name] = function
        return function

    return register


@assertion("golden")
def golden(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    if not isinstance(expected, str):
        raise ValueError(f"{case_id}: golden must name a file")
    path = fixture_path(root, expected)
    if not path.is_file():
        return f"{case_id}: missing golden {expected}; use --update-golden and review the diff"
    return transcript_diff(case_id, path.read_text(), render_transcript(evidence)) or None


@assertion("events_include")
def events_include(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    present = {event.type for event in evidence.events}
    missing = set(expected) - present
    return f"{case_id}: missing events {sorted(missing)}" if missing else None


@assertion("events_exclude")
def events_exclude(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    found = {event.type for event in evidence.events} & set(expected)
    return f"{case_id}: forbidden events {sorted(found)}" if found else None


class ViewExpectation(StrictModel):
    kind: str = Field(min_length=1)
    version: int | None = Field(default=None, strict=True, ge=1)
    props_match: dict[str, Any] = Field(default_factory=dict)


VIEW_EXPECTATIONS = TypeAdapter(list[ViewExpectation])


@assertion("views")
def views(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    remaining = iter(evidence.projection.views)
    for expectation in VIEW_EXPECTATIONS.validate_python(expected):
        for view in remaining:
            spec = view.spec
            if spec.kind != expectation.kind:
                continue
            if expectation.version is not None and spec.version != expectation.version:
                continue
            matched = True
            for key, value in expectation.props_match.items():
                actual = spec.props.get(key)
                if isinstance(value, str) and value.startswith("~"):
                    matched = isinstance(actual, str) and re.search(value[1:], actual) is not None
                else:
                    matched = actual == value
                if not matched:
                    break
            if matched:
                break
        else:
            return f"{case_id}: missing ordered view matching {expectation.model_dump()}"
    return None


@assertion("view_stack_depth")
def view_stack_depth(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    actual = len(evidence.projection.views)
    return (
        f"{case_id}: expected view stack depth {expected}, received {actual}"
        if actual != expected
        else None
    )


@assertion("tools_only_handles")
def tools_only_handles(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    if not expected:
        return None
    results = [event for event in evidence.events if event.type == "tool_result"]
    if not results:
        return f"{case_id}: no tool results to verify"
    for event in results:
        schema = RESPONSE_SCHEMAS.get(event.payload["name"])
        if schema is None or not Draft202012Validator(schema).is_valid(event.payload["result"]):
            return f"{case_id}: REQ-TOOL-01 invalid tool result at seq {event.seq}"
    if any("handle" not in view.spec.props for view in evidence.projection.views):
        return f"{case_id}: REQ-TOOL-01 a view used inline data"
    return None


@assertion("numeric_claims_grounded")
def numeric_claims_grounded(
    evidence: Evidence, expected: Any, root: Path, case_id: str
) -> str | None:
    if not expected:
        return None
    counts: dict[str, set[int]] = {"patient": set(), "specimen": set(), "librar": set()}
    texts: dict[str, str] = {}
    names = {"find_patients": "patient", "find_specimens": "specimen", "find_libraries": "librar"}
    pattern = re.compile(
        r"\b(\d+)\**\s+(patients?|specimens?|librar(?:y|ies)|records?)\b", re.IGNORECASE
    )
    for event in evidence.events:
        payload = event.payload
        if event.type == "tool_result" and payload["name"] in names:
            if type(payload["result"].get("count")) is int:
                counts[names[payload["name"]]].add(payload["result"]["count"])
        elif event.type == "text_delta":
            message_id = payload["message_id"]
            texts[message_id] = texts.get(message_id, "") + payload["text"]
        elif event.type == "message_done":
            for number, noun in pattern.findall(texts.get(payload["message_id"], "")):
                entity = next((name for name in counts if noun.lower().startswith(name)), None)
                support = counts[entity] if entity else set().union(*counts.values())
                if int(number) not in support:
                    return f"{case_id}: REQ-GROUND-01 unsupported claim: {number} {noun}"
    return None


@assertion("references_resolve")
def references_resolve(evidence: Evidence, expected: Any, root: Path, case_id: str) -> str | None:
    if not expected:
        return None
    specimen_handle = None
    resolved = False
    for event in evidence.events:
        payload = event.payload
        if event.type == "tool_result" and payload["name"] == "find_specimens":
            specimen_handle = payload["result"].get("handle", specimen_handle)
        elif event.type == "tool_call" and payload["name"] == "find_libraries":
            arguments = json.loads(payload["arguments"])
            if specimen_handle is None or arguments.get("specimen_handle") != specimen_handle:
                return f"{case_id}: REQ-CTX-01 follow-up did not reference the specimen handle"
            resolved = True
    return None if resolved else f"{case_id}: REQ-CTX-01 no library follow-up was exercised"


def view_invariants(evidence: Evidence, case_id: str) -> list[str]:
    replayed = Projection(session_id=evidence.projection.session_id)
    expected = []
    identities = set()
    for event in evidence.events:
        if event.type == "view_pushed":
            try:
                pushed = ViewPushed.model_validate(event.payload)
            except ValidationError as error:
                return [f"{case_id}: REQ-VIEW-01 invalid view at seq {event.seq}: {error}"]
            if pushed.view_id not in identities:
                identities.add(pushed.view_id)
                expected.append(
                    {"id": pushed.view_id, "seq": event.seq, "spec": pushed.spec.model_dump()}
                )
        replayed = reduce_event(replayed, event)
        if [view.model_dump() for view in replayed.views] != expected:
            return [f"{case_id}: REQ-VIEW-02 view stack differs at prefix {event.seq}"]
    if [view.model_dump() for view in evidence.projection.views] != expected:
        return [f"{case_id}: REQ-VIEW-02 final view stack differs from the log"]
    return []


def validate_expectations(case: Case, root: Path) -> None:
    unknown = case.expect.keys() - ASSERTIONS.keys()
    if unknown:
        raise ValueError(f"{case.id}: unknown assertions {sorted(unknown)}")
    if "golden" not in case.expect or not isinstance(case.expect["golden"], str):
        raise ValueError(f"{case.id}: a golden transcript path is required")
    fixture_path(root, case.expect["golden"])
    for name in ("events_include", "events_exclude"):
        if name in case.expect and (
            not isinstance(case.expect[name], list)
            or any(not isinstance(item, str) for item in case.expect[name])
        ):
            raise ValueError(f"{case.id}: {name} must be a list of event types")
        unknown_events = set(case.expect.get(name, [])) - set(get_args(EventType))
        if unknown_events:
            raise ValueError(f"{case.id}: unknown event types {sorted(unknown_events)}")
    if "views" in case.expect:
        for expectation in VIEW_EXPECTATIONS.validate_python(case.expect["views"]):
            for value in expectation.props_match.values():
                if isinstance(value, str) and value.startswith("~"):
                    try:
                        re.compile(value[1:])
                    except re.error as error:
                        raise ValueError(
                            f"{case.id}: invalid view match pattern: {error}"
                        ) from error
    if "view_stack_depth" in case.expect:
        depth = case.expect["view_stack_depth"]
        if type(depth) is not int or depth < 0:
            raise ValueError(f"{case.id}: view_stack_depth must be a nonnegative integer")
    for name in ("tools_only_handles", "numeric_claims_grounded", "references_resolve"):
        if name in case.expect and type(case.expect[name]) is not bool:
            raise ValueError(f"{case.id}: {name} must be a boolean")


def check_case(
    case: Case, evidence: Evidence, root: Path, *, skip_golden: bool = False
) -> list[str]:
    validate_expectations(case, root)
    failures = view_invariants(evidence, case.id)
    for name, expected in case.expect.items():
        if name == "golden" and skip_golden:
            continue
        failure = ASSERTIONS[name](evidence, expected, root, case.id)
        if failure:
            failures.append(failure)
    return failures
