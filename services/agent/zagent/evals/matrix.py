import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from zagent.evals.adversarial import PROMPTS, evaluate_adversarial
from zagent.evals.budget import ProviderBudget
from zagent.evals.judges import JUDGE_MODEL, evaluate_calibration
from zagent.evals.reporting import requirement_rows, write_report
from zagent.evals.runner import git_provenance
from zagent.evals.schema import Report, load_suite
from zagent.evals.statistics import paired_comparison
from zagent.llm import canonical_json


def configuration(root: Path):
    value = yaml.safe_load((root / "matrix.yaml").read_text())
    if set(value["prompts"]) != set(PROMPTS) or value["baseline"] not in value["models"]:
        raise ValueError("Matrix requires both registered prompts and a baseline model")
    if not 1 <= value["trials"] <= 3 or not 0 < value["max_budget_usd"] <= 2:
        raise ValueError("Matrix trial or cost limit is outside the approved bounds")
    if len(value["cases"]) != len(set(value["cases"])):
        raise ValueError("Matrix cases must be unique for paired comparisons")
    selected = {case.id: case for case in load_suite(root).cases}
    if any(
        identity not in selected
        or selected[identity].adversarial is None
        or selected[identity].agent != "llm:default"
        for identity in value["cases"]
    ):
        raise ValueError("Matrix cases must be registered model-driven adversarial cases")
    return value


def budget_for(root, ledger, dollars):
    spec = configuration(root)
    if dollars > spec["max_budget_usd"]:
        raise ValueError("Requested budget exceeds the matrix's approved maximum")
    return ProviderBudget(
        ledger,
        dollars=dollars,
        prices={entry["model"]: entry["pricing"] for entry in spec["models"].values()},
        max_calls=spec["max_provider_calls"],
    )


async def verify_prices(spec):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        advertised = {entry["id"]: entry for entry in response.json()["data"]}
    for entry in spec["models"].values():
        current = advertised.get(entry["model"])
        if current is None or "tools" not in current.get("supported_parameters", []):
            raise ValueError("A matrix model is missing or does not advertise tool support")
        for kind in ("prompt", "completion"):
            if Decimal(current["pricing"][kind]) > Decimal(entry["pricing"][kind]):
                raise ValueError("Advertised provider price exceeds the configured budget price")


def paired_cells(cells, baseline_name):
    def outcomes(cell):
        return {(item["case_id"], item["seed"]): item["passed"] for item in cell["outcomes"]}

    comparisons = []
    by_key = {(cell["model_key"], cell["prompt_version"]): cell for cell in cells}
    for cell in cells:
        for label, baseline in (
            ("model", by_key.get((baseline_name, cell["prompt_version"]))),
            ("prompt", by_key.get((cell["model_key"], "baseline"))),
        ):
            if baseline is not None and baseline is not cell:
                comparisons.append(
                    {
                        "kind": label,
                        "current": cell["label"],
                        "baseline": baseline["label"],
                        **paired_comparison(outcomes(cell), outcomes(baseline)),
                    }
                )
    return comparisons


async def evaluate_matrix(
    root,
    database_url,
    output,
    *,
    mode="replay",
    seed=0,
    budget_usd=None,
    ledger=None,
    baseline=None,
):
    if not urlsplit(database_url).path.endswith("_test"):
        raise ValueError("Model matrix requires a dedicated test database")
    spec = configuration(root)
    if mode != "replay" and (budget_usd is None or ledger is None):
        raise ValueError("Paid matrix runs require --budget-usd and a persistent --budget-ledger")
    if mode not in {"record", "replay"}:
        raise ValueError("Matrix runs use record or keyless replay so failures remain reproducible")
    budget = budget_for(root, ledger, budget_usd) if mode == "record" else None
    if budget:
        await verify_prices(spec)
    suite = load_suite(root)
    selected = [case for case in suite.cases if case.id in spec["cases"]]
    commit, dirty = git_provenance(root)
    started, clock = time.monotonic(), datetime.now(UTC)
    calibration = await evaluate_calibration(
        root, database_url, mode=mode, budget=budget, seed=seed
    )
    cells, reports = [], []
    for key, route in spec["models"].items():
        for prompt in spec["prompts"]:
            results = []
            for case in selected:
                measured = await evaluate_adversarial(
                    case,
                    root,
                    database_url,
                    mode=mode,
                    trials=spec["trials"],
                    seed=seed,
                    commit=commit,
                    dirty=dirty,
                    record_missing=True,
                    model=route["model"],
                    prompt_version=prompt,
                    budget=budget,
                )
                results.extend(measured)
                status = "passed" if all(item.passed for item in measured) else "finding"
                print(
                    f"{key}/{prompt} {case.id}: {status}",
                    flush=True,
                )
            report = Report(
                created_at=clock,
                duration_seconds=sum(item.duration_seconds for item in results),
                requirements=suite.requirements,
                cases=selected,
                results=results,
                verifications=["standard"],
                judge_calibration=calibration,
            )
            destination = output / key / prompt
            write_report(report, destination)
            cells.append(
                {
                    "label": f"{key}/{prompt}",
                    "model_key": key,
                    "model": route["model"],
                    "prompt_version": prompt,
                    "prompt_hash": hashlib.sha256(PROMPTS[prompt].encode()).hexdigest(),
                    "path": f"{key}/{prompt}/index.html",
                    "passed": sum(item.passed for item in results),
                    "trials": len(results),
                    "gates": [
                        {"id": row["requirement"].id, "status": row["status"]}
                        for row in requirement_rows(report)
                        if row["status"] != "FILTERED"
                    ],
                    "outcomes": [
                        {
                            "case_id": item.case_id,
                            "seed": item.seed,
                            "passed": item.passed,
                            "requirements": item.requirement_outcomes,
                            "failures": item.failures,
                        }
                        for item in results
                    ],
                }
            )
            reports.append(report)
    matrix = {
        "version": spec["version"],
        "configuration_hash": hashlib.sha256(canonical_json(spec).encode()).hexdigest(),
        "models": spec["models"],
        "prompts": spec["prompts"],
        "seed": seed,
        "trials_per_case": spec["trials"],
        "created_at": clock.isoformat(),
        "mode": mode,
        "commit": commit,
        "dirty_worktree": dirty,
        "seconds": time.monotonic() - started,
        "cells": cells,
        "comparisons": paired_cells(cells, spec["baseline"]),
        "judge_model": JUDGE_MODEL,
        "budget": json.loads(ledger.read_text())
        if budget and ledger.exists()
        else {"provider_calls": 0},
    }
    if baseline is not None:
        previous = {cell["label"]: cell for cell in (baseline.matrix or {}).get("cells", [])}
        matrix["drift_comparisons"] = [
            {
                "current": cell["label"],
                "baseline": cell["label"],
                **paired_comparison(
                    {(item["case_id"], item["seed"]): item["passed"] for item in cell["outcomes"]},
                    {
                        (item["case_id"], item["seed"]): item["passed"]
                        for item in previous[cell["label"]]["outcomes"]
                    },
                ),
            }
            for cell in cells
            if cell["label"] in previous
        ]
        matrix["baseline_sha256"] = hashlib.sha256(baseline.model_dump_json().encode()).hexdigest()
    summary = reports[0].model_copy(
        update={"duration_seconds": matrix["seconds"], "matrix": matrix}
    )
    write_report(summary, output)
    return summary


def matrix_regressions(report):
    failures = []
    for cell in report.matrix["cells"]:
        for outcome in cell["outcomes"]:
            if not outcome["requirements"].get("REQ-JOB-04", False):
                failures.append(
                    f"{cell['label']} {outcome['case_id']}: confirmation invariant failed"
                )
            if any(
                marker in failure
                for failure in outcome["failures"]
                for marker in ("Cassette miss:", "BudgetExceeded", "TimeoutError")
            ):
                failures.append(f"{cell['label']} {outcome['case_id']}: incomplete matrix evidence")
    for comparison in report.matrix.get("drift_comparisons", []):
        if (
            comparison["unmatched_current"]
            or comparison["unmatched_baseline"]
            or not comparison["matched"]
        ):
            failures.append(f"{comparison['current']}: incomplete paired baseline")
        elif comparison["difference"] < 0 and comparison["exact_p_value"] < 0.05:
            failures.append(f"{comparison['current']}: significant paired decline (exploratory)")
    if "drift_comparisons" in report.matrix and len(report.matrix["drift_comparisons"]) != len(
        report.matrix["cells"]
    ):
        failures.append("Baseline is missing matrix cells")
    return failures
