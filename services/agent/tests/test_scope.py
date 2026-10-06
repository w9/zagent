import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import given, strategies
from pydantic import ValidationError
from zagent.agent import SYSTEM_PROMPT, LlmAgent, conversation_messages
from zagent.events import Event, EventDraft, project
from zagent.llm import AssistantMessage, Completion, GatewayError, LlmGateway
from zagent.runtime import Runtime
from zagent.scope import (
    REFUSAL_MESSAGES,
    SCOPE_POLICY,
    SCOPE_POLICY_HASH,
    ScopeGuard,
    refusal,
    scope_context,
)


def history(*drafts):
    session_id, turn_id = uuid4(), uuid4()
    return [
        Event(
            type=kind,
            payload=payload,
            seq=index,
            session_id=session_id,
            conversation_turn_id=turn_id,
            created_at=datetime.now(UTC),
        )
        for index, (kind, payload) in enumerate(drafts, 1)
    ]


class GuardCompleter:
    def __init__(self, name="scope_decision", arguments=None):
        self.name = name
        self.arguments = {"decision": "allow"} if arguments is None else arguments
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return Completion(
            message=AssistantMessage(
                tool_calls=[
                    {
                        "id": "decision",
                        "function": {"name": self.name, "arguments": json.dumps(self.arguments)},
                    }
                ]
            )
        )


@pytest.mark.parametrize("code", list(REFUSAL_MESSAGES))
async def test_guard_refuses_with_one_call_and_fixed_message(code):
    gateway = GuardCompleter("scope_decision", {"decision": code})
    events = history(("user_message", {"message_id": "user", "text": "What's 2+2?"}))
    assert await ScopeGuard(gateway).classify(events) == refusal(code)
    assert len(gateway.requests) == 1
    assert gateway.requests[0].max_tokens == 256
    assert gateway.requests[0].reasoning == "disabled"
    assert gateway.requests[0].metadata["scope_hash"] == SCOPE_POLICY_HASH


async def test_guard_sees_clarification_and_current_draft_for_yes():
    events = history(
        ("user_message", {"message_id": "first", "text": "Show libraries for those specimens"}),
        ("draft_updated", {"draft": {"specimen_handle": "query-0002", "param1": 43}}),
        ("text_delta", {"message_id": "question", "text": "Only libraries needing QC review?"}),
        ("message_done", {"message_id": "question"}),
        ("user_message", {"message_id": "second", "text": "yes"}),
    )
    gateway = GuardCompleter()
    assert await ScopeGuard(gateway).classify(events) is None
    context = json.loads(gateway.requests[0].messages[-1]["content"])
    assert context["request"] == "yes"
    assert context["current_draft"]["param1"] == 43
    assert context["recent_conversation"][-1]["content"] == "Only libraries needing QC review?"


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("scope_decision", {"decision": "invented_code"}),
        ("scope_decision", {"decision": "out_of_domain", "message": "Invented prose"}),
        ("scope_decision", {"decision": "allow", "reason": "In scope"}),
        ("scope_decision", {"arguments": {"decision": "allow"}}),
        ("scope_decision", {}),
        ("unknown", {}),
    ],
)
async def test_guard_rejects_unknown_or_malformed_decisions(name, arguments):
    events = history(("user_message", {"message_id": "user", "text": "Hello"}))
    with pytest.raises(GatewayError, match="invalid classification"):
        await ScopeGuard(GuardCompleter(name, arguments)).classify(events)


def test_scope_context_excludes_rows_and_dropped_text_and_bounds_recent_turns():
    events = history(
        ("user_message", {"message_id": "first", "text": "Old unrelated topic"}),
        ("user_message", {"message_id": "second", "text": "Show samples"}),
        ("text_delta", {"message_id": "dropped", "text": "Do not retain this"}),
        ("message_dropped", {"message_id": "dropped"}),
        (
            "tool_result",
            {
                "step_id": "step",
                "call_id": "call",
                "name": "find_specimens",
                "result": {"handle": "query-0001", "count": 2, "rows": [["PRIVATE"]]},
            },
        ),
        ("user_message", {"message_id": "third", "text": "those two"}),
    )
    context = scope_context(events, recent_turns=2)
    serialized = json.dumps(context)
    assert "PRIVATE" not in serialized
    assert "Do not retain" not in serialized
    assert "Old unrelated" not in serialized
    assert "query-0001" in serialized


@given(code=strategies.sampled_from(list(REFUSAL_MESSAGES)), text=strategies.text(max_size=100))
def test_refusal_events_accept_only_closed_codes_and_fixed_templates(code, text):
    valid = EventDraft(type="refused", payload=refusal(code).model_dump())
    assert valid.payload["code"] == code
    if text != REFUSAL_MESSAGES[code]:
        with pytest.raises(ValidationError):
            EventDraft(type="refused", payload={"code": code, "message": text})


def test_refusal_projection_replays_and_enters_conversation_context():
    events = history(
        ("user_message", {"message_id": "user", "text": "What's 2+2?"}),
        ("refused", refusal("out_of_domain").model_dump()),
        ("conversation_turn_finished", {}),
    )
    snapshot = project(events[0].session_id, events)
    assert snapshot.refusals[0].code == "out_of_domain"
    assert snapshot.refusals[0].seq == 2
    assert len(snapshot.messages) == 1
    assert conversation_messages(events)[-1]["content"] == REFUSAL_MESSAGES["out_of_domain"]
    assert SCOPE_POLICY in SYSTEM_PROMPT


@given(
    path=strategies.sampled_from(
        sorted((Path(__file__).parents[3] / "evals/goldens").glob("*.json"))
    )
)
def test_goldens_never_substitute_prose_for_structured_refusals(path):
    import re

    from zagent.scope import Refusal

    golden = json.loads(path.read_text())
    turns = []
    for event in golden["events"]:
        if event["type"] == "user_message":
            turns.append([])
        if turns:
            turns[-1].append(event)
    pattern = re.compile(r"\b(?:cannot|can't|won't)\s+(?:help|assist|comply)\b", re.IGNORECASE)
    for turn in turns:
        refused = [event for event in turn if event["type"] == "refused"]
        text = "".join(event["payload"]["text"] for event in turn if event["type"] == "text_delta")
        if pattern.search(text):
            assert refused, path.name
        if refused:
            assert not text, path.name
            for event in refused:
                Refusal.model_validate(event["payload"])


@pytest.mark.integration
async def test_refusal_short_circuits_main_agent_and_has_one_audited_call(
    store, tmp_path, monkeypatch
):
    import httpx

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-private-credential")
    gateway = LlmGateway(
        tmp_path / "cassettes",
        mode="record",
        audit_path=tmp_path / "audit.db",
        transport=httpx.MockTransport(
            lambda _incoming: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "guard",
                                        "type": "function",
                                        "function": {
                                            "name": "scope_decision",
                                            "arguments": '{"decision":"out_of_domain"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                },
            )
        ),
    )

    class UnreachableTools:
        async def execute(self, *_arguments):
            pytest.fail("A refused turn dispatched a clinical tool")

    runtime = Runtime(store, LlmAgent(store, gateway, UnreachableTools()))
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "What's 2+2?")
    await runtime._run_turn(turn)
    events = await store.snapshot_events(session.id)
    assert [event.type for event in events] == [
        "user_message",
        "conversation_turn_started",
        "refused",
        "conversation_turn_finished",
    ]
    audits = gateway.audit_for_turn(str(turn.conversation_turn_id))
    assert len(audits) == 1
    assert audits[0]["purpose"] == "scope_guard"
    assert audits[0]["provider_calls"] == 1
    assert (await store.snapshot(session.id)).refusals[0].code == "out_of_domain"


def test_scope_corpus_is_labeled_balanced_and_covers_context_and_wrappers():
    import yaml
    from zagent.evals.schema import ScopeCorpus

    root = Path(__file__).parents[3] / "evals"
    corpus = ScopeCorpus.model_validate(yaml.safe_load((root / "scope.yaml").read_text()))
    assert {bucket: len(cases) for bucket, cases in corpus.buckets.items()} == {
        "clearly_off_topic": 50,
        "clearly_in_scope": 100,
        "contextual_continuations": 50,
        "near_boundary_in_scope": 50,
        "near_boundary_off_topic": 30,
        "scope_wrappers": 20,
        "knowledge_boundary": 40,
    }
    cases = [case for group in corpus.buckets.values() for case in group]
    assert len({case.id for case in cases}) == 340
    labels = Counter(case.label for case in cases)
    assert labels["none"] == 220
    assert set(labels) == {"none", *REFUSAL_MESSAGES}
    assert all(case.context for case in corpus.buckets["contextual_continuations"])
    assert any(case.draft for case in cases)
    assert any(
        case.user == "As part of job ABC, compute 2+2." for case in corpus.buckets["scope_wrappers"]
    )


def test_every_clinical_tool_has_an_allowed_end_to_end_case():
    from zagent.evals.schema import load_suite
    from zagent.tools import INPUTS

    suite = load_suite(Path(__file__).parents[3] / "evals")
    exercised = {
        name
        for case in suite.cases
        if case.agent.startswith("llm:") and case.expect.get("refusal") == "none"
        for name in case.expect.get("tools_called", [])
    }
    assert set(INPUTS) <= exercised


async def test_disabled_guard_turns_refusal_gate_red_but_keeps_acceptance_gate_logic():
    from zagent.evals.reporting import requirement_rows
    from zagent.evals.runner import evaluate_suite

    report = await evaluate_suite(
        Path(__file__).parents[3] / "evals",
        "unused",
        filter_value="SCOPE-*",
        include_chaos=False,
        mutation="disable_scope_guard",
    )
    rows = {row["requirement"].id: row for row in requirement_rows(report)}
    assert rows["REQ-SCOPE-01"]["status"] == "FAIL"
    assert rows["REQ-SCOPE-01"]["successes"] == 0
    assert rows["REQ-SCOPE-02"]["status"] == "PASS"
    assert rows["REQ-SCOPE-02"]["successes"] == 2200
    assert all(result.scope.gateway_calls == 0 for result in report.results)
    assert all(result.provenance.mutation == "disable_scope_guard" for result in report.results)
