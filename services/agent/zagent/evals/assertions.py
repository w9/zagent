import json
from collections.abc import Callable
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any, get_args

from zagent.evals.schema import Case, fixture_path
from zagent.events import Event, EventType, Projection, normalize_transcript


@dataclass
class Evidence:
    events: list[Event]
    projection: Projection


def normalized_evidence(evidence: Evidence) -> dict[str, Any]:
    return {
        "events": normalize_transcript(evidence.events),
        "messages": [
            message.model_dump(exclude={"id"}) for message in evidence.projection.messages
        ],
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


def check_case(
    case: Case, evidence: Evidence, root: Path, *, skip_golden: bool = False
) -> list[str]:
    validate_expectations(case, root)
    failures = []
    for name, expected in case.expect.items():
        if name == "golden" and skip_golden:
            continue
        failure = ASSERTIONS[name](evidence, expected, root, case.id)
        if failure:
            failures.append(failure)
    return failures
