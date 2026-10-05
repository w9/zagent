import argparse
import os
from pathlib import Path

from zknowledge.snapshot import DEFAULT_SNAPSHOTS, build_snapshot, corpus_root


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb-publish")
    parser.add_argument("--source", type=Path, default=corpus_root() / "legacy")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path(os.environ.get("ZKNOWLEDGE_SNAPSHOTS", DEFAULT_SNAPSHOTS)),
    )
    args = parser.parse_args(argv)
    print("Published knowledge snapshot " + build_snapshot(args.source, args.target))


if __name__ == "__main__":
    main()
