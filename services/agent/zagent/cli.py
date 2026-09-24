import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from uuid import UUID

import asyncpg

from zagent.evals.reporting import report_passes, terminal_report, write_report
from zagent.evals.runner import evaluate_suite
from zagent.evals.schema import Report
from zagent.events import normalize_transcript
from zagent.store import DEFAULT_DATABASE_URL, NotFound, Store


async def transcript(session_id: UUID, database_url: str) -> list[dict]:
    store = await Store.open(database_url)
    try:
        return normalize_transcript(await store.snapshot_events(session_id))
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="zagent")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("transcript", help="Print a normalized session transcript")
    command.add_argument("session_id", type=UUID)
    command.add_argument(
        "--database-url", default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    evaluate = commands.add_parser(
        "evals", help="Evaluate declarative cases over the public HTTP API"
    )
    evaluate.add_argument("--root", type=Path, default=Path("evals"))
    evaluate.add_argument(
        "--filter", dest="filter_value", help="Case/requirement ID, substring, or glob"
    )
    evaluate.add_argument(
        "--trials", type=int, help="Trials per case and mode (default: 1 normal, 10 chaos)"
    )
    evaluate.add_argument("--seed", type=int, default=0)
    evaluate.add_argument("--scope-concurrency", type=int, default=8)
    evaluate.add_argument("--mutation", choices=["disable_scope_guard"])
    evaluate.add_argument(
        "--mutate", help="Run paired enforcement mutations: all or comma-separated names"
    )
    evaluate.add_argument("--budget-usd", type=float)
    evaluate.add_argument(
        "--accept-known-findings",
        action="store_true",
        help="Allow only exact documented measured replay findings; never waive invariants",
    )
    evaluate.add_argument(
        "--budget-ledger", type=Path, default=Path(".cluster/evaluation-budget.json")
    )
    evaluate.add_argument("--update-golden", action="store_true")
    evaluate.add_argument(
        "--record-missing",
        action="store_true",
        help="In record mode, preserve existing samples and record only absent requests",
    )
    evaluate.add_argument("--mode", choices=["replay", "record", "live"], default="replay")
    chaos = evaluate.add_mutually_exclusive_group()
    chaos.add_argument("--chaos", action="store_true", help="Only seeded interruption trials")
    chaos.add_argument("--no-chaos", action="store_true", help="Only uninterrupted golden trials")
    evaluate.add_argument("--pass-k", type=int, default=3)
    evaluate.add_argument("--output", type=Path, default=Path("docs/evals"))
    evaluate.add_argument("--baseline", type=Path)
    evaluate.add_argument(
        "--database-url",
        default=os.environ.get("ZAGENT_TEST_DATABASE_URL")
        or "postgresql://zagent:zagent@localhost:5432/zagent_test",
    )
    report = commands.add_parser("report", help="Render stored evidence without executing cases")
    report.add_argument("--input", type=Path, default=Path("docs/evals/results.json"))
    report.add_argument("--output", type=Path, default=Path("docs/evals"))
    report.add_argument("--baseline", type=Path)
    report.add_argument("--accept-known-findings", action="store_true")
    matrix = commands.add_parser(
        "matrix", help="Bounded three-model, two-prompt adversarial evidence"
    )
    matrix.add_argument("--root", type=Path, default=Path("evals"))
    matrix.add_argument("--database-url", default=os.environ.get("ZAGENT_TEST_DATABASE_URL"))
    matrix.add_argument("--mode", choices=["replay", "record"], default="replay")
    matrix.add_argument("--seed", type=int, default=0)
    matrix.add_argument("--output", type=Path, default=Path("docs/evals/plan10/matrix"))
    matrix.add_argument("--budget-usd", type=float)
    matrix.add_argument("--baseline", type=Path, help="Stored matrix result for paired drift")
    matrix.add_argument(
        "--budget-ledger", type=Path, default=Path(".cluster/evaluation-budget.json")
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    try:
        if args.command == "transcript":
            result = asyncio.run(transcript(args.session_id, args.database_url))
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        if args.command == "matrix":
            from zagent.evals.matrix import evaluate_matrix, matrix_regressions

            if not args.database_url or not 0 <= args.seed <= 9997:
                raise ValueError("Matrix requires a test database and a seed in 0..9997")
            result = asyncio.run(
                evaluate_matrix(
                    args.root,
                    args.database_url,
                    args.output,
                    mode=args.mode,
                    seed=args.seed,
                    budget_usd=args.budget_usd,
                    ledger=args.budget_ledger,
                    baseline=Report.model_validate_json(args.baseline.read_text())
                    if args.baseline
                    else None,
                )
            )
            print(f"Matrix report: {args.output / 'index.html'}")
            regressions = matrix_regressions(result)
            print(
                f"Quality gates: {'PASS' if report_passes(result) else 'FAIL (findings retained)'}"
            )
            for regression in regressions:
                print(regression)
            if regressions:
                parser.exit(1)
            return
        baseline = Report.model_validate_json(args.baseline.read_text()) if args.baseline else None
        if args.command == "evals":
            if args.mutate:
                from zagent.evals.mutations import evaluate_mutations, evidence_report

                if (
                    args.mode != "replay"
                    or args.update_golden
                    or args.record_missing
                    or args.mutation
                ):
                    raise ValueError("Enforcement mutations are keyless replay-only experiments")
                result = evidence_report(
                    asyncio.run(evaluate_mutations(args.database_url, args.root, args.mutate))
                )
                path = write_report(result, args.output / "mutations")
                print(terminal_report(result))
                print(f"Mutation report: {path}")
                if not report_passes(result):
                    parser.exit(1)
                return
            if args.record_missing and args.mode != "record":
                raise ValueError("--record-missing requires explicit --mode record")
            if args.mode != "replay" and (not args.no_chaos or not args.filter_value):
                raise ValueError("Provider access requires --filter and --no-chaos to bound cost")
            if args.mode == "live" and args.update_golden:
                raise ValueError("Use --mode record to update replay goldens")
            budget = None
            if args.budget_usd is not None:
                from zagent.evals.matrix import budget_for

                budget = budget_for(args.root, args.budget_ledger, args.budget_usd)
            result = asyncio.run(
                evaluate_suite(
                    args.root,
                    args.database_url,
                    filter_value=args.filter_value,
                    trials=args.trials,
                    seed=args.seed,
                    chaos_only=args.chaos,
                    include_chaos=not args.no_chaos,
                    update_golden=args.update_golden,
                    pass_streak=args.pass_k,
                    mode=args.mode,
                    record_missing=args.record_missing,
                    scope_concurrency=args.scope_concurrency,
                    mutation=args.mutation,
                    budget=budget,
                    progress=lambda done, total: print(
                        f"Scope samples: {done}/{total}", file=sys.stderr
                    ),
                )
            )
        else:
            result = Report.model_validate_json(args.input.read_text())
        path = write_report(result, args.output, baseline)
        print(terminal_report(result, baseline))
        print(f"Report: {path}")
        if args.command == "evals" and args.update_golden:
            print("Golden update requested. Review the golden-file diff before committing.")
        accepted_findings = (
            args.command in {"evals", "report"}
            and args.accept_known_findings
            and result.findings_review
            and result.findings_review["passed"]
        )
        if not report_passes(result) and not accepted_findings:
            parser.exit(1)
    except (NotFound, OSError, ValueError, asyncpg.PostgresError) as error:
        parser.exit(1, f"zagent: {error}\n")


if __name__ == "__main__":
    main()
