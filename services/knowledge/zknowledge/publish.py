import argparse
from pathlib import Path

from zknowledge.index import build_index
from zknowledge.snapshot import corpus_root, snapshot_directory


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="kb-publish")
    parser.add_argument("--corpus", type=Path, default=corpus_root())
    parser.add_argument("--target", type=Path, default=snapshot_directory())
    args = parser.parse_args(argv)
    identifier, warnings = build_index(args.corpus, args.target)
    for warning in warnings:
        print("warning: " + warning)
    print("Published knowledge index " + identifier)


if __name__ == "__main__":
    main()
