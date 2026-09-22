import hashlib
import json
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from zagent.cohort import FROZEN_NOW, generate_cohort
from zagent.events import Event
from zagent.gateway import configured_gateway
from zagent.llm import AssistantMessage
from zagent.privacy import Detector, EgressTripwire, Identifier, Raw, SessionTokens

EVAL_TRIPWIRE_KEY = hashlib.sha256(b"synthetic-evaluation-key-not-for-production").digest()


@lru_cache(maxsize=1)
def fixture_identifiers() -> tuple[Identifier, ...]:
    cohort = generate_cohort(FROZEN_NOW)
    identifiers = []
    for patient in cohort["patients"]:
        identifiers.extend(Identifier(value=patient[key]) for key in ("id", "mrn", "display_name"))
    for entity, kind in (("specimens", "SP"), ("libraries", "LB")):
        identifiers.extend(Identifier(value=record["id"], kind=kind) for record in cohort[entity])
    return tuple(identifiers)


def fixture_tripwire() -> EgressTripwire:
    return EgressTripwire(
        EVAL_TRIPWIRE_KEY, EgressTripwire.manifest(EVAL_TRIPWIRE_KEY, fixture_identifiers())
    )


class FixturePrivacy:
    def __init__(self):
        self.detector = Detector(fixture_identifiers())
        self.sessions: dict[str, SessionTokens] = {}

    def protect_events(self, events: list[Event]) -> list[Event]:
        protected = []
        for event in events:
            vault = self.sessions.setdefault(str(event.session_id), SessionTokens(self.detector))
            payload = vault.tokenize(Raw(value=event.payload), path="assistant_output").value
            protected.append(event.model_copy(update={"payload": payload}))
        return protected

    async def protect_response(self, request, completion):
        vault = self.sessions[request.metadata["session_id"]]
        message = vault.tokenize(
            Raw(value=completion.message.as_message()), path="assistant_output"
        )
        return completion.model_copy(
            update={"message": AssistantMessage.model_validate(message.value)}
        )


def private_gateway(mode: str, privacy, *, record_missing: bool = False):
    async def protect_response(request, completion):
        value = await privacy.tokenize(
            UUID(request.metadata["session_id"]),
            Raw(value=completion.message.as_message()),
            path="assistant_output",
        )
        return completion.model_copy(
            update={"message": AssistantMessage.model_validate(value.value)}
        )

    gateway = configured_gateway(
        mode, egress_check=fixture_tripwire(), protect_response=protect_response
    )
    gateway.record_missing = record_missing
    return gateway


def evaluate_detector(case, root: Path, *, seed: int, commit: str | None, dirty: bool | None):
    from zagent.evals.assertions import Evidence, check_case, render_transcript
    from zagent.evals.schema import Provenance, TrialResult
    from zagent.evals.scope import case_events
    from zagent.events import project

    started, clock = time.perf_counter(), datetime.now(UTC)
    privacy = FixturePrivacy()
    events = privacy.protect_events(case_events(case))
    evidence = Evidence(
        events,
        project(events[0].session_id, events),
        bindings=[
            item.model_dump() for item in privacy.sessions[str(events[0].session_id)].bindings
        ],
    )
    failures = check_case(case, evidence, root)
    return TrialResult(
        case_id=case.id,
        verification="standard",
        seed=seed,
        passed=not failures,
        failures=failures,
        transcript=render_transcript(evidence),
        session_id=str(events[0].session_id),
        duration_seconds=time.perf_counter() - started,
        executions=0,
        provenance=Provenance(
            commit=commit,
            dirty_worktree=dirty,
            agent_implementation="Detector",
            seed=seed,
            clock=clock,
        ),
    )


async def scan_privacy_corpus(root: Path, cassette_dir: Path, database_url: str):
    from zagent.evals.schema import PrivacyScan
    from zagent.store import Store

    detector = Detector(fixture_identifiers())
    result = PrivacyScan()
    for directory, attribute in ((cassette_dir, "cassettes"), (root / "goldens", "goldens")):
        for path in sorted(directory.glob("*.json")):
            setattr(result, attribute, getattr(result, attribute) + 1)
            if detector.contains(json.loads(path.read_text())):
                result.violations.append(f"{attribute}:{path.name}")
    audit_path = configured_gateway().audit_path
    if audit_path is not None and audit_path.exists():
        with sqlite3.connect(audit_path) as connection:
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'model_requests'"
            ).fetchone()
            if exists:
                for identity, body in connection.execute(
                    "SELECT request_id, body FROM model_requests"
                ):
                    result.recorded_requests += 1
                    if detector.contains(json.loads(body)):
                        result.violations.append(f"model_request:{identity}")
    store = await Store.open(database_url)
    try:
        async with store.pool.acquire() as connection, connection.transaction():
            async for row in connection.cursor("SELECT session_id, seq, payload FROM events"):
                result.stored_events += 1
                if detector.contains(row["payload"]):
                    result.violations.append(f"event:{row['session_id']}:{row['seq']}")
    finally:
        await store.close()
    return result


def archive_identifier_cassettes(cassette_dir: Path, archive: Path) -> int:
    detector = Detector(fixture_identifiers())
    unsafe = [
        path
        for path in cassette_dir.glob("*.json")
        if detector.contains(json.loads(path.read_text()))
    ]
    archive.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in unsafe:
        target = archive / path.name
        if target.exists():
            raise ValueError("Privacy archive target already exists; choose a fresh directory")
    for path in unsafe:
        shutil.move(str(path), str(archive / path.name))
        (archive / path.name).chmod(0o600)
    return len(unsafe)
