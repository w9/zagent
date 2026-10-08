"""Intranet page models, built only from published snapshots and filtered by the visitor."""

import json
import re
import sqlite3
from dataclasses import dataclass, field

from zknowledge.faults import enabled
from zknowledge.index import Caller, IndexStore, KnowledgeIndex, NotFound
from zknowledge.snapshot import SnapshotUnavailable

SPACE = "MCGC"
AREAS = (
    ("wiki", "Wiki", "/wiki"),
    ("qms", "QMS", "/qms"),
    ("ticketing", "Service Desk", "/servicedesk"),
    ("reference", "Reference", "/reference"),
    ("wikipedia", "Library", "/library"),
)
SNAPSHOT_ID = re.compile(r"[a-f0-9]{64}")
LINE_RANGE = re.compile(r"([0-9]{1,5})(?:-([0-9]{1,5}))?")
TYPOGRAPHY = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00d7": "x"}
)
QUOTE_LIMIT = 300


@dataclass
class Line:
    number: int
    kind: str
    level: int = 0
    segments: list[tuple[str, bool]] = field(default_factory=list)
    cells: list[str] = field(default_factory=list)
    highlighted: bool = False
    source: str | None = None
    header: bool = False


@dataclass
class Block:
    kind: str
    lines: list[Line]


@dataclass
class Notice:
    kind: str
    text: str
    href: str | None = None
    link: str | None = None


def document_path(row: sqlite3.Row) -> str:
    source, source_id = row["source"], row["source_id"]
    if source == "wiki":
        return f"/wiki/display/{SPACE}/{source_id}"
    if source == "qms":
        return f"/qms/documents/{row['series']}/v{row['version']}"
    if source == "ticketing":
        return f"/servicedesk/browse/{source_id}"
    if source == "reference":
        return (
            "/reference/glossary"
            if row["doc_type"] == "glossary"
            else (f"/reference/tables/{source_id}")
        )
    return f"/library/{row['id'].removeprefix('wp-')}"


def find_document(index: KnowledgeIndex, area: str, key: str, version: str | None = None):
    query = {
        "wiki": ("SELECT id FROM documents WHERE source='wiki' AND source_id=?", (key,)),
        "qms": (
            "SELECT id FROM documents WHERE source='qms' AND series=? AND version=?",
            (key, version),
        ),
        "ticketing": ("SELECT id FROM documents WHERE source='ticketing' AND source_id=?", (key,)),
        "reference": (
            "SELECT id FROM documents WHERE source='reference' AND "
            "(source_id=? OR (doc_type='glossary' AND ?='glossary'))",
            (key, key),
        ),
        "wikipedia": ("SELECT id FROM documents WHERE source='wikipedia' AND id=?", (f"wp-{key}",)),
    }[area]
    found = index.connection.execute(*query).fetchone()
    if found is None:
        raise NotFound("Document not found")
    return found["id"]


def line_range(value: str | None, count: int) -> tuple[int, int] | None:
    match = LINE_RANGE.fullmatch(value or "")
    if not match:
        return None
    start, end = int(match[1]), int(match[2] or match[1])
    return (start, end) if 1 <= start <= end <= count else None


def emphasize(text: str, quote: str | None) -> list[tuple[str, bool]]:
    """Split text around the quoted part; the comparison ignores case and typography."""
    if not quote:
        return [(text, False)]
    folded = text.translate(TYPOGRAPHY).lower()
    for part in re.split(r"\u2026|\.\.\.", quote[:QUOTE_LIMIT]):
        needle = " ".join(part.translate(TYPOGRAPHY).lower().split()).strip(" .,;:\"'")
        if len(needle) < 8:
            continue
        line = folded.strip(" .")
        if len(line) >= 8 and line in needle:
            return [(text, True)]
        start = folded.find(needle)
        if start >= 0:
            end = start + len(needle)
            return [(text[:start], False), (text[start:end], True), (text[end:], False)]
    return [(text, False)]


def classify(number: int, text: str) -> tuple[str, int, str]:
    if number == 1 and text.startswith("# "):
        return "title", 1, text[2:]
    if heading := re.match(r"(#{2,6}) (.*)", text):
        return "heading", len(heading[1]), heading[2]
    if text.startswith("- "):
        return "item", 0, text[2:]
    if text.startswith("> "):
        return "quote", 0, text[2:]
    if text.startswith("|") and text.endswith("|") and len(text) > 1:
        return "row", 0, text
    return "text", 0, text


def blocks(
    lines: list[tuple[int, str]],
    highlight: tuple[int, int] | None,
    quote: str | None,
    sources: dict[int, str] | None = None,
) -> list[Block]:
    grouped: list[Block] = []
    for number, text in lines:
        kind, level, body = classify(number, text)
        highlighted = bool(highlight) and highlight[0] <= number <= highlight[1]
        line = Line(number, kind, level, highlighted=highlighted)
        if kind == "row":
            line.cells = [cell.strip() for cell in body.strip("|").split("|")]
            line.source = (sources or {}).get(number)
        else:
            line.segments = emphasize(body, quote) if highlighted else [(body, False)]
        group = {"item": "items", "quote": "quotes", "row": "rows"}.get(kind, kind)
        if grouped and grouped[-1].kind == group and group in {"items", "quotes", "rows"}:
            grouped[-1].lines.append(line)
            if group == "rows" and len(grouped[-1].lines) == 2:
                grouped[-1].lines[0].header = True
        else:
            grouped.append(Block(group, [line]))
    return grouped


def open_snapshot(store: IndexStore, snapshot: str | None) -> tuple[KnowledgeIndex, bool]:
    """The pinned snapshot when it is still retained, otherwise the current one."""
    if snapshot and SNAPSHOT_ID.fullmatch(snapshot) and not enabled("site_unpinned"):
        try:
            return store.open(snapshot), True
        except SnapshotUnavailable:
            pass
    return store.open(), False


def text_lines(index: KnowledgeIndex, document: str) -> list[tuple[int, str]]:
    return [
        (row["number"], row["text"])
        for row in index.connection.execute(
            "SELECT number, text FROM lines WHERE document=? ORDER BY number", (document,)
        )
    ]


def breadcrumbs(index: KnowledgeIndex, caller: Caller, provenance: dict) -> list[dict]:
    trail, parent = [], provenance.get("parent")
    while parent is not None:
        row = index.connection.execute(
            "SELECT * FROM documents WHERE id=?", (f"wiki-{parent}",)
        ).fetchone()
        if row is None:
            break
        if index.is_visible(caller, row["id"]):
            trail.append({"title": row["title"], "href": document_path(row)})
        parent = json.loads(row["provenance"]).get("parent")
    return trail[::-1]


def row_sources(index: KnowledgeIndex, caller: Caller, document: str) -> dict[int, str]:
    """Links from reference rows to their source lines, for visible sources only."""
    links = {}
    for row in index.connection.execute(
        "SELECT r.line, r.source_document, r.source_line FROM reference_rows r "
        "JOIN reference_tables t ON t.name = r.table_name WHERE t.document=?",
        (document,),
    ):
        if row["source_document"] and index.is_visible(caller, row["source_document"]):
            links[row["line"]] = (
                f"/d/{row['source_document']}?lines={row['source_line']}#L{row['source_line']}"
            )
    return links


def ticket_fields(lines: list[tuple[int, str]]) -> dict[str, str]:
    fields = {}
    for _number, text in lines[1:6]:
        for part in text.split(" | "):
            name, _, value = part.partition(": ")
            if value and name in {
                "Type",
                "Status",
                "Priority",
                "Site",
                "Components",
                "Created",
                "Resolved",
                "Links",
            }:
                fields[name] = value
    return fields


def document_page(
    store: IndexStore,
    caller: Caller,
    area: str,
    key: str,
    *,
    version: str | None = None,
    snapshot: str | None = None,
    lines: str | None = None,
    quote: str | None = None,
) -> dict:
    """Everything a document template needs; raises NotFound for missing and forbidden alike."""
    index, pinned = open_snapshot(store, snapshot)
    try:
        document = find_document(index, area, key, version)
        row = index.visible(caller, document)
        info = index.get_document(caller, document)
        provenance = json.loads(row["provenance"])
        content = text_lines(index, document)
        notices = []
        highlight = line_range(lines, row["line_count"])
        if snapshot and not pinned:
            notices.append(
                Notice(
                    "warning",
                    "The cited snapshot is no longer retained, so this is the current version "
                    "and the cited lines are not highlighted.",
                )
            )
            highlight = None
        elif pinned:
            notices += changed_since(store, caller, index.snapshot, row, content)
        return {
            "area": area,
            "document": document,
            "snapshot": index.snapshot,
            "pinned": pinned,
            "info": info,
            "provenance": provenance,
            "row": dict(row),
            "title": row["title"],
            "blocks": blocks(
                content,
                highlight,
                quote,
                row_sources(index, caller, document) if area == "reference" else None,
            ),
            "highlight": highlight,
            "notices": notices,
            "breadcrumbs": breadcrumbs(index, caller, provenance) if area == "wiki" else [],
            "fields": ticket_fields(content) if area == "ticketing" else {},
            "versions": [
                {**version_row, "href": f"/qms/documents/{row['series']}/v{version_row['version']}"}
                for version_row in info["versions"]
            ],
            "related": related(index, caller, info),
            "terms": glossary_terms(index, caller) if row["doc_type"] == "glossary" else [],
        }
    finally:
        index.close()


def related(index: KnowledgeIndex, caller: Caller, info: dict) -> dict:
    links = {}
    for name in ("supersedes", "superseded_by"):
        if info[name] and index.is_visible(caller, info[name]):
            other = index.visible(caller, info[name])
            links[name] = {
                "title": other["title"],
                "version": other["version"],
                "href": document_path(other),
            }
    return links


def changed_since(
    store: IndexStore, caller: Caller, snapshot: str, row: sqlite3.Row, content: list
) -> list[Notice]:
    current = store.open()
    try:
        if current.snapshot == snapshot:
            return []
        if not current.is_visible(caller, row["id"]):
            return [Notice("info", "This document is no longer published.")]
        if text_lines(current, row["id"]) == content:
            return []
        return [
            Notice(
                "info",
                "You are viewing the version an answer cited. The document has changed since.",
                document_path(current.visible(caller, row["id"])),
                "Open the current version",
            )
        ]
    finally:
        current.close()


def resolve(store: IndexStore, caller: Caller, document: str, snapshot: str | None) -> str:
    """The source-specific path of a document, or NotFound."""
    index, _pinned = open_snapshot(store, snapshot)
    try:
        return document_path(index.visible(caller, document))
    finally:
        index.close()


def visible_rows(index: KnowledgeIndex, caller: Caller, source: str) -> list[sqlite3.Row]:
    return [
        row
        for row in index.connection.execute(
            "SELECT * FROM documents WHERE source=? ORDER BY id", (source,)
        )
        if caller.sees(json.loads(row["sites"]), json.loads(row["roles"]))
    ]


def updated(row: sqlite3.Row) -> str | None:
    provenance = json.loads(row["provenance"])
    if row["source"] == "wiki":
        return provenance.get("updated")
    if row["source"] == "ticketing":
        return row["version"]
    if row["source"] == "qms":
        return row["effective_from"]
    return None


def summary(row: sqlite3.Row) -> dict:
    return {
        "title": row["title"],
        "href": document_path(row),
        "status": row["status"],
        "version": row["version"],
        "doc_type": row["doc_type"],
        "key": row["source_id"],
        "updated": updated(row),
    }


def home(index: KnowledgeIndex, caller: Caller) -> dict:
    rows = [row for source, _label, _href in AREAS for row in visible_rows(index, caller, source)]
    counts = {source: 0 for source, _label, _href in AREAS}
    for row in rows:
        counts[row["source"]] += 1
    recent = sorted(
        (row for row in rows if updated(row)),
        key=lambda row: (updated(row), row["id"]),
        reverse=True,
    )
    return {
        "counts": counts,
        "recent": [{**summary(row), "area": row["source"]} for row in recent[:8]],
    }


def wiki_tree(index: KnowledgeIndex, caller: Caller) -> list[dict]:
    """Visible pages nested under their nearest visible ancestor; hidden pages never appear."""
    parents = {
        row["source_id"]: json.loads(row["provenance"]).get("parent")
        for row in index.connection.execute("SELECT * FROM documents WHERE source='wiki'")
    }
    rows = visible_rows(index, caller, "wiki")
    visible = {row["source_id"] for row in rows}
    children: dict[str | None, list[sqlite3.Row]] = {}
    for row in rows:
        parent = parents.get(row["source_id"])
        while parent is not None and str(parent) not in visible:
            parent = parents.get(str(parent))
        children.setdefault(None if parent is None else str(parent), []).append(row)

    def node(row: sqlite3.Row) -> dict:
        nested = sorted(children.get(row["source_id"], []), key=lambda child: child["title"])
        return {**summary(row), "children": [node(child) for child in nested]}

    return [node(row) for row in sorted(children.get(None, []), key=lambda row: row["title"])]


def qms_register(
    index: KnowledgeIndex, caller: Caller, status: str | None = None, number: str | None = None
) -> list[dict]:
    series: dict[str, list[sqlite3.Row]] = {}
    for row in visible_rows(index, caller, "qms"):
        if (status and row["status"] != status) or (number and row["series"] != number):
            continue
        series.setdefault(row["series"], []).append(row)
    register = []
    for name, versions in sorted(series.items()):
        versions.sort(key=lambda row: int(row["version"]))
        register.append(
            {
                "number": name,
                "title": versions[-1]["title"],
                "doc_type": versions[-1]["doc_type"],
                "versions": [
                    summary(row)
                    | {"effective_from": row["effective_from"], "effective_to": row["effective_to"]}
                    for row in versions
                ],
            }
        )
    return register


def issues(
    index: KnowledgeIndex, caller: Caller, kind: str | None = None, status: str | None = None
) -> dict:
    rows = visible_rows(index, caller, "ticketing")
    shown = [
        row
        for row in rows
        if (not kind or row["doc_type"] == kind) and (not status or row["status"] == status)
    ]
    shown.sort(
        key=lambda row: (json.loads(row["provenance"]).get("created", ""), row["id"]), reverse=True
    )
    return {
        "issues": [
            summary(row) | {"created": json.loads(row["provenance"]).get("created")}
            for row in shown
        ],
        "kinds": sorted({row["doc_type"] for row in rows}),
        "statuses": sorted({row["status"] for row in rows}),
    }


def glossary_terms(index: KnowledgeIndex, caller: Caller) -> list[dict]:
    terms = []
    for row in index.connection.execute("SELECT * FROM terms ORDER BY term COLLATE NOCASE"):
        source = None
        if row["source_document"] and index.is_visible(caller, row["source_document"]):
            source = f"/d/{row['source_document']}?lines={row['source_line']}#L{row['source_line']}"
        terms.append(
            {
                "term": row["term"],
                "synonyms": json.loads(row["synonyms"]),
                "line": row["glossary_start"],
                "source": source,
            }
        )
    return terms


def search(index: KnowledgeIndex, caller: Caller, query: str, everything: bool) -> dict:
    result = index.search(caller, query[:200], include_inactive=everything, limit=20)
    labels = {source: label for source, label, _href in AREAS}
    groups: dict[str, list[dict]] = {}
    for match in result["matches"]:
        lines = f"{match['start_line']}-{match['end_line']}"
        groups.setdefault(match["source"], []).append(
            {
                **match,
                "snippet": "\n".join(
                    classify(0, line)[2] for line in match["snippet"].splitlines()
                ),
                "href": f"/d/{match['document']}?lines={lines}#L{match['start_line']}",
            }
        )
    return {
        "groups": [(source, labels[source], matches) for source, matches in groups.items()],
        "counts": result["counts"],
        "expanded": result["expanded_terms"],
    }
