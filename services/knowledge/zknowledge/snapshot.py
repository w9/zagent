import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

CURRENT = "current"
SNAPSHOT_ID = re.compile(r"^[a-f0-9]{64}$")
DEFAULT_SNAPSHOTS = "/var/lib/zknowledge/snapshots"


class SnapshotUnavailable(ValueError):
    pass


def corpus_root() -> Path:
    return Path(
        os.environ.get("ZKNOWLEDGE_CORPUS", str(Path(__file__).resolve().parents[1] / "corpus"))
    )


def source_version(source: Path) -> str:
    content = [(path.name, path.read_text()) for path in sorted(source.glob("*.md"))]
    return hashlib.sha256(json.dumps(content, ensure_ascii=True).encode()).hexdigest()


def build_snapshot(source: Path, snapshots: Path, *, current: bool = True) -> str:
    version = source_version(source)
    snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / f"{version}.sqlite3"
    temporary = target.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        with connection:
            connection.execute("CREATE TABLE metadata (version TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata VALUES (?)", (version,))
            connection.execute(
                "CREATE VIRTUAL TABLE lines USING fts5(document UNINDEXED, number UNINDEXED, text)"
            )
            for path in sorted(source.glob("*.md")):
                connection.executemany(
                    "INSERT INTO lines VALUES (?, ?, ?)",
                    [
                        (path.stem, number, text)
                        for number, text in enumerate(path.read_text().splitlines(), 1)
                    ],
                )
    finally:
        connection.close()
    temporary.replace(target)
    if current:
        pointer = snapshots / f"{CURRENT}.building"
        pointer.write_text(version + "\n")
        pointer.replace(snapshots / CURRENT)
    return version


class Snapshot:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
        self.version = self.connection.execute("SELECT version FROM metadata").fetchone()[0]

    def search(self, query: str, limit: int = 4) -> dict:
        words = re.findall(r"[A-Za-z0-9]+", query)[:20]
        if not words:
            return {"version": self.version, "matches": []}
        expression = " OR ".join(f'"{word}"' for word in words)
        rows = self.connection.execute(
            "SELECT document, number, text FROM lines WHERE lines MATCH ? "
            "ORDER BY rank, document, rowid LIMIT ?",
            (expression, min(limit, 5)),
        ).fetchall()
        return {
            "version": self.version,
            "matches": [
                {"document": document, "start_line": number, "end_line": number, "text": text}
                for document, number, text in rows
            ],
        }

    def read(self, document: str, start_line: int, end_line: int, version: str) -> dict:
        if version != self.version:
            raise ValueError("Knowledge version mismatch; search the current index again")
        if not 1 <= start_line <= end_line or end_line - start_line >= 30:
            raise ValueError("Document range must contain at most 30 lines")
        rows = self.connection.execute(
            "SELECT number, text FROM lines WHERE document=? "
            "AND number BETWEEN ? AND ? ORDER BY number",
            (document, start_line, end_line),
        ).fetchall()
        if len(rows) != end_line - start_line + 1:
            raise ValueError("Document or requested line range is unavailable")
        return {
            "version": self.version,
            "document": document,
            "start_line": start_line,
            "end_line": end_line,
            "text": "\n".join(text for _number, text in rows),
        }

    def close(self) -> None:
        self.connection.close()


class SnapshotStore:
    def __init__(self, directory: Path):
        self.directory = directory

    @classmethod
    def configured(cls) -> "SnapshotStore":
        return cls(Path(os.environ.get("ZKNOWLEDGE_SNAPSHOTS", DEFAULT_SNAPSHOTS)))

    def current(self) -> str:
        try:
            return (self.directory / CURRENT).read_text().strip()
        except OSError:
            raise SnapshotUnavailable("No knowledge snapshot has been published") from None

    def open(self, snapshot: str | None = None) -> Snapshot:
        identifier = snapshot or self.current()
        path = self.directory / f"{identifier}.sqlite3"
        if not SNAPSHOT_ID.fullmatch(identifier) or not path.is_file():
            raise SnapshotUnavailable("Knowledge snapshot is unavailable")
        return Snapshot(path)
