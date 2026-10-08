import os
import subprocess
import sys

import pytest
from zagent.evals.mutations import ZONE_MUTATIONS
from zagent.faults import MUTATIONS, configured


def mutation_environment(name="tokenizer_off"):
    target = "postgresql://localhost/zagent_mutation_" + "a" * 32
    return {
        **os.environ,
        "ZAGENT_MUTATION": name,
        "ZAGENT_TEST_MODE": "mutation",
        "ZAGENT_LLM_MODE": "replay",
        "DATABASE_URL": target,
        "ZAGENT_TEST_DATABASE_URL": target,
    }


@pytest.mark.parametrize("name", MUTATIONS)
def test_every_mutation_requires_explicit_test_configuration(name):
    environment = mutation_environment(name)
    environment.pop("ZAGENT_TEST_MODE")
    result = subprocess.run(
        [sys.executable, "-c", "import zagent"],
        env=environment,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "Mutation flags require" in result.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"ZAGENT_LLM_MODE": "live"},
        {"DATABASE_URL": "postgresql://localhost/zagent"},
        {
            "DATABASE_URL": "postgresql://localhost/zagent_test",
            "ZAGENT_TEST_DATABASE_URL": "postgresql://localhost/zagent_test",
        },
        {"ZAGENT_MUTATION": "unknown"},
    ],
)
def test_mutations_reject_live_mode_shared_databases_and_unknown_flags(overrides):
    result = subprocess.run(
        [sys.executable, "-c", "import zagent"],
        env={**mutation_environment(), **overrides},
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "Mutation flags require" in result.stderr


def test_mutation_target_must_match_the_opened_database(monkeypatch):
    for name, value in mutation_environment().items():
        monkeypatch.setenv(name, value)
    assert configured() == "tokenizer_off"
    with pytest.raises(RuntimeError, match="dedicated disposable database"):
        configured("postgresql://localhost/zagent")


def test_ordinary_configuration_has_no_mutations(monkeypatch):
    monkeypatch.delenv("ZAGENT_MUTATION", raising=False)
    assert configured("postgresql://localhost/zagent") is None


@pytest.mark.parametrize(
    "name,expression",
    [
        (
            "tokenizer_off",
            "from zagent.privacy import Raw,SessionTokens,Detector; "
            "assert SessionTokens(Detector()).tokenize(Raw(value='NGC-0041872'),"
            "path='user_message').value == 'NGC-0041872'",
        ),
        (
            "tripwire_off",
            "from zagent.evals.privacy import fixture_tripwire; "
            "fixture_tripwire()({'content':'NGC-0041872'})",
        ),
        (
            "guard_off",
            "import asyncio; from zagent.scope import ScopeGuard; "
            "assert asyncio.run(ScopeGuard(None).classify([])) is None",
        ),
        (
            "validator_off",
            "from zagent.drafts import DraftContent,validate_draft; "
            "assert validate_draft(DraftContent(app_id='somatic-snv'),[],[]) == []",
        ),
        (
            "submit_tool_on",
            "from zagent.tools import TOOL_DEFINITIONS; "
            "assert 'submit_job' in {tool['function']['name'] for tool in TOOL_DEFINITIONS}",
        ),
    ],
)
def test_mutations_reach_the_owning_mechanism(name, expression):
    result = subprocess.run(
        [sys.executable, "-c", expression],
        env=mutation_environment(name),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_mutation_gateway_cannot_enable_provider_access():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from zagent.llm import LlmGateway; "
            "LlmGateway(Path('.'),mode='live')",
        ],
        env=mutation_environment(),
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "cannot enable model provider access" in result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("name", [name for name in MUTATIONS if name not in ZONE_MUTATIONS])
async def test_paired_mutation_experiments_detect_the_removed_guarantee(database_url, name):
    from pathlib import Path

    from zagent.evals.mutations import compare_mutation, run_probe

    root = Path(__file__).parents[3] / "evals"
    control = await run_probe(name, database_url, root, mutate=False)
    mutant = await run_probe(name, database_url, root, mutate=True)
    result = compare_mutation(name, control, mutant)
    assert result["status"] == "detected", result
    assert control["healthy"] and mutant["healthy"]


def test_crashes_and_missing_controls_do_not_count_as_detected_mutations():
    from zagent.evals.mutations import compare_mutation

    control = {"healthy": True, "requirements": {"REQ-PHI-02": True}}
    crashed = {"healthy": False, "requirements": {"REQ-PHI-02": False}}
    assert compare_mutation("tokenizer_off", control, crashed)["status"] == "invalid"
    assert compare_mutation("tokenizer_off", control, control)["status"] == "survived"


def test_mutation_report_fails_survivors_and_keeps_paired_observations(tmp_path):
    from datetime import UTC, datetime

    from zagent.evals.mutations import compare_mutation, evidence_report
    from zagent.evals.reporting import report_passes, terminal_report, write_report

    control = {"healthy": True, "requirements": {"REQ-PHI-02": True}}
    result = evidence_report(
        {
            "created_at": datetime.now(UTC).isoformat(),
            "seconds": 1,
            "provenance": {"commit": None, "dirty_worktree": True},
            "results": [compare_mutation("tokenizer_off", control, control)],
        }
    )
    assert not report_passes(result)
    document = write_report(result, tmp_path).read_text()
    assert "survived" in document and "Enforcement mutations" in document
    assert "REQ-PHI-02" in document
    assert "2 probe executions" in terminal_report(result)
    assert "Probe executions" in document and "HTTP executions" not in document
