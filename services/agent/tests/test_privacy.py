import asyncio
import json

import pytest
from hypothesis import given, strategies
from zagent.privacy import (
    Detector,
    DisplayHoldback,
    EgressBlocked,
    EgressTripwire,
    Identifier,
    PrivacyError,
    Raw,
    SessionTokens,
    Tokenized,
)

MRNS = ["NGC-0041872", "LHX/26/41872", "SQ-AB-1000", "CV00041872", "704-42-1000"]


@pytest.mark.parametrize("mrn", MRNS)
def test_each_site_mrn_is_detected_without_a_registry(mrn):
    vault = SessionTokens(Detector())
    tokenized = vault.tokenize(Raw(value=f"Find {mrn}, then {mrn}."), path="user_message")
    assert tokenized.value == "Find [PT_1], then [PT_1]."
    assert vault.resolve(tokenized).value == f"Find {mrn}, then {mrn}."


def test_dictionary_names_numbering_and_persisted_bindings():
    detector = Detector([Identifier(value="Mira Vellorin"), Identifier(value=MRNS[0])])
    first = SessionTokens(detector)
    assert first.tokenize(
        Raw(value=f"{MRNS[0]} belongs to Mira Vellorin"), path="user_message"
    ).value == ("[PT_1] belongs to [PT_2]")
    restored = SessionTokens(detector, first.bindings)
    assert restored.text(f"Mira Vellorin, {MRNS[0]}, NGC-0041873") == "[PT_2], [PT_1], [PT_3]"
    assert SessionTokens(detector).text("Mira Vellorin") == "[PT_1]"


def test_schema_annotations_protect_values_not_detectable_in_free_text():
    vault = SessionTokens(Detector())
    schema = {"properties": {"mrn": {"type": "string", "x-identifier": "PT"}}}
    result = vault.tokenize(
        Raw(value={"mrn": "opaque-identity", "count": 1}), path="tool_arguments", schema=schema
    )
    assert result.value == {"mrn": "[PT_1]", "count": 1}
    assert vault.resolve(result, strict=True).value["mrn"] == "opaque-identity"
    assert vault.text("Find opaque-identity again") == "Find [PT_1] again"
    restored = SessionTokens(Detector(), vault.bindings)
    assert restored.text("opaque-identity") == "[PT_1]"
    with pytest.raises(PrivacyError, match="Unregistered"):
        vault.tokenize(Raw(value="hello"), path="new_ingress")
    with pytest.raises(TypeError):
        vault.tokenize("not typed", path="user_message")


def test_encoded_json_tool_arguments_are_tokenized_before_persistence():
    vault = SessionTokens(Detector([Identifier(value="Mira Vellorin")]))
    source = {
        "tool_calls": [
            {
                "function": {
                    "name": "find_patients",
                    "arguments": '{"mrn":"\\u004eGC-0041872","name":"Mira Vellorin"}',
                }
            }
        ]
    }
    protected = vault.tokenize(Raw(value=source), path="assistant_output")
    arguments = json.loads(protected.value["tool_calls"][0]["function"]["arguments"])
    assert arguments == {"mrn": "[PT_1]", "name": "[PT_2]"}
    assert "NGC-0041872" not in json.dumps(protected.value)
    assert "Mira Vellorin" not in json.dumps(protected.value)


def test_raw_reserved_tokens_are_escaped_and_unknown_tokens_fail_resolution():
    vault = SessionTokens(Detector())
    value = vault.tokenize(
        Raw(value="Literal [PT_1] and NGC-0041872"), path="user_message", external=True
    )
    assert value.value == "Literal [LIT_1] and [PT_1]"
    assert vault.resolve(value).value == "Literal [PT_1] and NGC-0041872"
    with pytest.raises(PrivacyError, match="cross-session"):
        SessionTokens(Detector()).resolve(Tokenized(value="[PT_1]"), strict=True)
    with pytest.raises(ValueError, match="collides"):
        Detector([Identifier(value="[PT_1]")])


@given(cuts=strategies.lists(strategies.integers(min_value=0, max_value=43), unique=True))
def test_display_holdback_resolves_tokens_split_at_arbitrary_boundaries(cuts):
    vault = SessionTokens(Detector())
    token = vault.text(MRNS[0])
    source = f"The patient {token} has records for {token}."
    boundaries = sorted({0, len(source), *(min(cut, len(source)) for cut in cuts)})
    buffer = DisplayHoldback(lambda text: vault.resolve(Tokenized(value=text)).value)
    rendered = ""
    for start, stop in zip(boundaries, boundaries[1:], strict=False):
        chunk = buffer.feed(source[start:stop])
        assert "[PT" not in chunk
        rendered += chunk
    rendered += buffer.feed("", final=True)
    assert rendered == f"The patient {MRNS[0]} has records for {MRNS[0]}."


def test_incomplete_display_token_is_held_and_never_rendered_literally():
    buffer = DisplayHoldback(lambda text: text)
    assert buffer.feed("Patient [PT_") == "Patient "
    assert buffer.feed("", final=True) == "[unavailable identifier]"
    assert buffer.feed("ordinary [bracketed text]") == "ordinary [bracketed text]"


def test_tripwire_contains_only_keyed_hashes_and_scans_nested_json():
    key = b"unit-test-only-tripwire-key-32bytes"
    identifiers = [Identifier(value=value) for value in [*MRNS, "Mira Vellorin"]]
    manifest = EgressTripwire.manifest(key, identifiers)
    serialized = manifest.model_dump_json()
    assert all(item.value not in serialized for item in identifiers)
    assert manifest != EgressTripwire.manifest(b"different-key-at-least-32-bytes-long", identifiers)
    check = EgressTripwire(key, manifest)
    for value in [*MRNS, "Mira Vellorin", "mira vellorin"]:
        with pytest.raises(EgressBlocked):
            check({"messages": [{"content": json.dumps({"mrn": value})}]})
    with pytest.raises(EgressBlocked):
        check({"messages": [{"content": "prefixMira Vellorinsuffix"}]})
    check({"messages": [{"content": "Find [PT_1] with received_within P1D"}]})


@pytest.mark.integration
async def test_private_vault_is_persistent_and_runtime_cannot_resolve(store):
    import httpx
    from zagent.cohort import FROZEN_NOW, ClinicalStore
    from zagent.privacy_client import PrivacyClient
    from zagent.privacy_server import capability, create_privacy_app
    from zagent.privacy_store import PrivacyStore

    await ClinicalStore(store, lambda: FROZEN_NOW).seed()
    session = await store.create_session()
    master = b"unit-test-only-master-key-32-bytes"
    backend = PrivacyStore(store.pool)
    app = create_privacy_app(master, backend)
    transport = httpx.ASGITransport(app=app)
    runtime = PrivacyClient("http://privacy", capability(master, "tokenize"), transport=transport)
    display = PrivacyClient("http://privacy", capability(master, "display"), transport=transport)
    tokens = await runtime.tokenize(
        session.id, Raw(value="NGC-0041872 is Mira Vellorin"), path="user_message"
    )
    assert tokens.value == "[PT_1] is [PT_2]"
    assert (await display.resolve(session.id, tokens)).value == "NGC-0041872 is Mira Vellorin"
    assert (
        await PrivacyStore(store.pool).tokenize(
            session.id,
            Raw(value="Mira Vellorin"),
            path="user_message",
        )
    ).value == "[PT_2]"
    with pytest.raises(PrivacyError, match="capability"):
        await runtime.resolve(session.id, tokens)
    with pytest.raises(PrivacyError, match="capability"):
        await runtime.bindings(session.id)
    async with store.pool.acquire() as connection, connection.transaction():
        await connection.execute("SET LOCAL ROLE zagent_runtime")
        with pytest.raises(Exception, match="permission denied"):
            await connection.fetch("SELECT * FROM privacy.tokens")


@pytest.mark.integration
async def test_cold_vault_resolution_does_not_exhaust_database_pool(store):
    from zagent.privacy_store import PrivacyStore

    session = await store.create_session()
    await store.privacy.tokenize(session.id, Raw(value=MRNS[0]), path="user_message")
    cold = PrivacyStore(store.pool)
    async with asyncio.timeout(5):
        results = await asyncio.gather(
            *(cold.resolve(session.id, Tokenized(value="[PT_1]")) for _index in range(20))
        )
    assert all(result.value == MRNS[0] for result in results)


def test_every_persisted_event_has_an_explicit_privacy_ingress_or_lifecycle_role():
    from typing import get_args

    from zagent.events import EventType
    from zagent.store import EVENT_INGRESS, LIFECYCLE_EVENTS

    assert set(get_args(EventType)) == set(EVENT_INGRESS) | LIFECYCLE_EVENTS


@pytest.mark.integration
async def test_event_ingress_and_tool_execution_keep_identifiers_at_the_edges(store):
    from zagent.cohort import FROZEN_NOW, ClinicalStore
    from zagent.events import EventDraft
    from zagent.tools import McpToolClient, ToolsGateway, create_mcp_server

    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Find NGC-0041872, Mira Vellorin")
    assert turn.message == "Find [PT_1], [PT_2]"
    gateway = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    result = await gateway.execute(turn, "find_patients", '{"mrn":"[PT_1]"}')
    assert result["count"] == 1
    executed = await store.pool.fetchval(
        "SELECT arguments FROM privacy.execution_audit WHERE conversation_turn_id = $1",
        turn.conversation_turn_id,
    )
    assert executed == {"mrn": "NGC-0041872"}
    await store.append(
        session.id,
        turn.conversation_turn_id,
        EventDraft(
            type="text_delta",
            payload={"message_id": "answer", "text": "Mira Vellorin: NGC-0041872"},
        ),
    )
    events = await store.snapshot_events(session.id)
    serialized = json.dumps([event.model_dump(mode="json") for event in events])
    assert "NGC-0041872" not in serialized
    assert "Mira Vellorin" not in serialized
    assert "[PT_1]" in serialized
    assert (await store.privacy.resolve(session.id, Tokenized(value=events[-1].payload))).value[
        "text"
    ] == ("Mira Vellorin: NGC-0041872")
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
@pytest.mark.parametrize("field", ["display_name", "id", "mrn"])
async def test_patient_reference_tokens_resolve_to_site_scoped_mrns(store, field):
    from zagent.cohort import FROZEN_NOW, ClinicalStore
    from zagent.tools import McpToolClient, ToolsGateway, create_mcp_server

    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    patient = await store.pool.fetchrow(
        "SELECT id,mrn,display_name FROM patients "
        "WHERE site_id='northgate' AND display_name='Arin Vellorin'"
    )
    assert patient is not None
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, f"Let's use {patient[field]}")
    assert turn.message == "Let's use [PT_1]"
    gateway = ToolsGateway(store, McpToolClient(server=create_mcp_server(clinical)))
    result = await gateway.execute(turn, "find_patients", '{"mrn":"[PT_1]"}')
    assert result["count"] == 1
    assert set(result) == {"handle", "count", "schema"}
    selected = await clinical.resolve(session.id, result["handle"], "patients")
    assert selected["row_ids"] == [patient["id"]]
    executed = await store.pool.fetchval(
        "SELECT arguments FROM privacy.execution_audit WHERE conversation_turn_id=$1",
        turn.conversation_turn_id,
    )
    assert executed == {"mrn": patient["mrn"]}
    audit = await store.pool.fetchrow(
        "SELECT arguments,result FROM tool_audit WHERE conversation_turn_id=$1",
        turn.conversation_turn_id,
    )
    assert patient["mrn"] not in json.dumps(dict(audit))
    assert patient["display_name"] not in json.dumps(dict(audit))
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)


@pytest.mark.integration
async def test_patient_reference_does_not_guess_ambiguous_names_or_cross_sites(store):
    from zagent.cohort import FROZEN_NOW, ClinicalStore
    from zagent.tools import ClinicalTools

    clinical = ClinicalStore(store, lambda: FROZEN_NOW)
    await clinical.seed()
    backend = ClinicalTools(clinical)
    patients = await store.pool.fetch(
        "SELECT id,mrn,display_name FROM patients WHERE site_id='northgate' ORDER BY id LIMIT 2"
    )
    selected, other = patients
    session = await store.create_session()
    token = await store.privacy.tokenize(
        session.id, Raw(value=selected["display_name"]), path="user_message"
    )
    async with store.pool.atomic() as connection:
        await connection.execute(
            "UPDATE patients SET display_name=$2 WHERE id=$1", other["id"], selected["display_name"]
        )
        try:
            result = await backend.dispatch(session.id, "find_patients", {"mrn": token.value})
            assert result["error"]["code"] == "invalid_arguments"
            assert "ambiguous" in result["error"]["message"]
            assert "handle" not in result
        finally:
            await connection.execute(
                "UPDATE patients SET display_name=$2 WHERE id=$1",
                other["id"],
                other["display_name"],
            )
    foreign = await store.create_session("lakeside")
    assert (await backend.dispatch(foreign.id, "find_patients", {"mrn": token.value}))["error"][
        "code"
    ] == "invalid_arguments"
    foreign_token = await store.privacy.tokenize(
        foreign.id, Raw(value=selected["mrn"]), path="user_message"
    )
    assert (await backend.dispatch(foreign.id, "find_patients", {"mrn": foreign_token.value}))[
        "count"
    ] == 0
    assert (await backend.dispatch(session.id, "find_patients", {"mrn": selected["display_name"]}))[
        "count"
    ] == 0


@pytest.mark.integration
async def test_tripwire_blocks_bypassed_ingress_before_network_and_emits_alert(store, tmp_path):
    import httpx
    from zagent.llm import CompletionRequest, LlmGateway
    from zagent.runtime import Runtime

    key = b"unit-test-tripwire-key-at-least-32-bytes"
    check = EgressTripwire(key, EgressTripwire.manifest(key, [Identifier(value=MRNS[0])]))
    gateway = LlmGateway(
        tmp_path / "cassettes",
        mode="live",
        egress_check=check,
        audit_path=tmp_path / "audit.db",
        transport=httpx.MockTransport(lambda _request: pytest.fail("Identifier egress")),
    )

    class BypassedIngress:
        async def run_turn(self, session, _emit):
            await gateway.complete(
                CompletionRequest(
                    messages=[{"role": "user", "content": MRNS[0]}],
                    metadata={
                        "session_id": str(session.id),
                        "conversation_turn_id": str(session.conversation_turn_id),
                    },
                )
            )

    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Exercise the privacy tripwire")
    await Runtime(store, BypassedIngress())._run_turn(turn)
    events = await store.snapshot_events(session.id)
    assert [event.type for event in events][-2:] == ["privacy_alert", "conversation_turn_failed"]
    audit = gateway.audit_for_turn(str(turn.conversation_turn_id))
    assert audit[0]["outcome"] == "blocked"
    assert audit[0]["provider_calls"] == 0
    assert gateway.requests_for_session(str(session.id)) == []
    assert MRNS[0] not in json.dumps(audit)


@pytest.mark.integration
async def test_display_stream_and_snapshot_agree_across_partial_tokens_and_reconnect(store):
    from datetime import UTC, datetime
    from uuid import uuid4

    from zagent.display import SessionDisplay
    from zagent.events import Event, project

    session = await store.create_session()
    await store.privacy.tokenize(session.id, Raw(value=MRNS[0]), path="user_message")
    turn_id = uuid4()
    drafts = [
        ("user_message", {"message_id": "user", "text": "Show [PT_1]"}),
        ("text_delta", {"message_id": "answer", "text": "Patient [PT_"}),
        ("text_delta", {"message_id": "answer", "text": "1] has a result."}),
        ("message_done", {"message_id": "answer"}),
        ("conversation_turn_finished", {}),
    ]
    events = [
        Event(
            type=kind,
            payload=payload,
            session_id=session.id,
            conversation_turn_id=turn_id,
            seq=index,
            created_at=datetime.now(UTC),
        )
        for index, (kind, payload) in enumerate(drafts, 1)
    ]
    for split in range(len(events)):
        first = SessionDisplay(session.id, store.privacy)
        shown = [await first.event(event) for event in events[:split]]
        restored = SessionDisplay(session.id, store.privacy)
        for event in events[:split]:
            await restored.event(event)
        shown.extend([await restored.event(event) for event in events[split:]])
        assert project(session.id, shown) == await restored.projection(project(session.id, events))
        assert project(session.id, shown).messages[-1].text == f"Patient {MRNS[0]} has a result."
        assert "[PT_" not in json.dumps([event.payload for event in shown])


@pytest.mark.integration
async def test_public_display_resolves_but_model_snapshot_stays_tokenized(database_url):
    from zagent.agent import ScriptedAgent
    from zagent.evals.environment import local_api

    async with local_api(database_url, ScriptedAgent(delay_scale=0)) as environment:
        client = environment.client
        session = (await client.post("/sessions")).json()["id"]
        await client.post(f"/sessions/{session}/messages", json={"text": f"Find {MRNS[0]}"})
        display = (await client.get(f"/sessions/{session}/snapshot")).json()
        model = (await client.get(f"/sessions/{session}/snapshot?representation=model")).json()
        assert display["messages"][0]["text"] == f"Find {MRNS[0]}"
        assert model["messages"][0]["text"] == "Find [PT_1]"
        bindings = (await client.get(f"/sessions/{session}/bindings")).json()
        assert any(item["token"] == "[PT_1]" and item["value"] == MRNS[0] for item in bindings)
        foreign = await environment.app.state.store.create_session("lakeside")
        assert (await client.get(f"/sessions/{foreign.id}/bindings")).status_code == 404


@pytest.mark.integration
async def test_runtime_api_rejects_raw_messages_and_cannot_resolve_handles(database_url):
    import httpx
    from zagent.agent import ScriptedAgent
    from zagent.app import Settings, create_app

    app = create_app(
        Settings(database_url=database_url, display_mode=False), ScriptedAgent(delay_scale=0)
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://runtime"
        ) as client:
            session = (await client.post("/sessions")).json()["id"]
            raw = await client.post(f"/sessions/{session}/messages", json={"text": MRNS[0]})
            assert raw.status_code == 422
            mislabeled = await client.post(
                f"/sessions/{session}/messages", json={"text": {"value": MRNS[0]}}
            )
            assert mislabeled.status_code == 422
            assert (await client.get(f"/sessions/{session}/handles/query-0001")).status_code == 403
            assert (await client.get(f"/sessions/{session}/xray")).status_code == 403
            assert (await client.get(f"/sessions/{session}/bindings")).status_code == 403
            snapshot = (await client.get(f"/sessions/{session}/snapshot")).json()
            assert snapshot["messages"] == []


def test_private_evidence_assertions_detect_identifier_leaks_and_resolved_mismatches(tmp_path):
    from datetime import UTC, datetime
    from uuid import uuid4

    from zagent.evals.assertions import (
        Evidence,
        egress_private,
        event_log_private,
        resolved_tool_calls,
    )
    from zagent.events import Event, project

    session_id, turn_id = uuid4(), uuid4()
    event = Event(
        type="user_message",
        payload={"message_id": "user", "text": "Find [PT_1]"},
        seq=1,
        session_id=session_id,
        conversation_turn_id=turn_id,
        created_at=datetime.now(UTC),
    )
    evidence = Evidence(
        [event],
        project(session_id, [event]),
        requests=[
            {
                "messages": [{"role": "user", "content": "Find [PT_1]"}],
            }
        ],
        executions=[{"tool": "find_patients", "arguments": {"mrn": MRNS[0]}}],
    )
    assert egress_private(evidence, "no_known_identifiers", tmp_path, "PHI") is None
    assert event_log_private(evidence, "no_known_identifiers", tmp_path, "PHI") is None
    assert (
        resolved_tool_calls(
            evidence,
            [{"name": "find_patients", "args_resolved": {"mrn": MRNS[0]}}],
            tmp_path,
            "PHI",
        )
        is None
    )
    evidence.requests[0]["messages"][0]["content"] = MRNS[0]
    assert "REQ-PHI-01" in egress_private(evidence, "no_known_identifiers", tmp_path, "PHI")
    event.payload["text"] = MRNS[0]
    assert "REQ-PHI-02" in event_log_private(evidence, "no_known_identifiers", tmp_path, "PHI")


def test_legacy_cassette_archive_preserves_raw_recording_and_keeps_clean_files(tmp_path):
    from zagent.evals.privacy import archive_identifier_cassettes

    source = tmp_path / "cassettes"
    source.mkdir()
    raw = '{"request":{"messages":[{"content":"Find NGC-0041872"}]}}'
    (source / "raw.json").write_text(raw)
    (source / "clean.json").write_text('{"request":{"messages":[{"content":"Find [PT_1]"}]}}')
    archive = tmp_path / "private" / "archive"
    assert archive_identifier_cassettes(source, archive) == 1
    assert (archive / "raw.json").read_text() == raw
    assert (archive / "raw.json").stat().st_mode & 0o777 == 0o600
    assert not (source / "raw.json").exists()
    assert (source / "clean.json").exists()


def test_privacy_corpus_failure_cannot_be_hidden_by_passing_behavioral_trials(tmp_path):
    from datetime import UTC, datetime

    from zagent.evals.reporting import report_passes, terminal_report, write_report
    from zagent.evals.schema import Case, PrivacyScan, Provenance, Report, Requirement, TrialResult

    clock = datetime.now(UTC)
    report = Report(
        created_at=clock,
        duration_seconds=0,
        verifications=["standard"],
        requirements=[
            Requirement(
                id="REQ-PHI-01",
                tier="invariant",
                statement="Private requests",
                cases=["PHI-TEST"],
                enforced_by=["privacy.py"],
                mutations=["bypass"],
            )
        ],
        cases=[
            Case(
                id="PHI-TEST",
                requirement="REQ-PHI-01",
                agent="llm:default",
                conversation_turns=[{"user": "Hello"}],
                expect={"golden": "test.json"},
            )
        ],
        results=[
            TrialResult(
                case_id="PHI-TEST",
                verification="standard",
                seed=0,
                passed=True,
                duration_seconds=0,
                executions=1,
                privacy_requests=2,
                provenance=Provenance(
                    commit=None,
                    dirty_worktree=None,
                    agent_implementation="LlmAgent",
                    seed=0,
                    clock=clock,
                ),
            )
        ],
        privacy_scan=PrivacyScan(recorded_requests=2, stored_events=3),
    )
    assert report_passes(report)
    assert "0 identifier violations" in terminal_report(report)
    assert "Privacy boundary" in write_report(report, tmp_path).read_text()
    report.privacy_scan.violations.append("model_request:example")
    assert not report_passes(report)
