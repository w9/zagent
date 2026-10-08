"""REQ-CITE-01: every recorded citation opens on the intranet at the lines the agent read."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from zagent.evals.adversarial import attack_knowledge
from zagent.evals.assertions import CITATION, NUMBERED_LINE
from zagent.evals.local_knowledge import current_snapshot, published_snapshots
from zagent.evals.schema import load_suite
from zagent.identity import GrantSigner
from zagent.privacy import IDENTIFIER_PATTERNS, TOKEN
from zknowledge.index import Caller, IndexStore
from zknowledge.site.app import create_site
from zknowledge.site.identity import SITES, STAFF, GrantVerifier
from zknowledge.site.pages import classify

ROOT = Path(__file__).parents[3]
CASSETTES = ROOT / "services/agent/zagent/cassettes"


class Lines(HTMLParser):
    """Rendered text of each canonical line anchor and which anchors are highlighted."""

    def __init__(self):
        super().__init__()
        self.text: dict[int, list[str]] = {}
        self.highlighted: set[int] = set()
        self.current, self.depth, self.skip = None, 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if self.current is None:
            if match := re.fullmatch(r"L([0-9]+)", attrs.get("id") or ""):
                self.current, self.depth = int(match[1]), 0
                self.text[self.current] = []
                if "hl" in classes:
                    self.highlighted.add(self.current)
            return
        self.depth += 1
        if self.skip or {"ln", "source-cell"} & classes:
            self.skip += 1

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if self.depth == 0:
            self.current = None
            return
        self.depth -= 1
        if self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.current is not None and not self.skip:
            self.text[self.current].append(data)


def recorded_citations():
    """Each citation in a recorded response, with the read_document result it cites."""
    for path in sorted(CASSETTES.glob("*.json")):
        cassette = json.loads(path.read_text())
        reads = []
        for message in cassette["request"]["messages"]:
            if message["role"] != "tool" or not isinstance(message.get("content"), str):
                continue
            try:
                result = json.loads(message["content"])
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict) and {"start_line", "text", "snapshot"} <= set(result):
                reads.append(result)
        responses = [*cassette.get("samples", {}).values()]
        if "response" in cassette:
            responses.append(cassette["response"])
        for response in responses:
            for match in CITATION.finditer((response.get("message") or {}).get("content") or ""):
                start = int(match[3])
                end = int(match[4] or start)
                read = next(
                    (
                        item
                        for item in reads
                        if item.get("document") == match[1]
                        and item.get("version") == match[2]
                        and item["start_line"] <= start <= end <= item["end_line"]
                    ),
                    None,
                )
                if read is not None:
                    yield path.name, match[1], start, end, read


@pytest.fixture(scope="module")
def snapshot_directories(tmp_path_factory):
    """The published snapshot and every poisoned snapshot an adversarial case published."""
    directories = {current_snapshot(): published_snapshots()}
    for case in load_suite(ROOT / "evals").cases:
        attack = case.adversarial
        if attack is not None and attack.ingress in {"kb_wiki", "kb_ticket"}:
            directory = tmp_path_factory.mktemp(case.id)
            snapshots, identifier = attack_knowledge(directory, attack.payload, attack.ingress)
            directories[identifier] = snapshots
    return directories


def expected(number: int, read_line: str) -> re.Pattern:
    """The rendered text of a read line; privacy tokens stand for the identifiers they replaced."""
    kind, _level, body = classify(number, read_line)
    body = re.sub(r"\s+", "", body.replace("|", "") if kind == "row" else body)
    parts = TOKEN.split(body)
    return re.compile("(.+?)".join(re.escape(part) for part in parts))


def test_every_recorded_citation_opens_the_lines_the_agent_read(snapshot_directories):
    key = Ed25519PrivateKey.generate()
    signer = GrantSigner(key)
    sites = {
        snapshot: TestClient(
            create_site(IndexStore(directory), verifier=GrantVerifier(key.public_key()))
        )
        for snapshot, directory in snapshot_directories.items()
    }
    checked = 0
    for cassette, document, start, end, read in recorded_citations():
        label = (cassette, document, start, end)
        snapshot = read["snapshot"]
        assert snapshot in sites, label
        index = IndexStore(snapshot_directories[snapshot]).open(snapshot)
        try:
            persona, site = next(
                (persona, site)
                for site in SITES
                for persona, (_name, _title, roles) in STAFF.items()
                if index.is_visible(Caller(site, list(roles)), document)
            )
        finally:
            index.close()
        token = signer.mint(
            site=site,
            persona=persona,
            document=document,
            snapshot=snapshot,
            lines=f"{start}-{end}",
        )
        page = sites[snapshot].get("/signin/grant", params={"token": token})
        assert page.status_code == 200, label
        lines = Lines()
        lines.feed(page.text)
        assert lines.highlighted == set(range(start, end + 1)), label
        numbered = {
            int(line[1]): line[2]
            for line in map(NUMBERED_LINE.fullmatch, read["text"].splitlines())
            if line
        }
        for number in range(start, end + 1):
            rendered = re.sub(r"\s+", "", "".join(lines.text[number]))
            match = expected(number, numbered[number]).fullmatch(rendered)
            assert match, (*label, number)
            tokens = TOKEN.findall(numbered[number])
            for token_text, identifier in zip(tokens, match.groups(), strict=True):
                pattern = IDENTIFIER_PATTERNS.get(token_text[1:].split("_")[0])
                assert pattern is None or pattern.fullmatch(identifier), (*label, token_text)
        checked += 1
    assert checked >= 25
