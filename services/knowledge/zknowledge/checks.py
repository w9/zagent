import re
from collections import Counter

from zknowledge.document import (
    DOCUMENT_ID,
    MAX_LINE,
    ROLES,
    SITES,
    SOURCES,
    Document,
)

MAX_DOCUMENT_LINES = 3000
MAX_DEFINITION = 600
# The knowledge team's own scan: generic personal data, not hospital identifier formats.
PERSONAL_DATA = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "phone": re.compile(r"(?<!\d)(?:\+1[ -]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"),
    "ssn": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
}
REQUIRED_PROVENANCE = {
    "wiki": ("url", "updated", "updated_by_role"),
    "qms": ("system", "file", "owner_role", "approver_roles"),
    "ticketing": ("system", "reporter_role", "created"),
    "reference": ("owner_role",),
    "wikipedia": ("url", "license", "retrieved", "attribution"),
}
STATUSES = {
    "wiki": {"current", "archived"},
    "qms": {"effective", "superseded", "retired", "draft"},
    "ticketing": {"open", "resolved"},
    "reference": {"reference"},
    "wikipedia": {"reference"},
}


class PublishError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("Knowledge publication failed:\n" + "\n".join(problems))
        self.problems = problems


def anchor_line(document: Document, anchor: str) -> int | None:
    return next((number for number, text in enumerate(document.lines, 1) if anchor in text), None)


def resolve_citations(documents: list[Document], tables: list[dict], terms: list[dict]) -> list:
    problems = []
    index = {document.id: document for document in documents}

    def resolve(owner: str, item: dict) -> None:
        source, anchor = item.get("source_document"), item.get("source_anchor")
        if not source:
            problems.append(f"{owner}: missing source citation")
            return
        document = index.get(source)
        line = anchor_line(document, anchor) if document and anchor else None
        if line is None:
            problems.append(f"{owner}: anchor {anchor!r} not found in {source}")
        item["source_line"] = line

    for table in tables:
        for ordinal, row in enumerate(table["rows"], 1):
            resolve(f"{table['name']} row {ordinal}", row)
    for term in terms:
        resolve(f"glossary {term['term']!r}", term)
    return problems


def check_corpus(
    documents: list[Document], tables: list[dict], terms: list[dict], conflicts: dict
) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    counts = Counter(document.id for document in documents)
    errors += [f"duplicate document id {name}" for name, count in counts.items() if count > 1]
    titles = {document.title for document in documents} | {
        document.source_id for document in documents
    }
    index = {document.id: document for document in documents}
    for document in documents:
        where = f"{document.id}:"
        if not DOCUMENT_ID.fullmatch(document.id):
            errors.append(f"{where} invalid document id")
        if document.source not in SOURCES:
            errors.append(f"{where} unknown source {document.source}")
        elif document.status not in STATUSES[document.source]:
            errors.append(f"{where} status {document.status} is not valid for {document.source}")
        missing = [
            key
            for key in REQUIRED_PROVENANCE.get(document.source, ())
            if not document.provenance.get(key)
        ]
        if missing:
            errors.append(f"{where} missing provenance {', '.join(missing)}")
        if not document.version:
            errors.append(f"{where} missing version")
        if not document.sites or any(site not in (*SITES, "all") for site in document.sites):
            errors.append(f"{where} invalid site labels {document.sites}")
        if not document.roles or any(role not in (*ROLES, "all") for role in document.roles):
            errors.append(f"{where} invalid role labels {document.roles}")
        if document.status == "draft" and "all" in document.roles:
            errors.append(f"{where} drafts must be restricted to named roles")
        if len(document.lines) > MAX_DOCUMENT_LINES:
            errors.append(f"{where} exceeds {MAX_DOCUMENT_LINES} lines")
        for number, text in enumerate(document.lines, 1):
            if len(text) > MAX_LINE:
                errors.append(f"{where}L{number} exceeds {MAX_LINE} characters")
            for kind, pattern in PERSONAL_DATA.items():
                for match in pattern.finditer(text):
                    if kind == "email" and match.group().endswith(".example"):
                        continue
                    errors.append(f"{where}L{number} contains a possible {kind}")
        for link in document.links:
            if link not in titles and link.lower() not in index:
                warnings.append(f"{where} broken link to {link!r}")
        for relation in ("supersedes", "superseded_by"):
            target = getattr(document, relation)
            if target and target not in index:
                errors.append(f"{where} {relation} {target} does not exist")
    series = Counter(
        document.series
        for document in documents
        if document.source == "qms" and document.status == "effective"
    )
    for name in {document.series for document in documents if document.source == "qms"}:
        retired = all(
            document.status == "retired" for document in documents if document.series == name
        )
        if series[name] != 1 and not retired:
            errors.append(f"{name}: expected exactly one effective version, found {series[name]}")
    for document in documents:
        if document.superseded_by and index[document.superseded_by].supersedes != document.id:
            errors.append(f"{document.id}: supersession chain is not reciprocal")
    allowed = {
        (item["table"], item["row"]) for item in conflicts.get("allowed_value_mismatches", [])
    }
    for table in tables:
        for ordinal, row in enumerate(table["rows"], 1):
            line = row.get("source_line")
            if line is None:
                continue
            text = index[row["source_document"]].lines[line - 1]
            for column in table["cite_values"]:
                value = row["raw"][column]
                if value and not re.search(rf"(?<![\w.]){re.escape(value)}(?!\d)", text):
                    if (table["name"], ordinal) not in allowed:
                        errors.append(
                            f"{table['name']} row {ordinal}: {column}={value} is not stated in "
                            f"{row['source_document']}:L{line}"
                        )
    for term in terms:
        if len(term["definition"]) > MAX_DEFINITION:
            errors.append(f"glossary {term['term']!r}: definition exceeds {MAX_DEFINITION}")
    for conflict in conflicts.get("conflicts", []):
        for name in conflict["documents"]:
            if name not in index:
                errors.append(f"conflict {conflict['id']}: unknown document {name}")
    return errors, warnings
