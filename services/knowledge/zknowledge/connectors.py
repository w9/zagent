import csv
import json
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import yaml

from zknowledge.document import Block, Document, markdown_blocks, render

AC = "urn:confluence:ac"
RI = "urn:confluence:ri"
ENTITIES = {"&nbsp;": "&#160;", "&mdash;": "&#8212;", "&ndash;": "&#8211;", "&rarr;": "&#8594;"}
NOTE_MACROS = {"info": "Info", "note": "Note", "warning": "Warning", "tip": "Tip", "panel": "Note"}
PDF_FURNITURE = re.compile(
    r"^(?:MERIDIAN CLINICAL GENOMICS CORE.*|Page \d+ of \d+|CONTROLLED COPY.*|"
    r"Printed copies are uncontrolled.*|Document: [A-Z]+-[A-Z]+-\d+.*Page \d+.*)$"
)
PDF_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Z0-9 ,/&()'-]+)$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def wiki_blocks(xhtml: str) -> tuple[list[Block], list[str]]:
    for entity, replacement in ENTITIES.items():
        xhtml = xhtml.replace(entity, replacement)
    root = ElementTree.fromstring(f'<root xmlns:ac="{AC}" xmlns:ri="{RI}">{xhtml}</root>')
    blocks: list[Block] = []
    links: list[str] = []

    def inline(element) -> str:
        parts = [element.text or ""]
        for child in element:
            name = local(child.tag)
            if name == "link":
                page = child.find(f"{{{RI}}}page")
                body = child.find(f"{{{AC}}}plain-text-link-body")
                title = page.get(f"{{{RI}}}content-title") if page is not None else None
                if title:
                    links.append(title)
                parts.append(body.text if body is not None and body.text else title or "")
            elif name == "br":
                parts.append(" ")
            elif name not in {"image", "structured-macro"}:
                parts.append(inline(child))
            parts.append(child.tail or "")
        return " ".join("".join(parts).split())

    def visit(element) -> None:
        for child in element:
            name = local(child.tag)
            if re.fullmatch(r"h[1-6]", name):
                blocks.append(Block("heading", inline(child), int(name[1]) + 1))
            elif name == "p":
                if text := inline(child):
                    blocks.append(Block("paragraph", text))
            elif name in {"ul", "ol"}:
                for item in child:
                    nested = [part for part in item if local(part.tag) in {"ul", "ol"}]
                    for part in nested:
                        item.remove(part)
                    blocks.append(Block("item", inline(item)))
                    for part in nested:
                        holder = ElementTree.Element("div")
                        holder.append(part)
                        visit(holder)
            elif name == "table":
                for row in child.iter():
                    if local(row.tag) == "tr":
                        cells = [inline(cell) for cell in row if local(cell.tag) in {"th", "td"}]
                        blocks.append(Block("row", " | ".join(cells)))
            elif name == "structured-macro":
                macro = child.get(f"{{{AC}}}name", "")
                plain = child.find(f"{{{AC}}}plain-text-body")
                rich = child.find(f"{{{AC}}}rich-text-body")
                if macro == "code" and plain is not None:
                    blocks.extend(Block("code", line) for line in (plain.text or "").splitlines())
                elif macro in NOTE_MACROS and rich is not None:
                    text = " ".join(inline(part) for part in rich)
                    blocks.append(Block("note", f"{NOTE_MACROS[macro]}: {text}"))
                elif rich is not None:
                    visit(rich)
            elif name in {"div", "section", "span", "layout", "layout-section", "layout-cell"}:
                visit(child)

    visit(root)
    return blocks, links


def load_wiki(root: Path) -> list[Document]:
    space = json.loads((root / "space.json").read_text())
    base = space["space"]["base_url"]
    documents = []
    for page in space["pages"]:
        blocks, links = wiki_blocks((root / "pages" / f"{page['id']}.xhtml").read_text())
        lines, sections = render(
            page["title"],
            blocks,
            [f"Wiki page {page['id']} | Version {page['version']} | Updated {page['updated']}"],
        )
        documents.append(
            Document(
                id=f"wiki-{page['id']}",
                source="wiki",
                source_id=str(page["id"]),
                title=page["title"],
                doc_type="wiki_page",
                version=str(page["version"]),
                status=page["status"],
                lines=lines,
                sections=sections,
                applies_to=page.get("applies_to", []),
                labels=page.get("labels", []),
                sites=page["restrictions"]["sites"],
                roles=page["restrictions"]["roles"],
                provenance={
                    "url": f"{base}/{page['id']}",
                    "parent": page.get("parent"),
                    "updated": page["updated"],
                    "updated_by_role": page["updated_by_role"],
                },
                links=links,
            )
        )
    return documents


def pdf_blocks(text: str) -> list[Block]:
    """PDF text exports: drop page furniture and re-join hard-wrapped paragraphs and items."""
    blocks: list[Block] = []
    paragraph: list[str] = []
    item: list[str] = []

    def flush():
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()
        if item:
            blocks.append(Block("item", " ".join(item)))
            item.clear()

    for raw in text.splitlines():
        line = raw.strip()
        if PDF_FURNITURE.match(line):
            continue
        if not line:
            flush()
        elif heading := PDF_HEADING.match(line):
            flush()
            title = heading.group(2).title()
            blocks.append(Block("heading", title, heading.group(1).count(".") + 2))
        elif bullet := re.match(r"^(?:[-\u2022*]|[a-z]\))\s+(.*)$", line):
            flush()
            item.append(bullet.group(1))
        elif line.startswith("|"):
            flush()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            blocks.append(Block("row", " | ".join(cells)))
        elif item:
            item.append(line)
        else:
            paragraph.append(line)
    flush()
    return blocks


def load_qms(root: Path) -> list[Document]:
    register = json.loads((root / "register.json").read_text())
    documents = []
    for entry in register["documents"]:
        body = (root / entry["file"]).read_text()
        blocks = pdf_blocks(body) if entry["file"].endswith(".pdf.txt") else markdown_blocks(body)
        number, version = entry["number"], entry["version"]
        lines, sections = render(
            f"{number} v{version}: {entry['title']}",
            blocks,
            [
                f"Document: {number} | Version {version} | Status: {entry['status']} | "
                f"Effective: {entry.get('effective_from') or 'not yet effective'}",
                f"Owner: {entry['owner_role']} | Approvers: {', '.join(entry['approver_roles'])}",
            ],
        )
        documents.append(
            Document(
                id=f"{slug(number)}-v{version}",
                source="qms",
                source_id=number,
                title=entry["title"],
                doc_type=entry["type"],
                version=str(version),
                status=entry["status"],
                lines=lines,
                sections=sections,
                effective_from=entry.get("effective_from"),
                effective_to=entry.get("effective_to"),
                applies_to=entry.get("applies_to", []),
                labels=entry.get("labels", []),
                sites=entry["sites"],
                roles=entry["roles"],
                provenance={
                    "system": register["system"],
                    "file": entry["file"],
                    "owner_role": entry["owner_role"],
                    "approver_roles": entry["approver_roles"],
                    "change_reference": entry.get("change_reference"),
                },
                series=number,
            )
        )
    for number in {document.series for document in documents}:
        released = sorted(
            (
                document
                for document in documents
                if document.series == number and document.status != "draft"
            ),
            key=lambda document: int(document.version),
        )
        for older, newer in zip(released, released[1:], strict=False):
            older.superseded_by, newer.supersedes = newer.id, older.id
    return documents


def load_tickets(root: Path) -> list[Document]:
    export = json.loads((root / "export.json").read_text())
    documents = []
    for issue in export["issues"]:
        blocks = [Block("heading", "Description", 2), *markdown_blocks(issue["description"])]
        if issue.get("comments"):
            blocks.append(Block("heading", "Comments", 2))
            for index, comment in enumerate(issue["comments"], 1):
                blocks.append(
                    Block(
                        "heading",
                        f"Comment {index} ({comment['author_role']}, {comment['created']})",
                        3,
                    )
                )
                blocks.extend(markdown_blocks(comment["body"]))
        preamble = [
            f"Type: {issue['type']} | Status: {issue['status']} | Priority: {issue['priority']} | "
            f"Site: {issue.get('site') or 'all'}",
            f"Components: {', '.join(issue.get('components', [])) or 'none'}",
            f"Created: {issue['created']} | Resolved: {issue.get('resolved') or 'unresolved'}",
        ]
        if issue.get("links"):
            preamble.append("Links: " + ", ".join(issue["links"]))
        lines, sections = render(f"{issue['key']}: {issue['summary']}", blocks, preamble)
        documents.append(
            Document(
                id=slug(issue["key"]),
                source="ticketing",
                source_id=issue["key"],
                title=issue["summary"],
                doc_type=issue["type"],
                version=issue.get("updated", issue["created"]),
                status=issue["status"],
                lines=lines,
                sections=sections,
                applies_to=issue.get("components", []),
                labels=issue.get("labels", []),
                sites=issue["access"]["sites"],
                roles=issue["access"]["roles"],
                provenance={
                    "system": export["system"],
                    "reporter_role": issue["reporter_role"],
                    "created": issue["created"],
                },
                links=issue.get("links", []),
            )
        )
    return documents


def frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    header, body = text[4:].split("\n---\n", 1)
    return yaml.safe_load(header), body


def load_wikipedia(root: Path) -> list[Document]:
    documents = []
    for path in sorted(root.glob("*.md")):
        meta, body = frontmatter(path.read_text())
        lines, sections = render(
            meta["title"],
            markdown_blocks(body),
            [f"Wikipedia article, revision {meta['revision_id']}, licensed {meta['license']}"],
        )
        documents.append(
            Document(
                id=f"wp-{path.stem}",
                source="wikipedia",
                source_id=str(meta["revision_id"]),
                title=meta["title"],
                doc_type="encyclopedia",
                version=str(meta["revision_id"]),
                status="reference",
                lines=lines,
                sections=sections,
                provenance={
                    key: meta[key]
                    for key in ("url", "license", "retrieved", "attribution")
                    if key in meta
                },
            )
        )
    return documents


def reference_table(spec: dict, rows: list[dict]) -> tuple[Document, dict]:
    columns = list(spec["columns"])
    notes = spec.get("column_notes", {})
    blocks = [Block("paragraph", spec["description"]), Block("heading", "Columns", 2)]
    blocks += [
        Block("item", f"{name} ({kind})" + (f": {notes[name]}" if name in notes else ""))
        for name, kind in spec["columns"].items()
    ]
    blocks.append(Block("heading", "Rows", 2))
    blocks.append(Block("row", " | ".join(columns)))
    blocks += [Block("row", " | ".join(row[name] for name in columns)) for row in rows]
    identifier = "ref-" + slug(spec["name"])
    lines, sections = render(f"Reference table: {spec['title']}", blocks)
    first_row = len(lines) - len(rows) + 1
    table = {
        "name": spec["name"],
        "title": spec["title"],
        "description": spec["description"],
        "columns": spec["columns"],
        "document": identifier,
        "cite_values": spec.get("cite_values", []),
        "rows": [
            {
                "values": {name: typed(row[name], spec["columns"][name]) for name in columns},
                "raw": {name: row[name] for name in columns},
                "line": first_row + index,
                "source_document": row.get("source_document") or None,
                "source_anchor": row.get("source_anchor") or None,
            }
            for index, row in enumerate(rows)
        ],
    }
    return reference_document(identifier, spec, lines, sections), table


def register_table(qms: list[Document], exported: str) -> tuple[Document, dict]:
    spec = {
        "name": "document_register",
        "title": "Controlled document register",
        "description": "Generated from the QMS export: one row per released controlled document "
        "version, including superseded and retired versions. Drafts are not listed.",
        "columns": {
            "number": "string",
            "version": "integer",
            "title": "string",
            "type": "string",
            "status": "string",
            "effective_from": "string",
            "effective_to": "string",
        },
        "cite_values": ["number"],
        "version": exported,
        "owner_role": "qa-officer",
    }
    rows = [
        {
            "number": document.series,
            "version": document.version,
            "title": document.title,
            "type": document.doc_type,
            "status": document.status,
            "effective_from": document.effective_from or "",
            "effective_to": document.effective_to or "",
            "source_document": document.id,
            "source_anchor": f"{document.series} v{document.version}:",
        }
        for document in sorted(qms, key=lambda document: (document.series, int(document.version)))
        if document.status != "draft"
    ]
    return reference_table(spec, rows)


def load_reference(root: Path) -> tuple[list[Document], list[dict], list[dict]]:
    """Tables and glossary; source citations are resolved later against the other documents."""
    documents, tables, terms = [], [], []
    for spec in json.loads((root / "tables.json").read_text()):
        with (root / spec["file"]).open(newline="") as handle:
            document, table = reference_table(spec, list(csv.DictReader(handle)))
        documents.append(document)
        tables.append(table)
    glossary = yaml.safe_load((root / "glossary.yaml").read_text())
    blocks = [Block("paragraph", glossary["description"])]
    for entry in glossary["terms"]:
        blocks.append(Block("heading", entry["term"], 2))
        blocks.append(Block("paragraph", entry["definition"]))
        if entry.get("synonyms"):
            blocks.append(Block("paragraph", "Synonyms: " + ", ".join(entry["synonyms"]) + "."))
    lines, sections = render("Glossary", blocks)
    documents.append(reference_document("ref-glossary", glossary, lines, sections))
    for entry, section in zip(glossary["terms"], sections[1:], strict=True):
        terms.append(
            {
                **entry,
                "synonyms": entry.get("synonyms", []),
                "glossary_lines": (section.start_line, section.end_line),
            }
        )
    return documents, tables, terms


def reference_document(identifier, spec, lines, sections) -> Document:
    return Document(
        id=identifier,
        source="reference",
        source_id=spec.get("name", "glossary"),
        title=spec["title"],
        doc_type="reference_table" if identifier != "ref-glossary" else "glossary",
        version=str(spec["version"]),
        status="reference",
        lines=lines,
        sections=sections,
        provenance={"owner_role": spec["owner_role"]},
    )


def typed(value: str, kind: str):
    if value == "":
        return None
    if kind == "number":
        number = float(value)
        return int(number) if number.is_integer() else number
    if kind == "integer":
        return int(value)
    if kind == "boolean":
        return value.lower() == "true"
    return value


def load_corpus(root: Path) -> tuple[list[Document], list[dict], list[dict]]:
    qms = load_qms(root / "qms")
    exported = json.loads((root / "qms" / "register.json").read_text())["exported"]
    register, register_rows = register_table(qms, exported)
    documents = [
        *qms,
        *load_wiki(root / "wiki"),
        *load_tickets(root / "ticketing"),
        *load_wikipedia(root / "public" / "wikipedia"),
    ]
    references, tables, terms = load_reference(root / "reference")
    return [*documents, *references, register], [*tables, register_rows], terms
