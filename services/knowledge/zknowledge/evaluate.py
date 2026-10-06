import argparse
import math
import sys
from pathlib import Path

import yaml

from zknowledge.index import Caller, IndexStore, KnowledgeIndex, build_index
from zknowledge.snapshot import corpus_root

EVALS = Path(__file__).resolve().parents[1] / "evals" / "retrieval.yaml"
DEPTH = 8


def wilson_lower(successes: int, trials: int, z: float = 1.96) -> float:
    if not trials:
        return 0.0
    p = successes / trials
    centre = p + z * z / (2 * trials)
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (centre - margin) / (1 + z * z / trials)


def gold_line(index: KnowledgeIndex, document: str, text: str) -> int | None:
    row = index.connection.execute(
        "SELECT number FROM lines WHERE document=? AND instr(text, ?) > 0 ORDER BY number LIMIT 1",
        (document, text),
    ).fetchone()
    return row[0] if row else None


def evaluate(index: KnowledgeIndex, spec: dict) -> dict:
    default = spec["default_caller"]
    k = spec["gate"]["k"]
    rows, errors, violations = [], [], []
    for query in spec["queries"]:
        claims = query.get("caller", default)
        caller = Caller(claims["site"], claims["roles"])
        gold = []
        for item in query["relevant"]:
            line = gold_line(index, item["document"], item["contains"])
            if line is None:
                errors.append(f"{query['id']}: gold text not found in {item['document']}")
            elif not index.is_visible(caller, item["document"]):
                errors.append(f"{query['id']}: gold {item['document']} is hidden from the caller")
            else:
                gold.append((item["document"], line))
        result = index.search(
            caller,
            query["query"],
            include_inactive=query.get("include_inactive", False),
            limit=DEPTH,
        )
        forbidden = set(query.get("must_not", []))
        violations += [
            f"{query['id']}: {match['document']} returned to a caller who cannot see it"
            for match in result["matches"]
            if match["document"] in forbidden
        ]
        rank = next(
            (
                position
                for position, match in enumerate(result["matches"], 1)
                if any(
                    match["document"] == document
                    and match["start_line"] <= line <= match["end_line"]
                    for document, line in gold
                )
            ),
            None,
        )
        if query["relevant"]:
            source = index.connection.execute(
                "SELECT source FROM documents WHERE id=?", (query["relevant"][0]["document"],)
            ).fetchone()
            rows.append(
                {
                    "id": query["id"],
                    "source": source[0] if source else "unknown",
                    "rank": rank,
                    "hit": rank is not None and rank <= k,
                }
            )
    by_source: dict[str, dict] = {}
    for row in rows:
        bucket = by_source.setdefault(row["source"], {"queries": 0, "hits": 0, "rr": 0.0})
        bucket["queries"] += 1
        bucket["hits"] += row["hit"]
        bucket["rr"] += 1 / row["rank"] if row["rank"] else 0.0
    hits = sum(row["hit"] for row in rows)
    return {
        "snapshot": index.snapshot,
        "queries": len(rows),
        "recall": hits / len(rows) if rows else 0.0,
        "recall_lower_bound": wilson_lower(hits, len(rows)),
        "mrr": sum(1 / row["rank"] for row in rows if row["rank"]) / len(rows) if rows else 0.0,
        "by_source": {
            source: {
                "queries": bucket["queries"],
                "recall": bucket["hits"] / bucket["queries"],
                "mrr": bucket["rr"] / bucket["queries"],
            }
            for source, bucket in sorted(by_source.items())
        },
        "misses": [row["id"] for row in rows if not row["hit"]],
        "gold_errors": errors,
        "access_violations": violations,
        "passed": not errors
        and not violations
        and wilson_lower(hits, len(rows)) >= spec["gate"]["min_recall_lower_bound"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb-eval")
    parser.add_argument("--corpus", type=Path, default=corpus_root())
    parser.add_argument("--snapshots", type=Path, default=None)
    parser.add_argument("--cases", type=Path, default=EVALS)
    args = parser.parse_args(argv)
    spec = yaml.safe_load(args.cases.read_text())
    directory = args.snapshots
    if directory is None:
        import tempfile

        directory = Path(tempfile.mkdtemp(prefix="kb-eval-"))
        build_index(args.corpus, directory)
    index = IndexStore(directory).open()
    try:
        report = evaluate(index, spec)
    finally:
        index.close()
    k = spec["gate"]["k"]
    print(f"snapshot {report['snapshot']}")
    print(
        f"recall@{k} {report['recall']:.3f} (95% lower bound {report['recall_lower_bound']:.3f}) "
        f"MRR@{DEPTH} {report['mrr']:.3f} over {report['queries']} queries"
    )
    for source, values in report["by_source"].items():
        print(
            f"  {source:<10} recall@{k} {values['recall']:.3f}  MRR {values['mrr']:.3f}  "
            f"n={values['queries']}"
        )
    for name in ("misses", "gold_errors", "access_violations"):
        if report[name]:
            print(f"{name}: {', '.join(report[name])}")
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
