from collections import Counter
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined, select_autoescape

from zagent.evals.schema import Report
from zagent.evals.statistics import paired_comparison, pass_power, wilson_interval


def requirement_rows(report: Report) -> list[dict]:
    selected = {case.id for case in report.cases}
    rows = []
    for requirement in report.requirements:
        cases = selected & set(requirement.cases)
        outcomes = [
            result
            for result in report.results
            if result.case_id in cases and result.verification == requirement.verification
        ]
        successes = sum(result.passed for result in outcomes)
        trials = len(outcomes)
        counts = Counter(result.case_id for result in outcomes)
        lower, upper = wilson_interval(successes, trials)
        if not requirement.cases:
            status = "UNCOVERED"
        elif not cases:
            status = "FILTERED"
        elif requirement.verification not in report.verifications:
            status = "NOT SELECTED"
        elif not trials or any(not counts[case_id] for case_id in cases):
            status = "UNCOVERED"
        elif requirement.tier == "invariant":
            status = "PASS" if successes == trials else "FAIL"
        elif any(counts[case_id] < requirement.threshold.trials for case_id in cases):
            status = "INSUFFICIENT"
        else:
            status = "PASS" if lower >= requirement.threshold.min_lower_bound else "FAIL"
        estimates = [
            pass_power(
                sum(result.passed for result in outcomes if result.case_id == case_id),
                counts[case_id],
                report.pass_streak,
            )
            for case_id in sorted(cases)
        ]
        streak_estimate = (
            sum(estimates) / len(estimates)
            if estimates and all(estimate is not None for estimate in estimates)
            else None
        )
        rows.append(
            {
                "requirement": requirement,
                "status": status,
                "successes": successes,
                "trials": trials,
                "lower": lower,
                "upper": upper,
                "pass_power": streak_estimate,
                "cases": sorted(cases),
                "selected_case_count": len(cases),
            }
        )
    return rows


def report_passes(report: Report) -> bool:
    rows = requirement_rows(report)
    return (
        bool(rows)
        and any(row["status"] == "PASS" for row in rows)
        and all(row["status"] in {"PASS", "FILTERED", "NOT SELECTED"} for row in rows)
    )


def compare_reports(report: Report, baseline: Report) -> dict:
    def outcomes(source: Report):
        return {
            (result.case_id, result.verification, result.seed): result.passed
            for result in source.results
        }

    return paired_comparison(outcomes(report), outcomes(baseline))


def percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def terminal_report(report: Report, baseline: Report | None = None) -> str:
    lines = [f"{'Requirement':<20} {'Tier':<10} {'Gate':<13} {'Trials':<10} 95% Wilson CI"]
    for row in requirement_rows(report):
        requirement = row["requirement"]
        interval = (
            f"[{percentage(row['lower'])}, {percentage(row['upper'])}]" if row["trials"] else "n/a"
        )
        count = f"{row['successes']}/{row['trials']}"
        lines.append(
            f"{requirement.id:<20} {requirement.tier:<10} {row['status']:<13} "
            f"{count:<10} {interval}"
        )
        lines.append(f"  {requirement.statement}")
        lines.append(f"  mean per-case pass^{report.pass_streak}: {percentage(row['pass_power'])}")
    failures = sum(not result.passed for result in report.results)
    executions = sum(result.executions for result in report.results)
    lines.append(
        f"\n{len(report.requirements)} requirements, {len(report.results)} trials, "
        f"{failures} failed trials; {executions} HTTP case executions "
        f"in {report.duration_seconds:.2f}s."
    )
    if baseline:
        paired = compare_reports(report, baseline)
        lines.append(
            f"Baseline: {paired['matched']} paired trials, {paired['improved']} improved, "
            f"{paired['regressed']} regressed; exact p={paired['exact_p_value']}. "
            f"Unpaired: {paired['unmatched_current']} current, "
            f"{paired['unmatched_baseline']} baseline."
        )
    seen = set()
    for result in report.results:
        for failure in result.failures:
            if (result.case_id, failure) not in seen:
                lines.append(
                    f"\n{result.case_id} [{result.verification}, seed={result.seed}]\n{failure}"
                )
                seen.add((result.case_id, failure))
    return "\n".join(lines)


def write_report(report: Report, output: Path, baseline: Report | None = None) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    environment = Environment(
        autoescape=select_autoescape(default_for_string=True),
        undefined=StrictUndefined,
    )
    environment.filters["percentage"] = percentage
    template = environment.from_string(files("zagent.evals").joinpath("report.html").read_text())
    grouped = [
        {
            "case": case,
            "results": [result for result in report.results if result.case_id == case.id],
        }
        for case in report.cases
    ]
    passed = sum(result.passed for result in report.results)
    document = template.render(
        report=report,
        rows=requirement_rows(report),
        cases=grouped,
        paired=compare_reports(report, baseline) if baseline else None,
        passed=passed,
        gate=report_passes(report),
        success_share=100 * passed / len(report.results) if report.results else 0,
    )
    (output / "results.json").write_text(report.model_dump_json(indent=2) + "\n")
    path = output / "index.html"
    path.write_text(document)
    return path
