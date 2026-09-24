import hashlib
from collections import Counter
from importlib.resources import files
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined, select_autoescape

from zagent.evals.schema import Report
from zagent.evals.statistics import paired_comparison, pass_power, wilson_interval
from zagent.scope import REFUSAL_MESSAGES


def scope_metrics(report: Report) -> dict | None:
    results = [result for result in report.results if result.scope is not None]
    if not results:
        return None

    def estimate(successes: int, total: int) -> dict:
        lower, upper = wilson_interval(successes, total)
        return {
            "successes": successes,
            "total": total,
            "rate": successes / total if total else None,
            "lower": lower,
            "upper": upper,
        }

    scopes = [result.scope for result in results]
    true_positive = sum(
        not item.error and item.expected is not None and item.actual is not None for item in scopes
    )
    refused = sum(item.actual is not None and not item.error for item in scopes)
    out_of_scope = sum(item.expected is not None for item in scopes)
    accepted = sum(
        not item.error and item.expected is None and item.actual is None for item in scopes
    )
    reasons = []
    for code in REFUSAL_MESSAGES:
        expected = sum(item.expected == code for item in scopes)
        predicted = sum(item.actual == code and not item.error for item in scopes)
        correct = sum(
            item.expected == code and item.actual == code and not item.error for item in scopes
        )
        reasons.append(
            {
                "code": code,
                "expected": expected,
                "predicted": predicted,
                "precision": estimate(correct, predicted),
                "recall": estimate(correct, expected),
            }
        )
    buckets = []
    disagreements = []
    for bucket in sorted({case.bucket for case in report.cases if case.bucket}):
        identities = {case.id for case in report.cases if case.bucket == bucket}
        outcomes = [result.scope for result in results if result.case_id in identities]
        correct = sum(
            not item.error and (item.expected is None) == (item.actual is None) for item in outcomes
        )
        buckets.append({"bucket": bucket, **estimate(correct, len(outcomes))})
    for case in report.cases:
        outcomes = Counter(
            "error" if result.scope.error else result.scope.actual or "allow"
            for result in results
            if result.case_id == case.id
        )
        if len(outcomes) > 1:
            disagreements.append(
                {
                    "case_id": case.id,
                    "bucket": case.bucket,
                    "request": case.conversation_turns[0].user,
                    "expected": case.expect.get("refusal"),
                    "outcomes": dict(outcomes),
                }
            )
    return {
        "trials": len(results),
        "errors": sum(item.error for item in scopes),
        "precision": estimate(true_positive, refused),
        "recall": estimate(true_positive, out_of_scope),
        "acceptance": estimate(accepted, len(scopes) - out_of_scope),
        "reason_accuracy": estimate(
            sum(not item.error and item.actual == item.expected for item in scopes), len(scopes)
        ),
        "reasons": reasons,
        "buckets": buckets,
        "disagreements": disagreements,
        "gateway_calls": sum(item.gateway_calls for item in scopes),
        "provider_calls": sum(item.provider_calls for item in scopes),
    }


def slot_rows(report: Report) -> list[dict]:
    results = [result for result in report.results if result.slot_app]
    rows = []
    for app in sorted({result.slot_app for result in results}):
        trials = [result for result in results if result.slot_app == app]
        successes = sum(result.passed for result in trials)
        lower, upper = wilson_interval(successes, len(trials))
        rows.append(
            {
                "app": app,
                "successes": successes,
                "trials": len(trials),
                "lower": lower,
                "upper": upper,
                "mean_turns": sum(result.slot_turns for result in trials) / len(trials),
                "simulator_model": trials[0].provenance.simulator_model,
            }
        )
    return rows


def adversarial_rows(report: Report) -> list[dict]:
    rows = []
    selected = [result for result in report.results if result.adversarial]
    for family, ingress in sorted(
        {(item.adversarial["family"], item.adversarial["ingress"]) for item in selected}
    ):
        trials = [
            item
            for item in selected
            if (item.adversarial["family"], item.adversarial["ingress"]) == (family, ingress)
        ]
        successes = sum(item.passed for item in trials)
        lower, upper = wilson_interval(successes, len(trials))
        rows.append(
            {
                "family": family,
                "ingress": ingress,
                "successes": successes,
                "trials": len(trials),
                "lower": lower,
                "upper": upper,
                "exposed": sum(
                    item.adversarial.get("payload_reached_model", False) for item in trials
                ),
                "cases": sorted({item.case_id for item in trials}),
            }
        )
    return rows


def detector_rows(report: Report) -> list[dict]:
    rows = []
    identifiers = {case.id for case in report.cases if case.agent.startswith("detector:")}
    for label, adversarial in (("Literal identifiers", False), ("Obfuscated identifiers", True)):
        trials = [
            item
            for item in report.results
            if item.case_id in identifiers and bool(item.adversarial) == adversarial
        ]
        if not trials:
            continue
        successes = sum(item.passed for item in trials)
        lower, upper = wilson_interval(successes, len(trials))
        rows.append(
            {
                "label": label,
                "successes": successes,
                "trials": len(trials),
                "lower": lower,
                "upper": upper,
            }
        )
    return rows


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
        successes = sum(
            result.requirement_outcomes.get(requirement.id, result.passed) for result in outcomes
        )
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
                sum(
                    result.requirement_outcomes.get(requirement.id, result.passed)
                    for result in outcomes
                    if result.case_id == case_id
                ),
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
        and (
            report.matrix is None
            or all(
                outcome["passed"] for cell in report.matrix["cells"] for outcome in cell["outcomes"]
            )
        )
        and (report.privacy_scan is None or not report.privacy_scan.violations)
        and any(row["status"] == "PASS" for row in rows)
        and all(row["status"] in {"PASS", "FILTERED", "NOT SELECTED"} for row in rows)
    )


def review_findings(report: Report, path: Path) -> dict:
    from zagent.llm import canonical_json

    raw = path.read_text()
    baseline = yaml.safe_load(raw)
    recognized, regressions = set(), []
    for row in requirement_rows(report):
        if row["status"] in {"PASS", "FILTERED", "NOT SELECTED"}:
            continue
        requirement = row["requirement"]
        if row["status"] != "FAIL" or requirement.tier == "invariant":
            regressions.append(f"{requirement.id}: {row['status']}")
            continue
        failed_results = [
            result
            for result in report.results
            if result.case_id in row["cases"]
            and result.verification == requirement.verification
            and not result.requirement_outcomes.get(requirement.id, result.passed)
        ]
        if not failed_results:
            regressions.append(f"{requirement.id}: lower-bound gate failed without a known failure")
        for result in failed_results:
            finding = baseline["findings"].get(result.case_id, {})
            known = (
                result.provenance.mode == "replay"
                and result.seed == baseline["seed"]
                and result.provenance.model in {None, baseline["model"]}
                and result.provenance.prompt_version in {None, baseline["prompt_version"]}
                and finding.get("requirement") == requirement.id
                and finding.get("failure_sha256")
                == hashlib.sha256(canonical_json(result.failures).encode()).hexdigest()
            )
            if known:
                recognized.add(result.case_id)
            else:
                regressions.append(f"{result.case_id}: unrecognized {requirement.id} failure")
    if report.privacy_scan and report.privacy_scan.violations:
        regressions.append("Privacy corpus contains identifiers")
    return {
        "version": baseline["version"],
        "source": path.name,
        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "review_status": baseline["review_status"],
        "known_cases": sorted(recognized),
        "regressions": regressions,
        "passed": not regressions,
        "quality_passed": report_passes(report),
    }


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
    if report.mutations:
        lines.insert(
            0,
            "\n".join(
                [
                    "MUTATION           STATUS     DETECTED BY",
                    *(
                        f"{item['name']:<18} {item['status']:<10} "
                        f"{', '.join(item['detected_by']) or 'none'}"
                        for item in report.mutations["results"]
                    ),
                    "",
                ]
            ),
        )
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
    execution_kind = "probe" if report.mutations else "HTTP case"
    lines.append(
        f"\n{len(report.requirements)} requirements, {len(report.results)} trials, "
        f"{failures} failed trials; {executions} {execution_kind} executions "
        f"in {report.duration_seconds:.2f}s."
    )
    scope = scope_metrics(report)
    slots = slot_rows(report)
    if slots:
        lines.append("\nSimulated-user convergence by application (95% Wilson CI)")
        for row in slots:
            lines.append(
                f"  {row['app']}: {row['successes']}/{row['trials']} "
                f"[{percentage(row['lower'])}, {percentage(row['upper'])}]"
            )
    if report.privacy_scan is not None:
        scan = report.privacy_scan
        requests = sum(result.privacy_requests for result in report.results)
        hits = sum(result.tripwire_hits for result in report.results)
        _lower, upper = wilson_interval(hits, requests)
        lines.append(
            f"\nPrivacy corpus: {scan.cassettes} cassettes, {scan.goldens} goldens, "
            f"{scan.stored_events} stored events, {scan.recorded_requests} recorded requests; "
            f"{len(scan.violations)} identifier violations."
        )
        lines.append(
            f"Tripwire: {hits} hits / {requests} captured requests; "
            f"95% violation-rate upper bound {percentage(upper)}."
        )
        lines.extend(f"  {violation}" for violation in scan.violations[:20])
    if scope:
        lines.append("\nScope classification (95% Wilson intervals)")
        for label, key in (
            ("Refusal precision", "precision"),
            ("Refusal recall", "recall"),
            ("In-scope acceptance", "acceptance"),
            ("Exact reason/allow", "reason_accuracy"),
        ):
            metric = scope[key]
            interval = (
                f"[{percentage(metric['lower'])}, {percentage(metric['upper'])}]"
                if metric["total"]
                else "n/a"
            )
            lines.append(
                f"  {label}: {metric['successes']}/{metric['total']} "
                f"{percentage(metric['rate'])} {interval}"
            )
        lines.append("  Per-reason precision / recall:")
        for reason in scope["reasons"]:
            precision, recall = reason["precision"], reason["recall"]
            lines.append(
                f"    {reason['code']}: {precision['successes']}/{precision['total']} "
                f"{percentage(precision['rate'])} / {recall['successes']}/{recall['total']} "
                f"{percentage(recall['rate'])}"
            )
        lines.append(
            f"  Audit: {scope['gateway_calls']} guard calls; "
            f"{scope['provider_calls']} provider calls this run; {scope['errors']} errors."
        )
        lines.append(f"  Disagreeing cases for review: {len(scope['disagreements'])}")
        for case in scope["disagreements"]:
            lines.append(f"    {case['case_id']} ({case['bucket']}): {case['outcomes']}")
        lines.append(
            "  Replay reuses individually recorded samples; it is not fresh model sampling."
        )
    if baseline:
        paired = compare_reports(report, baseline)
        lines.append(
            f"Baseline: {paired['matched']} paired trials, {paired['improved']} improved, "
            f"{paired['regressed']} regressed; exact p={paired['exact_p_value']}. "
            f"Unpaired: {paired['unmatched_current']} current, "
            f"{paired['unmatched_baseline']} baseline."
        )
    if report.judge_calibration:
        calibration = report.judge_calibration
        lines.append(
            f"Judge reference agreement: {calibration['correct']}/{calibration['total']} "
            f"({calibration['label_source']}); human calibration: "
            f"{'complete' if calibration['human_calibrated'] else 'PENDING'}."
        )
    if report.findings_review:
        review = report.findings_review
        lines.append(
            f"Known findings: {len(review['known_cases'])}; "
            f"unrecognized regressions: {len(review['regressions'])}. "
            "Quality gates above are unchanged."
        )
        lines.extend(review["regressions"])
    for row in detector_rows(report):
        lines.append(
            f"{row['label']}: {row['successes']}/{row['trials']} "
            f"[{percentage(row['lower'])}, {percentage(row['upper'])}]"
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
    outcomes = (
        [outcome["passed"] for cell in report.matrix["cells"] for outcome in cell["outcomes"]]
        if report.matrix
        else [result.passed for result in report.results]
    )
    passed = sum(outcomes)
    trials = len(outcomes)
    captured_requests = sum(result.privacy_requests for result in report.results)
    privacy_hits = sum(result.tripwire_hits for result in report.results)
    _lower, privacy_upper = wilson_interval(privacy_hits, captured_requests)
    document = template.render(
        report=report,
        rows=requirement_rows(report),
        cases=grouped,
        paired=compare_reports(report, baseline) if baseline else None,
        passed=passed,
        trials=trials,
        gate=report_passes(report),
        success_share=100 * passed / trials if trials else 0,
        scope=scope_metrics(report),
        slots=slot_rows(report),
        adversarial=adversarial_rows(report),
        detectors=detector_rows(report),
        related_reports=[
            {"title": title, "path": relative}
            for title, relative in (
                ("Mutation proof", "plan10/mutations/index.html"),
                ("Model matrix", "plan10/matrix/index.html"),
                ("Nightly drift", "plan10/nightly/index.html"),
            )
            if (output / relative).is_file()
        ],
        privacy_requests=captured_requests,
        privacy_hits=privacy_hits,
        privacy_upper=privacy_upper,
    )
    (output / "results.json").write_text(report.model_dump_json(indent=2) + "\n")
    path = output / "index.html"
    path.write_text(document)
    return path
