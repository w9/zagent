import json
import sqlite3
from pathlib import Path

import pytest
from zknowledge.snapshot import (
    SnapshotStore,
    SnapshotUnavailable,
    build_snapshot,
    corpus_root,
    source_version,
)

LEGACY = corpus_root() / "legacy"


def test_snapshots_are_deterministic_read_only_and_line_exact(tmp_path):
    first = build_snapshot(LEGACY, tmp_path / "first")
    second = build_snapshot(LEGACY, tmp_path / "second")
    assert first == second == source_version(LEGACY)
    assert (tmp_path / "first" / f"{first}.sqlite3").read_bytes() == (
        tmp_path / "second" / f"{second}.sqlite3"
    ).read_bytes()
    snapshot = SnapshotStore(tmp_path / "first").open()
    try:
        assert snapshot.version == first
        match = snapshot.search("genotype concordance")["matches"][0]
        excerpt = snapshot.read(match["document"], match["start_line"], match["end_line"], first)
        assert excerpt["text"] == match["text"]
        with pytest.raises(ValueError, match="version mismatch"):
            snapshot.read(match["document"], 1, 2, "old")
        with pytest.raises(ValueError, match="at most 30 lines"):
            snapshot.read(match["document"], 1, 31, first)
        with pytest.raises(sqlite3.OperationalError):
            snapshot.connection.execute("DELETE FROM lines")
    finally:
        snapshot.close()


def test_older_snapshots_stay_addressable_after_a_new_publication(tmp_path):
    snapshots = tmp_path / "snapshots"
    old = build_snapshot(LEGACY, snapshots)
    changed = tmp_path / "changed"
    changed.mkdir()
    (changed / "read-quality.md").write_text("# Read Quality\nCoverage below 40x fails.\n")
    new = build_snapshot(changed, snapshots)
    store = SnapshotStore(snapshots)
    assert store.current() == new != old
    for identifier in (old, new):
        snapshot = store.open(identifier)
        try:
            assert snapshot.version == identifier
        finally:
            snapshot.close()
    for missing in ("a" * 64, "../current", "current"):
        with pytest.raises(SnapshotUnavailable):
            store.open(missing)


def test_an_unpublished_store_is_unavailable(tmp_path):
    with pytest.raises(SnapshotUnavailable):
        SnapshotStore(tmp_path).open()


def test_legacy_corpus_keeps_the_pinned_execution_version():
    cases = (Path(__file__).parents[3] / "evals/cases/execution.yaml").read_text()
    assert f"kb_version: {source_version(LEGACY)}" in cases
    assert json.dumps(sorted(path.name for path in LEGACY.glob("*.md"))) == json.dumps(
        ["read-quality.md", "specimen-identity.md"]
    )
