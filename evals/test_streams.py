from pathlib import Path

import pytest
from zagent.evals.reporting import report_passes, terminal_report, write_report
from zagent.evals.runner import evaluate_suite
from zagent.evals.schema import load_suite

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parent
CASES = load_suite(ROOT).cases


@pytest.fixture(scope="session")
async def stream_report(database_url):
    report = await evaluate_suite(ROOT, database_url)
    write_report(report, ROOT.parent / "docs/evals")
    return report


@pytest.mark.parametrize(
    "case_id",
    [
        case.id
        for case in CASES
        if not case.agent.startswith(("guard:", "detector:")) and case.simulator is None
    ],
)
async def test_case_golden_transcript(stream_report, case_id):
    result = next(
        result
        for result in stream_report.results
        if result.case_id == case_id and result.verification == "standard"
    )
    assert result.passed, "\n".join(result.failures)


@pytest.mark.chaos
@pytest.mark.parametrize(
    "case_id,seed",
    [
        pytest.param(case.id, seed, id=f"{case.id}-seed-{seed:02d}")
        for case in CASES
        if not case.agent.startswith(("guard:", "detector:")) and case.simulator is None
        for seed in range(10)
    ],
)
async def test_case_chaos_resume(stream_report, case_id, seed):
    result = next(
        (
            result
            for result in stream_report.results
            if result.case_id == case_id and result.verification == "chaos" and result.seed == seed
        ),
        None,
    )
    assert result is not None, terminal_report(stream_report)
    assert result.passed, f"{case_id}, seed={seed}\n" + "\n".join(result.failures)


async def test_all_registered_requirements_are_covered(stream_report):
    assert report_passes(stream_report), terminal_report(stream_report)


def test_scope_samples_are_independent_and_structured(stream_report):
    scoped = [result for result in stream_report.results if result.scope]
    assert len(scoped) == 3000
    assert all(result.scope.structured for result in scoped)
    assert all(
        result.scope.gateway_calls == 1 and result.scope.provider_calls == 0 for result in scoped
    )
    for case in CASES:
        if case.agent.startswith("guard:"):
            assert {
                result.provenance.independent_sample
                for result in scoped
                if result.case_id == case.id
            } == set(range(10))
