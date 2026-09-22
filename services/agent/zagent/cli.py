import argparse
import asyncio
import json
import logging
import os
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
    evaluate.add_argument("--update-golden", action="store_true")
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
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    try:
        if args.command == "transcript":
            result = asyncio.run(transcript(args.session_id, args.database_url))
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        baseline = Report.model_validate_json(args.baseline.read_text()) if args.baseline else None
        if args.command == "evals":
            if args.mode != "replay" and (not args.no_chaos or not args.filter_value):
                raise ValueError("Provider access requires --filter and --no-chaos to bound cost")
            if args.mode == "live" and args.update_golden:
                raise ValueError("Use --mode record to update replay goldens")
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
                )
            )
        else:
            result = Report.model_validate_json(args.input.read_text())
        path = write_report(result, args.output, baseline)
        print(terminal_report(result, baseline))
        print(f"Report: {path}")
        if args.command == "evals" and args.update_golden:
            print("Golden update requested. Review the golden-file diff before committing.")
        if not report_passes(result):
            parser.exit(1)
    except (NotFound, OSError, ValueError, asyncpg.PostgresError) as error:
        parser.exit(1, f"zagent: {error}\n")


if __name__ == "__main__":
    main()
