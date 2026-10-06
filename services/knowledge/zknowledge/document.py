import re
from dataclasses import dataclass, field
from typing import Literal

SOURCES = ("wiki", "qms", "ticketing", "reference", "wikipedia")
SITES = ("northgate", "lakeside", "sequoia", "cedar", "harbor")
ROLES = ("lab-technologist", "analyst", "qa-officer", "lab-director")
ACTIVE = frozenset({"effective", "current", "open", "resolved", "reference"})
MAX_LINE = 400
DOCUMENT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
ABBREVIATIONS = ("e.g.", "i.e.", "et al.", "vs.", "Fig.", "approx.", "No.", "Dr.", "St.", "cf.")


@dataclass(frozen=True)
class Block:
    kind: Literal["heading", "paragraph", "item", "row", "code", "note"]
    text: str
    level: int = 0


@dataclass
class Section:
    path: str
    heading: str
    level: int
    start_line: int
    end_line: int


@dataclass
class Document:
    id: str
    source: str
    source_id: str
    title: str
    doc_type: str
    version: str
    status: str
    lines: list[str]
    sections: list[Section]
    effective_from: str | None = None
    effective_to: str | None = None
    applies_to: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    sites: list[str] = field(default_factory=lambda: ["all"])
    roles: list[str] = field(default_factory=lambda: ["all"])
    provenance: dict = field(default_factory=dict)
    series: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    links: list[str] = field(default_factory=list)


def sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    protected = text
    for index, abbreviation in enumerate(ABBREVIATIONS):
        protected = protected.replace(abbreviation, f"\x00{index}\x00")
    pieces = SENTENCE_END.split(protected)
    restored = []
    for piece in pieces:
        for index, abbreviation in enumerate(ABBREVIATIONS):
            piece = piece.replace(f"\x00{index}\x00", abbreviation)
        restored.extend(wrap(piece))
    return restored


def wrap(text: str, width: int = MAX_LINE) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


def markdown_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    paragraph: list[str] = []
    fenced = False

    def flush():
        if paragraph:
            blocks.append(Block("paragraph", " ".join(paragraph)))
            paragraph.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            flush()
            fenced = not fenced
            continue
        if fenced:
            blocks.append(Block("code", line))
            continue
        stripped = line.strip()
        if not stripped:
            flush()
        elif heading := re.match(r"^(#{1,6})\s+(.*)$", stripped):
            flush()
            blocks.append(Block("heading", heading.group(2).strip(), len(heading.group(1))))
        elif item := re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", stripped):
            flush()
            blocks.append(Block("item", item.group(1)))
        elif stripped.startswith("|"):
            flush()
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
                blocks.append(Block("row", " | ".join(cells)))
        elif stripped.startswith(">"):
            flush()
            blocks.append(Block("note", stripped.lstrip("> ").strip()))
        else:
            paragraph.append(stripped)
    flush()
    return blocks


def render(title: str, blocks: list[Block], preamble: list[str] = ()) -> tuple[list, list]:
    """Canonical citation lines: one sentence, list item, table row or code line per line."""
    lines = [f"# {title}", *preamble]
    sections = [Section("0", title, 1, 1, 0)]
    counters: list[int] = []
    for block in blocks:
        if block.kind == "heading":
            depth = max(1, block.level - 1)
            counters = counters[:depth]
            while len(counters) < depth:
                counters.append(0)
            counters[-1] += 1
            lines.append("#" * (depth + 1) + " " + block.text)
            sections.append(Section(".".join(map(str, counters)), block.text, depth, len(lines), 0))
        elif block.kind == "paragraph":
            lines.extend(sentences(block.text))
        elif block.kind == "item":
            lines.extend("- " + piece for piece in wrap(" ".join(block.text.split())))
        elif block.kind == "row":
            lines.extend("| " + piece + " |" for piece in wrap(block.text))
        elif block.kind == "note":
            lines.extend("> " + piece for piece in sentences(block.text))
        elif block.text.strip():
            lines.extend(wrap(block.text) or [""])
    for index, section in enumerate(sections):
        following = [
            other.start_line
            for other in sections[index + 1 :]
            if section.path == "0" or other.level <= section.level
        ]
        section.end_line = (following[0] - 1) if following and section.path != "0" else len(lines)
    return lines, sections
