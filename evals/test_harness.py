import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError
from zagent.evals.assertions import Evidence, check_case, render_transcript, transcript_diff
from zagent.evals.schema import Case, Requirement, Suite, fixture_path
from zagent.events import Event, project


def sample_case(**overrides):
    return Case.model_validate(
        {
            "id": "STREAM-TEST",
            "requirement": "REQ-STREAM-01",
            "agent": "scripted:default",
            "conversation_turns": [{"user": "Hello"}],
            "expect": {
                "golden": "goldens/test.json",
                "events_include": ["conversation_turn_finished"],
            },
            **overrides,
        }
    )


def sample_evidence(text="Hello world."):
    session_id, turn_id = uuid4(), uuid4()
    events = [
        Event(
            session_id=session_id,
            seq=seq,
            conversation_turn_id=turn_id,
            type=kind,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        for seq, (kind, payload) in enumerate(
            [
                ("user_message", {"message_id": str(uuid4()), "text": "Hello"}),
                ("conversation_turn_started", {}),
                ("text_delta", {"message_id": "answer", "text": text}),
                ("message_done", {"message_id": "answer"}),
                ("conversation_turn_finished", {}),
            ],
            start=1,
        )
    ]
    return Evidence(events, project(session_id, events))


def test_golden_diff_names_case_and_exposes_broken_reducer(tmp_path):
    evidence = sample_evidence()
    golden = fixture_path(tmp_path, "goldens/test.json")
    golden.parent.mkdir()
    golden.write_text(render_transcript(evidence))
    assert check_case(sample_case(), evidence, tmp_path) == []
    evidence.projection.messages[-1].text = "Broken projection"
    failures = check_case(sample_case(), evidence, tmp_path)
    assert len(failures) == 1
    assert "--- STREAM-TEST/golden" in failures[0]
    assert '+      "text": "Broken projection"' in failures[0]


def test_normalized_evidence_is_stable_across_fresh_identifiers():
    assert render_transcript(sample_evidence()) == render_transcript(sample_evidence())


def test_refusal_assertion_accepts_closed_codes_and_detects_unstructured_prose(tmp_path):
    from zagent.evals.assertions import refusal_invariants
    from zagent.scope import refusal

    evidence = sample_evidence("I cannot help with unrelated arithmetic.")
    assert "REQ-SCOPE-03" in refusal_invariants(evidence, "SCOPE-TEST")[0]
    case = sample_case(agent="guard:default", expect={"refusal": {"code": "out_of_domain"}})
    events = (
        evidence.events[:2]
        + [
            evidence.events[2].model_copy(
                update={
                    "type": "refused",
                    "payload": refusal("out_of_domain").model_dump(),
                }
            )
        ]
        + [evidence.events[-1].model_copy(update={"seq": 4})]
    )
    evidence = Evidence(events, project(evidence.projection.session_id, events))
    assert check_case(case, evidence, tmp_path) == []
    case.expect["refusal"] = "none"
    assert "in-scope request was refused" in check_case(case, evidence, tmp_path)[0]
    case.expect["refusal"] = {"code": "unknown"}
    with pytest.raises(ValidationError):
        check_case(case, evidence, tmp_path)


def test_numeric_grounding_requires_a_preceding_entity_count(tmp_path):
    evidence = sample_evidence("Found **3** specimens.")
    result = evidence.events[0].model_copy(
        update={
            "type": "tool_result",
            "payload": {
                "step_id": "step",
                "call_id": "call",
                "name": "find_specimens",
                "result": {"handle": "query-0001", "count": 3, "schema": []},
            },
        }
    )
    events = evidence.events[:2] + [result] + evidence.events[2:]
    events = [event.model_copy(update={"seq": index}) for index, event in enumerate(events, 1)]
    evidence = Evidence(events, project(evidence.projection.session_id, events))
    case = sample_case(expect={"golden": "test.json", "numeric_claims_grounded": True})
    assert check_case(case, evidence, tmp_path, skip_golden=True) == []
    evidence.events[2].payload["result"]["count"] = 99
    assert (
        "unsupported claim: 3 specimens"
        in check_case(case, evidence, tmp_path, skip_golden=True)[0]
    )


def test_real_agent_assertions_reject_bad_configuration_and_inline_rows(tmp_path):
    evidence = sample_evidence()
    for name in ("tools_only_handles", "numeric_claims_grounded", "references_resolve"):
        with pytest.raises(ValueError, match="must be a boolean"):
            check_case(sample_case(expect={"golden": "test.json", name: "yes"}), evidence, tmp_path)
    case = sample_case(expect={"golden": "test.json", "tools_only_handles": True})
    assert "no tool results" in check_case(case, evidence, tmp_path, skip_golden=True)[0]


def view_evidence():
    fixture = json.loads((Path(__file__).parent / "fixtures/view-replay.json").read_text())
    session_id, turn_id = uuid4(), uuid4()
    events = [
        Event(
            **draft,
            seq=index + 1,
            session_id=session_id,
            conversation_turn_id=turn_id,
            created_at=datetime.now(UTC),
        )
        for index, draft in enumerate(fixture["events"])
    ]
    return Evidence(events, project(session_id, events))


def test_view_assertions_validate_schema_and_every_replayed_prefix(tmp_path):
    case = sample_case(
        expect={
            "golden": "test.json",
            "views": [{"kind": "table", "props_match": {"title": "~received"}}],
            "view_stack_depth": 2,
        }
    )
    evidence = view_evidence()
    assert check_case(case, evidence, tmp_path, skip_golden=True) == []
    evidence.projection.views.pop()
    failures = check_case(case, evidence, tmp_path, skip_golden=True)
    assert any("REQ-VIEW-02" in failure for failure in failures)
    assert any("expected view stack depth 2" in failure for failure in failures)


def test_view_schema_is_checked_even_without_view_expectations(tmp_path):
    evidence = view_evidence()
    evidence.events[3].payload["spec"]["props"]["row_count"] = -1
    failures = check_case(sample_case(), evidence, tmp_path, skip_golden=True)
    assert "REQ-VIEW-01 invalid view" in failures[0]


def test_bad_view_assertion_configuration_is_rejected(tmp_path):
    for expected in [
        {"view_stack_depth": -1},
        {"view_stack_depth": True},
        {"views": [{"kind": "table", "props_match": {"title": "~["}}]},
        {"views": [{"kind": "table", "typo": True}]},
    ]:
        with pytest.raises(ValueError):
            check_case(
                sample_case(expect={"golden": "test.json", **expected}), view_evidence(), tmp_path
            )


def test_view_chaos_targets_complete_view_push_boundaries():
    from zagent.evals.runner import chaos_plan

    reference = view_evidence()
    plans = [chaos_plan(sample_case(), reference, seed) for seed in range(10)]
    assert all(plan.disconnect_after_view is not None for plan in plans)
    assert len({plan.disconnect_after_view for plan in plans}) > 1


def test_unredacted_nondeterminism_produces_a_readable_diff():
    first = sample_evidence()
    second = sample_evidence()
    second.events[-1].payload["unredacted_nonce"] = "changes-between-executions"
    difference = transcript_diff(
        "STREAM-TEST", render_transcript(first), render_transcript(second), "determinism"
    )
    assert "STREAM-TEST/determinism" in difference
    assert "unredacted_nonce" in difference


def test_unknown_assertions_and_escaping_paths_fail_loudly(tmp_path):
    with pytest.raises(ValueError, match="unknown assertions"):
        check_case(
            sample_case(expect={"golden": "test.json", "typo": True}), sample_evidence(), tmp_path
        )
    with pytest.raises(ValueError, match="inside"):
        fixture_path(tmp_path, "../outside.json")


def test_register_allows_uncovered_requirements_but_rejects_broken_links():
    requirement = Requirement(
        id="REQ-STREAM-01",
        tier="invariant",
        statement="Stream remains intact",
        enforced_by=["stream.py"],
        mutations=["skip_event"],
        cases=[],
    )
    assert Suite(requirements=[requirement], cases=[]).requirements[0].cases == []
    with pytest.raises(ValidationError, match="must link"):
        Suite(requirements=[requirement], cases=[sample_case()])
    with pytest.raises(ValidationError, match="unique"):
        Suite(requirements=[requirement, requirement], cases=[])


def test_requirement_tiers_are_not_interchangeable():
    with pytest.raises(ValidationError, match="threshold"):
        Requirement(id="REQ-SCOPE-01", tier="measured", statement="Measured quality")
    with pytest.raises(ValidationError, match="enforcement"):
        Requirement(id="REQ-STREAM-01", tier="invariant", statement="Invariant")


@pytest.mark.integration
async def test_public_http_capture_and_seeded_reconnect_agree(api):
    from zagent.evals.runner import capture_case, chaos_plan

    case = sample_case()
    reference = await capture_case(api.client, case)
    plan = chaos_plan(case, reference, seed=17)
    assert plan == chaos_plan(case, reference, seed=17)
    resumed = await capture_case(api.client, case, plan=plan)
    assert plan.disconnected_at_seq is not None
    assert render_transcript(reference) == render_transcript(resumed)


@pytest.mark.integration
async def test_broken_resume_is_detected_through_http(api, monkeypatch):
    from zagent.evals import runner

    case = sample_case()
    reference = await runner.capture_case(api.client, case)
    plan = runner.chaos_plan(case, reference, seed=17)
    monkeypatch.setattr(runner, "resume_headers", lambda cursor: {"Last-Event-ID": str(cursor + 1)})
    with pytest.raises(AssertionError, match="STREAM-TEST: noncontiguous SSE cursor"):
        await runner.capture_case(api.client, case, plan=plan)


def test_wilson_interval_keeps_small_samples_honest():
    from zagent.evals.statistics import wilson_interval

    assert wilson_interval(0, 0) == (0.0, 1.0)
    lower, upper = wilson_interval(1, 1)
    assert lower == pytest.approx(0.20655, abs=0.00001)
    assert upper == pytest.approx(1)
    lower, upper = wilson_interval(297, 300)
    assert lower == pytest.approx(0.971, abs=0.001)
    assert upper < 1
    with pytest.raises(ValueError):
        wilson_interval(2, 1)


def test_pass_power_uses_distinct_trials_and_reports_insufficient_samples():
    from zagent.evals.statistics import pass_power

    assert pass_power(1, 1, 3) is None
    assert pass_power(2, 4, 2) == pytest.approx(1 / 6)
    assert pass_power(1, 4, 2) == 0
    assert pass_power(5, 5, 3) == 1
    assert pass_power(3, 5, 1) == 0.6


def test_paired_comparison_matches_case_mode_and_seed():
    from zagent.evals.statistics import paired_comparison

    keys = [("case", "chaos", seed) for seed in range(6)]
    compared = paired_comparison(dict.fromkeys(keys, False), dict.fromkeys(keys, True))
    assert compared["matched"] == 6
    assert compared["regressed"] == 6
    assert compared["difference"] == -1
    assert compared["exact_p_value"] == pytest.approx(0.03125)
    unmatched = paired_comparison({("case", "chaos", 1): True}, {("case", "standard", 1): True})
    assert unmatched["matched"] == 0
    assert unmatched["unmatched_current"] == 1
    assert unmatched["exact_p_value"] is None


@pytest.mark.integration
async def test_shared_evaluator_updates_goldens_only_after_agreement(tmp_path, database_url):
    from zagent.evals.runner import evaluate_case

    results = await evaluate_case(
        sample_case(),
        tmp_path,
        database_url,
        chaos_trials=1,
        update_golden=True,
        seed=17,
    )
    assert len(results) == 2
    assert all(result.passed for result in results), [result.failures for result in results]
    assert results[0].executions == 2
    assert results[1].interruption["disconnected_at_seq"] is not None
    assert results[1].provenance.seed == 17
    assert results[0].transcript == (tmp_path / "goldens/test.json").read_text()


@pytest.mark.integration
async def test_live_capture_timeout_covers_reference_and_repeat(
    tmp_path, database_url, monkeypatch
):
    from zagent.evals import runner

    capture = runner.capture_case
    timeouts = []

    async def timed_capture(*args, **kwargs):
        timeouts.append(kwargs.get("timeout_seconds"))
        return await capture(*args, **kwargs)

    monkeypatch.setattr(runner, "capture_case", timed_capture)
    results = await runner.evaluate_case(sample_case(), tmp_path, database_url, mode="live")
    assert all(result.passed for result in results)
    assert timeouts == [600, 600]


@pytest.mark.integration
async def test_nondeterminism_blocks_golden_updates(tmp_path, database_url, monkeypatch):
    from zagent.evals import runner

    render = runner.render_transcript
    invocation = 0

    def unstable(evidence):
        nonlocal invocation
        invocation += 1
        return render(evidence) + f"nonce={invocation}\n"

    monkeypatch.setattr(runner, "render_transcript", unstable)
    results = await runner.evaluate_case(sample_case(), tmp_path, database_url, update_golden=True)
    assert not results[0].passed
    assert "nondeterministic transcript" in results[0].failures[0]
    assert "STREAM-TEST/determinism" in results[0].failures[0]
    assert not (tmp_path / "goldens/test.json").exists()


def sample_report(*, trials=1, measured=False):
    from zagent.evals.schema import Provenance, Report, TrialResult

    requirement = Requirement(
        id="REQ-STREAM-01",
        tier="measured" if measured else "invariant",
        statement="Transcript matches",
        cases=["STREAM-TEST"],
        enforced_by=[] if measured else ["events.py"],
        mutations=[] if measured else ["corrupt_projection"],
        threshold={"min_lower_bound": 0.9, "trials": 1} if measured else None,
    )
    clock = datetime.now(UTC)
    results = [
        TrialResult(
            case_id="STREAM-TEST",
            verification="standard",
            seed=seed,
            passed=True,
            transcript=render_transcript(sample_evidence()),
            duration_seconds=0.1,
            executions=2,
            provenance=Provenance(
                commit="test-commit",
                dirty_worktree=False,
                agent_implementation="ScriptedAgent",
                script_sha256="digest",
                seed=seed,
                clock=clock,
            ),
        )
        for seed in range(trials)
    ]
    return Report(
        created_at=clock,
        duration_seconds=0.2,
        requirements=[requirement],
        cases=[sample_case()],
        verifications=["standard"],
        results=results,
    )


def test_report_never_marks_an_uncovered_requirement_green():
    from zagent.evals.reporting import report_passes, requirement_rows, terminal_report

    report = sample_report()
    assert report_passes(report)
    report.requirements.append(
        Requirement(
            id="REQ-MISSING-01",
            tier="invariant",
            statement="No linked cases",
            enforced_by=["missing.py"],
            mutations=["disable_check"],
        )
    )
    assert not report_passes(report)
    assert requirement_rows(report)[-1]["status"] == "UNCOVERED"
    assert "REQ-MISSING-01" in terminal_report(report)
    assert "UNCOVERED" in terminal_report(report)


def test_measured_gate_uses_lower_bound_not_perfect_point_estimate():
    from zagent.evals.reporting import report_passes, requirement_rows

    single = sample_report(measured=True)
    assert requirement_rows(single)[0]["successes"] == 1
    assert not report_passes(single)
    enough = sample_report(trials=50, measured=True)
    assert report_passes(enough)
    enough.requirements[0].threshold.trials = 100
    assert requirement_rows(enough)[0]["status"] == "INSUFFICIENT"


def test_html_report_escapes_transcripts_and_roundtrips_results(tmp_path):
    from zagent.evals.reporting import write_report
    from zagent.evals.schema import Report

    report = sample_report()
    report.results[0].transcript = '<script>alert("untrusted")</script>'
    path = write_report(report, tmp_path, baseline=report)
    document = path.read_text()
    assert '<script>alert("untrusted")</script>' not in document
    assert "&lt;script&gt;" in document
    assert "Paired baseline comparison" in document
    assert Report.model_validate_json((tmp_path / "results.json").read_text()) == report


def test_scope_report_separates_precision_recall_codes_and_disagreements(tmp_path):
    from zagent.evals.reporting import scope_metrics, terminal_report, write_report
    from zagent.evals.schema import ScopeOutcome

    report = sample_report(trials=4)
    for result, expected, actual in zip(
        report.results,
        ["out_of_domain", "out_of_domain", None, None],
        ["out_of_domain", None, "out_of_domain", None],
        strict=True,
    ):
        result.scope = ScopeOutcome(expected=expected, actual=actual, gateway_calls=1)
    metrics = scope_metrics(report)
    assert metrics["precision"]["rate"] == 0.5
    assert metrics["recall"]["rate"] == 0.5
    assert metrics["acceptance"]["rate"] == 0.5
    assert metrics["reasons"][0]["precision"]["rate"] == 0.5
    assert metrics["disagreements"][0]["case_id"] == "STREAM-TEST"
    assert metrics["disagreements"][0]["outcomes"] == {"out_of_domain": 2, "allow": 2}
    assert "Refusal precision: 1/2" in terminal_report(report)
    document = write_report(report, tmp_path).read_text()
    assert "Disagreeing cases for review" in document
    assert "Reason codes" in document
    assert "In-scope acceptance" in document


def test_duplicate_trials_are_rejected():
    from zagent.evals.schema import Report

    data = sample_report().model_dump()
    data["results"] *= 2
    with pytest.raises(ValidationError, match="inflate"):
        Report.model_validate(data)


@pytest.mark.integration
async def test_broken_resume_turns_req_stream_02_red(tmp_path, database_url, monkeypatch):
    from zagent.evals import runner
    from zagent.evals.reporting import report_passes, requirement_rows

    await runner.evaluate_case(sample_case(), tmp_path, database_url, update_golden=True)
    monkeypatch.setattr(runner, "resume_headers", lambda cursor: {"Last-Event-ID": str(cursor + 1)})
    results = await runner.evaluate_case(
        sample_case(),
        tmp_path,
        database_url,
        standard_trials=0,
        chaos_trials=1,
        seed=7,
    )
    report = sample_report()
    report.results = results
    report.verifications = ["chaos"]
    report.requirements[0].id = "REQ-STREAM-02"
    report.requirements[0].verification = "chaos"
    assert not report_passes(report)
    assert requirement_rows(report)[0]["status"] == "FAIL"
    assert "noncontiguous SSE cursor" in results[0].failures[0]


@pytest.mark.integration
async def test_corrupted_reducer_produces_case_named_golden_diff(
    tmp_path, database_url, monkeypatch
):
    from zagent import events
    from zagent.evals import runner

    await runner.evaluate_case(sample_case(), tmp_path, database_url, update_golden=True)
    original = events.reduce_event

    def corrupted(state, event):
        result = original(state, event)
        if event.type == "text_delta":
            result.messages[-1].text += "CORRUPTED"
        return result

    monkeypatch.setattr(events, "reduce_event", corrupted)
    monkeypatch.setattr(runner, "reduce_event", corrupted)
    results = await runner.evaluate_case(sample_case(), tmp_path, database_url)
    assert not results[0].passed
    assert "--- STREAM-TEST/golden" in results[0].failures[0]
    assert "CORRUPTED" in results[0].failures[0]


@pytest.mark.integration
async def test_cli_shares_results_filtering_updates_baselines_and_exit_codes(
    tmp_path, database_url
):
    import asyncio
    import sys

    from zagent.evals.schema import Report

    root = tmp_path / "suite"
    (root / "cases").mkdir(parents=True)
    requirement = sample_report().requirements[0].model_dump(mode="json")
    (root / "requirements.yaml").write_text(yaml.safe_dump([requirement]))
    (root / "cases/test.yaml").write_text(yaml.safe_dump({"cases": [sample_case().model_dump()]}))
    output = tmp_path / "report"

    async def invoke(*arguments):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "zagent.cli",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode() + stderr.decode()

    arguments = [
        "evals",
        "--root",
        str(root),
        "--database-url",
        database_url,
        "--output",
        str(output),
    ]
    code, text = await invoke(*arguments, "--update-golden")
    assert code == 0, text
    assert "Golden update requested" in text
    assert (root / "goldens/test.json").is_file()
    baseline = tmp_path / "baseline.json"
    baseline.write_text((output / "results.json").read_text())
    code, text = await invoke(
        *arguments,
        "--no-chaos",
        "--trials",
        "2",
        "--filter",
        "STREAM-TEST",
        "--baseline",
        str(baseline),
    )
    assert code == 0, text
    report = Report.model_validate_json((output / "results.json").read_text())
    assert len(report.results) == 2
    assert "1 paired trials" in text
    code, text = await invoke(
        "report", "--input", str(output / "results.json"), "--output", str(tmp_path / "rendered")
    )
    assert code == 0, text
    assert (tmp_path / "rendered/index.html").is_file()
    code, text = await invoke(*arguments, "--mode", "live")
    assert code == 1
    assert "requires --filter and --no-chaos" in text
    code, text = await invoke(*arguments, "--filter", "DOES-NOT-EXIST")
    assert code == 1
    assert "No cases match" in text
    uncovered = {**requirement, "id": "REQ-MISSING-01", "cases": []}
    (root / "requirements.yaml").write_text(yaml.safe_dump([requirement, uncovered]))
    code, text = await invoke(*arguments, "--no-chaos")
    assert code == 1
    assert "UNCOVERED" in text


def test_unknown_excluded_event_is_not_silently_ignored(tmp_path):
    case = sample_case(expect={"golden": "test.json", "events_exclude": ["typo"]})
    with pytest.raises(ValueError, match="unknown event types"):
        check_case(case, sample_evidence(), tmp_path)
