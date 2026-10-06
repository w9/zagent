import hashlib
import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

import yaml

from zknowledge.checks import PublishError, check_corpus, resolve_citations
from zknowledge.connectors import load_corpus
from zknowledge.document import ACTIVE, Document
from zknowledge.snapshot import CURRENT, SnapshotUnavailable

FORMAT = "zknowledge-index-2"
PASSAGE_LINES = 6
CANDIDATES = 200
SNIPPET = 420
READ_LINES = 30
READ_CHARACTERS = 5000
PRIORS = {
    "sop": 0.6,
    "validation": 0.45,
    "reference_table": 0.35,
    "form": 0.3,
    "wiki_page": 0.2,
    "glossary": 0.1,
    "encyclopedia": 0.0,
}
TICKET_PRIOR = 0.1
LEAD_BONUS = 0.8
STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i in is it of on or our should the this "
    "to us we what when where which who why will with you".split()
)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def build_index(corpus: Path, snapshots: Path, *, current: bool = True) -> tuple[str, list[str]]:
    documents, tables, terms = load_corpus(corpus)
    conflicts = yaml.safe_load((corpus / "conflicts.yaml").read_text())
    problems = resolve_citations(documents, tables, terms)
    errors, warnings = check_corpus(documents, tables, terms, conflicts)
    if problems or errors:
        raise PublishError(problems + errors)
    documents.sort(key=lambda document: document.id)
    chunks = [chunk for document in documents for chunk in passages(document)]
    content = canonical(
        {
            "format": FORMAT,
            "documents": [asdict(document) for document in documents],
            "passages": chunks,
            "tables": tables,
            "terms": terms,
            "conflicts": conflicts,
        }
    )
    identifier = hashlib.sha256(content.encode()).hexdigest()
    snapshots.mkdir(parents=True, exist_ok=True)
    target = snapshots / f"{identifier}.sqlite3"
    temporary = target.with_suffix(".building")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        with connection:
            write_index(connection, identifier, documents, chunks, tables, terms)
        connection.execute("VACUUM")
    finally:
        connection.close()
    temporary.replace(target)
    if current:
        pointer = snapshots / f"{CURRENT}.building"
        pointer.write_text(identifier + "\n")
        pointer.replace(snapshots / CURRENT)
    return identifier, warnings


def write_index(connection, identifier, documents: list[Document], chunks, tables, terms) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE documents (
            id TEXT PRIMARY KEY, source TEXT, source_id TEXT, title TEXT, doc_type TEXT,
            version TEXT, status TEXT, effective_from TEXT, effective_to TEXT, series TEXT,
            supersedes TEXT, superseded_by TEXT, applies_to TEXT, labels TEXT, sites TEXT,
            roles TEXT, provenance TEXT, line_count INTEGER);
        CREATE TABLE sections (
            document TEXT, path TEXT, heading TEXT, level INTEGER, start_line INTEGER,
            end_line INTEGER, PRIMARY KEY (document, path));
        CREATE TABLE lines (
            document TEXT, number INTEGER, text TEXT, PRIMARY KEY (document, number)
        ) WITHOUT ROWID;
        CREATE VIRTUAL TABLE passages USING fts5(
            document UNINDEXED, section UNINDEXED, start_line UNINDEXED, end_line UNINDEXED,
            title, heading, body, tokenize='porter unicode61');
        CREATE TABLE terms (
            key TEXT PRIMARY KEY, term TEXT, definition TEXT, synonyms TEXT,
            source_document TEXT, source_line INTEGER, glossary_start INTEGER,
            glossary_end INTEGER);
        CREATE TABLE term_keys (key TEXT PRIMARY KEY, term_key TEXT);
        CREATE TABLE reference_tables (
            name TEXT PRIMARY KEY, title TEXT, description TEXT, columns TEXT, document TEXT);
        CREATE TABLE reference_rows (
            table_name TEXT, ordinal INTEGER, row TEXT, line INTEGER, source_document TEXT,
            source_line INTEGER, PRIMARY KEY (table_name, ordinal));
        """
    )
    connection.executemany(
        "INSERT INTO metadata VALUES (?, ?)", [("snapshot", identifier), ("format", FORMAT)]
    )
    for document in documents:
        connection.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                document.id,
                document.source,
                document.source_id,
                document.title,
                document.doc_type,
                document.version,
                document.status,
                document.effective_from,
                document.effective_to,
                document.series,
                document.supersedes,
                document.superseded_by,
                canonical(document.applies_to),
                canonical(document.labels),
                canonical(document.sites),
                canonical(document.roles),
                canonical(document.provenance),
                len(document.lines),
            ),
        )
        connection.executemany(
            "INSERT INTO sections VALUES (?,?,?,?,?,?)",
            [
                (document.id, s.path, s.heading, s.level, s.start_line, s.end_line)
                for s in document.sections
            ],
        )
        connection.executemany(
            "INSERT INTO lines VALUES (?,?,?)",
            [(document.id, number, text) for number, text in enumerate(document.lines, 1)],
        )
    connection.executemany("INSERT INTO passages VALUES (?,?,?,?,?,?,?)", chunks)
    for term in terms:
        key = normalize(term["term"])
        connection.execute(
            "INSERT INTO terms VALUES (?,?,?,?,?,?,?,?)",
            (
                key,
                term["term"],
                term["definition"],
                canonical(term["synonyms"]),
                term["source_document"],
                term["source_line"],
                *term["glossary_lines"],
            ),
        )
        connection.executemany(
            "INSERT OR IGNORE INTO term_keys VALUES (?, ?)",
            [(normalize(name), key) for name in (term["term"], *term["synonyms"])],
        )
    for table in tables:
        connection.execute(
            "INSERT INTO reference_tables VALUES (?,?,?,?,?)",
            (
                table["name"],
                table["title"],
                table["description"],
                canonical(table["columns"]),
                table["document"],
            ),
        )
        connection.executemany(
            "INSERT INTO reference_rows VALUES (?,?,?,?,?,?)",
            [
                (
                    table["name"],
                    ordinal,
                    canonical(row["values"]),
                    row["line"],
                    row["source_document"],
                    row["source_line"],
                )
                for ordinal, row in enumerate(table["rows"], 1)
            ],
        )


def passages(document: Document):
    """Fixed windows across the whole document, so passage length does not skew BM25."""
    headings = {section.path: section.heading for section in document.sections[1:]}
    count = len(document.lines)
    starts = list(range(2, count + 1, PASSAGE_LINES))
    if len(starts) > 1 and count - starts[-1] + 1 < PASSAGE_LINES // 2:
        starts.pop()
    for index, first in enumerate(starts):
        last = starts[index + 1] - 1 if index + 1 < len(starts) else count
        overlapping = [
            section
            for section in document.sections[1:]
            if section.start_line <= last and first <= section.end_line
        ]
        paths = []
        for section in overlapping:
            parts = section.path.split(".")
            paths.append(
                " > ".join(
                    headings[".".join(parts[: depth + 1])]
                    for depth in range(len(parts))
                    if ".".join(parts[: depth + 1]) in headings
                )
            )
        body = [
            text
            for text in document.lines[first - 1 : last]
            if not (document.doc_type == "glossary" and text.startswith("Synonyms:"))
        ]
        yield (
            document.id,
            overlapping[0].path if overlapping else "0",
            first,
            last,
            document.title,
            " | ".join(dict.fromkeys(paths)),
            "\n".join(body),
        )


class Caller:
    def __init__(self, site: str | None = None, roles: list[str] | None = None):
        self.site = site
        self.roles = set(roles or [])

    def sees(self, sites: list[str], roles: list[str]) -> bool:
        return ("all" in sites or self.site in sites) and (
            "all" in roles or bool(self.roles & set(roles))
        )


class NotFound(ValueError):
    pass


class KnowledgeIndex:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
        self.connection.row_factory = sqlite3.Row
        self.snapshot = self.connection.execute(
            "SELECT value FROM metadata WHERE key='snapshot'"
        ).fetchone()[0]

    def close(self) -> None:
        self.connection.close()

    def visible(self, caller: Caller, document: str) -> sqlite3.Row:
        row = self.connection.execute("SELECT * FROM documents WHERE id=?", (document,)).fetchone()
        if row is None or not caller.sees(json.loads(row["sites"]), json.loads(row["roles"])):
            raise NotFound("Document not found")
        return row

    def summary(self, row: sqlite3.Row) -> dict:
        return {
            "document": row["id"],
            "title": row["title"],
            "source": row["source"],
            "doc_type": row["doc_type"],
            "version": row["version"],
            "status": row["status"],
        }

    def expansions(self, query: str) -> list[str]:
        text = f" {normalize(query)} "
        keys = {
            row["term_key"]
            for row in self.connection.execute("SELECT key, term_key FROM term_keys")
            if f" {row['key']} " in text
        }
        phrases = set()
        for key in sorted(keys):
            term = self.connection.execute(
                "SELECT term, synonyms FROM terms WHERE key=?", (key,)
            ).fetchone()
            phrases.update(
                normalize(name) for name in (term["term"], *json.loads(term["synonyms"]))
            )
        return sorted(phrase for phrase in phrases if phrase)

    def search(
        self,
        caller: Caller,
        query: str,
        *,
        sources: list[str] | None = None,
        doc_types: list[str] | None = None,
        applies_to: str | None = None,
        include_inactive: bool = False,
        limit: int = 5,
    ) -> dict:
        words = [word for word in normalize(query).split() if word not in STOPWORDS][:20]
        codes = [
            normalize(code) for code in re.findall(r"[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+", query)
        ]
        expanded = self.expansions(query)
        terms = sorted({*words, *codes, *expanded})
        result = {"snapshot": self.snapshot, "expanded_terms": expanded, "matches": []}
        if not terms:
            return {**result, "counts": {}}
        expression = " OR ".join(f'"{term}"' for term in terms)
        rows = self.connection.execute(
            "SELECT p.document, p.section, p.start_line, p.end_line, p.heading, p.body, "
            "bm25(passages, 0, 0, 0, 0, 2.0, 2.0, 1.0) AS rank, d.* "
            "FROM passages p JOIN documents d ON d.id = p.document "
            "WHERE passages MATCH ? ORDER BY rank, p.document, p.start_line LIMIT ?",
            (expression, CANDIDATES),
        ).fetchall()
        scored, counts = [], {}
        for row in rows:
            if not caller.sees(json.loads(row["sites"]), json.loads(row["roles"])):
                continue
            if not include_inactive and row["status"] not in ACTIVE:
                continue
            if sources and row["source"] not in sources:
                continue
            if doc_types and row["doc_type"] not in doc_types:
                continue
            if applies_to and applies_to not in json.loads(row["applies_to"]):
                continue
            prior = PRIORS.get(row["doc_type"], TICKET_PRIOR)
            prior -= 0.3 if row["status"] not in ACTIVE else 0
            # Encyclopedia leads summarize the article; later sections are rarely the answer.
            prior += (
                LEAD_BONUS if row["doc_type"] == "encyclopedia" and row["start_line"] == 2 else 0
            )
            scored.append((-row["rank"] * (1 + prior), row))
            counts.setdefault(row["source"], set()).add(row["id"])
        scored.sort(key=lambda item: (-item[0], item[1]["id"], item[1]["start_line"]))
        taken: dict[str, int] = {}
        for score, row in scored:
            if taken.get(row["id"], 0) >= 2:
                continue
            taken[row["id"]] = taken.get(row["id"], 0) + 1
            body = row["body"]
            result["matches"].append(
                {
                    **self.summary(row),
                    "section": row["heading"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "snippet": body if len(body) <= SNIPPET else body[: SNIPPET - 1] + "\u2026",
                    "score": round(score, 3),
                }
            )
            if len(result["matches"]) >= limit:
                break
        result["counts"] = {source: len(names) for source, names in sorted(counts.items())}
        return result

    def get_document(self, caller: Caller, document: str) -> dict:
        row = self.visible(caller, document)
        versions = []
        if row["series"]:
            for other in self.connection.execute(
                "SELECT * FROM documents WHERE series=? ORDER BY CAST(version AS INTEGER)",
                (row["series"],),
            ):
                if caller.sees(json.loads(other["sites"]), json.loads(other["roles"])):
                    versions.append(
                        {
                            "document": other["id"],
                            "version": other["version"],
                            "status": other["status"],
                            "effective_from": other["effective_from"],
                        }
                    )
        outline = [
            dict(section)
            for section in self.connection.execute(
                "SELECT path, heading, start_line, end_line FROM sections "
                "WHERE document=? AND path != '0' ORDER BY start_line LIMIT 60",
                (document,),
            )
        ]
        hidden = {
            name
            for name in (row["supersedes"], row["superseded_by"])
            if name and not self.is_visible(caller, name)
        }
        provenance = json.loads(row["provenance"])
        return {
            "snapshot": self.snapshot,
            **self.summary(row),
            "effective_from": row["effective_from"],
            "effective_to": row["effective_to"],
            "applies_to": json.loads(row["applies_to"]),
            "labels": json.loads(row["labels"]),
            "supersedes": None if row["supersedes"] in hidden else row["supersedes"],
            "superseded_by": None if row["superseded_by"] in hidden else row["superseded_by"],
            "versions": versions,
            "provenance": {
                key: provenance[key]
                for key in ("url", "license", "attribution", "owner_role", "updated", "created")
                if key in provenance
            },
            "line_count": row["line_count"],
            "outline": outline,
        }

    def is_visible(self, caller: Caller, document: str) -> bool:
        try:
            self.visible(caller, document)
        except NotFound:
            return False
        return True

    def read_document(
        self,
        caller: Caller,
        document: str,
        *,
        section: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict:
        row = self.visible(caller, document)
        if (section is None) == (start_line is None):
            raise ValueError("Provide either a section or a start_line")
        if section is not None:
            found = self.connection.execute(
                "SELECT start_line, end_line FROM sections WHERE document=? AND path=?",
                (document, section),
            ).fetchone()
            if found is None:
                raise ValueError("Section is not in this document's outline")
            start_line, end_line = found["start_line"], found["end_line"]
        end_line = end_line or start_line
        if not 1 <= start_line <= end_line <= row["line_count"]:
            raise ValueError(f"Line range must lie within 1-{row['line_count']}")
        requested = end_line
        lines, size = [], 0
        for item in self.connection.execute(
            "SELECT text FROM lines WHERE document=? AND number BETWEEN ? AND ? ORDER BY number",
            (document, start_line, min(end_line, start_line + READ_LINES - 1)),
        ):
            if lines and size + len(item["text"]) + 1 > READ_CHARACTERS:
                break
            lines.append(item["text"])
            size += len(item["text"]) + 1
        end_line = start_line + len(lines) - 1
        return {
            "snapshot": self.snapshot,
            **self.summary(row),
            "start_line": start_line,
            "end_line": end_line,
            "truncated": end_line < requested,
            "text": "\n".join(lines),
        }

    def lookup_term(self, caller: Caller, term: str) -> dict:
        key = normalize(term)
        found = self.connection.execute(
            "SELECT t.* FROM term_keys k JOIN terms t ON t.key = k.term_key WHERE k.key=?",
            (key,),
        ).fetchone()
        if found is None:
            suggestions = [
                row["term"]
                for row in self.connection.execute(
                    "SELECT DISTINCT t.term FROM term_keys k JOIN terms t ON t.key = k.term_key "
                    "WHERE k.key LIKE ? ORDER BY t.term LIMIT 5",
                    (f"%{key}%",),
                )
            ]
            raise NotFound(
                "Term not found"
                + (f"; similar terms: {', '.join(suggestions)}" if suggestions else "")
            )
        source = None
        if found["source_document"] and self.is_visible(caller, found["source_document"]):
            source_row = self.visible(caller, found["source_document"])
            source = {
                "document": found["source_document"],
                "version": source_row["version"],
                "line": found["source_line"],
            }
        return {
            "snapshot": self.snapshot,
            "term": found["term"],
            "definition": found["definition"],
            "synonyms": json.loads(found["synonyms"]),
            "glossary": {
                "document": "ref-glossary",
                "start_line": found["glossary_start"],
                "end_line": found["glossary_end"],
            },
            "source": source,
        }

    def query_reference(
        self, caller: Caller, table: str, filters: dict | None = None, limit: int = 10
    ) -> dict:
        spec = self.connection.execute(
            "SELECT * FROM reference_tables WHERE name=?", (table,)
        ).fetchone()
        if spec is None:
            names = [row[0] for row in self.connection.execute("SELECT name FROM reference_tables")]
            raise NotFound(f"Unknown reference table; available: {', '.join(sorted(names))}")
        columns = json.loads(spec["columns"])
        filters = filters or {}
        unknown = sorted(set(filters) - set(columns))
        if unknown:
            raise ValueError(f"Unknown filter columns: {', '.join(unknown)}")
        matched = []
        for row in self.connection.execute(
            "SELECT * FROM reference_rows WHERE table_name=? ORDER BY ordinal", (table,)
        ):
            values = json.loads(row["row"])
            if all(matches(values.get(name), wanted) for name, wanted in filters.items()):
                source = None
                if row["source_document"] and self.is_visible(caller, row["source_document"]):
                    source = {"document": row["source_document"], "line": row["source_line"]}
                matched.append({**values, "_row_line": row["line"], "_source": source})
        return {
            "snapshot": self.snapshot,
            "table": table,
            "title": spec["title"],
            "document": spec["document"],
            "columns": columns,
            "total": len(matched),
            "truncated": len(matched) > limit,
            "rows": matched[:limit],
        }


def matches(value, wanted) -> bool:
    if isinstance(wanted, str) and isinstance(value, str):
        return value.lower() == wanted.lower()
    return value == wanted


class IndexStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def open(self, snapshot: str | None = None) -> KnowledgeIndex:
        try:
            identifier = snapshot or (self.directory / CURRENT).read_text().strip()
        except OSError:
            raise SnapshotUnavailable("No knowledge snapshot has been published") from None
        path = self.directory / f"{identifier}.sqlite3"
        if not re.fullmatch(r"[a-f0-9]{64}", identifier) or not path.is_file():
            raise SnapshotUnavailable("Knowledge snapshot is unavailable")
        return KnowledgeIndex(path)
