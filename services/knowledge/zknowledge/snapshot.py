import os
from pathlib import Path

CURRENT = "current"
DEFAULT_SNAPSHOTS = "/var/lib/zknowledge/snapshots"


class SnapshotUnavailable(ValueError):
    pass


def corpus_root() -> Path:
    return Path(
        os.environ.get("ZKNOWLEDGE_CORPUS", str(Path(__file__).resolve().parents[1] / "corpus"))
    )


def snapshot_directory() -> Path:
    return Path(os.environ.get("ZKNOWLEDGE_SNAPSHOTS", DEFAULT_SNAPSHOTS))
