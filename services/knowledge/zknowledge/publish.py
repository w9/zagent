import argparse
import os
from pathlib import Path

from zknowledge.index import build_index
from zknowledge.snapshot import DEFAULT_SNAPSHOTS, build_snapshot, corpus_root


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb-publish")
    parser.add_argument("--corpus", type=Path, default=corpus_root())
    parser.add_argument(
        "--target",
        type=Path,
        default=Path(os.environ.get("ZKNOWLEDGE_SNAPSHOTS", DEFAULT_SNAPSHOTS)),
    )
    args = parser.parse_args(argv)
    print("Published legacy snapshot " + build_snapshot(args.corpus / "legacy", args.target))
    identifier, warnings = build_index(args.corpus, args.target / "v2")
    for warning in warnings:
        print("warning: " + warning)
    print("Published knowledge index " + identifier)


if __name__ == "__main__":
    main()
