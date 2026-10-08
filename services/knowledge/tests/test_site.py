import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from knowledge_fixtures import *  # noqa: F403
from zknowledge.index import Caller, IndexStore, build_index
from zknowledge.site.app import create_site
from zknowledge.site.pages import classify, document_path

SIGNED_OUT = Caller(None, [])
RESTRICTED = {
    "sop-qc-001-v4": "/qms/documents/SOP-QC-001/v4",
    "chg-0024": "/servicedesk/browse/CHG-0024",
    "inc-0142": "/servicedesk/browse/INC-0142",
    "wiki-40205": "/wiki/display/MCGC/40205",
}


class LineText(HTMLParser):
    """Text of every element anchored as a canonical line, without line numbers or links out."""

    def __init__(self):
        super().__init__()
        self.text: dict[int, list[str]] = {}
        self.highlighted: set[int] = set()
        self.current, self.depth, self.skip = None, 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if self.current is None:
            if match := re.fullmatch(r"L([0-9]+)", attrs.get("id") or ""):
                self.current, self.depth = int(match[1]), 0
                self.text[self.current] = []
                if "hl" in classes:
                    self.highlighted.add(self.current)
            return
        self.depth += 1
        if self.skip or {"ln", "source-cell"} & set(classes):
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


def parsed(html: str) -> LineText:
    parser = LineText()
    parser.feed(html)
    return parser


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


@pytest.fixture(scope="module")
def site(published_index):
    store, _identifier, _warnings = published_index
    return TestClient(create_site(store), follow_redirects=False)


def test_every_visible_document_renders_each_canonical_line_once(site, published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        documents = [
            row
            for row in index.connection.execute("SELECT * FROM documents ORDER BY id")
            if index.is_visible(SIGNED_OUT, row["id"])
        ]
        assert len(documents) > 150
        for row in documents:
            response = site.get(document_path(row))
            assert response.status_code == 200, row["id"]
            lines = parsed(response.text).text
            expected = list(
                index.connection.execute(
                    "SELECT number, text FROM lines WHERE document=? ORDER BY number", (row["id"],)
                )
            )
            assert sorted(lines) == [number for number, _text in expected], row["id"]
            for number, text in expected:
                kind, _level, body = classify(number, text)
                wanted = body.replace("|", "") if kind == "row" else body
                assert compact("".join(lines[number])) == compact(wanted), (row["id"], number)
    finally:
        index.close()


def test_citation_links_resolve_to_the_source_system_with_the_lines_highlighted(site):
    response = site.get("/d/sop-qc-001-v3?lines=10-12&q=Tumor libraries intended for somatic")
    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("/qms/documents/SOP-QC-001/v3?") and location.endswith("#L10")
    page = site.get(location.split("#")[0])
    lines = parsed(page.text)
    assert lines.highlighted == {10, 11, 12}
    assert '<mark class="quote">Tumor libraries intended for somatic</mark>' in page.text
    assert site.get("/d/sop-qc-001-v3?lines=12-10").status_code == 302
    assert not parsed(site.get("/qms/documents/SOP-QC-001/v3?lines=12-10").text).highlighted
    assert parsed(site.get("/qms/documents/SOP-QC-001/v3?lines=99").text).highlighted == set()
    for target in ("/d/no-such-document", "/d/Bad%20Id", "/d/..%2Fetc"):
        assert site.get(target).status_code == 404
    assert site.get("/d/wiki-40218").headers["location"] == "/wiki/display/MCGC/40218"


def test_forbidden_documents_are_indistinguishable_from_missing_ones(site):
    missing = site.get("/qms/documents/SOP-QC-001/v9")
    assert missing.status_code == 404
    for document, path in RESTRICTED.items():
        assert site.get(path).text == missing.text, document
        assert site.get(f"/d/{document}").text == missing.text, document
    listings = {
        "/qms": "sop-qc-001-v4",
        "/qms?status=draft": "/v4",
        "/qms/documents/SOP-QC-001": "/v4",
        "/qms/documents/SOP-QC-001/v3": "/v4",
        "/servicedesk": "CHG-0024",
        "/wiki": "40205",
        "/search?q=45x+tumor+minimum+draft&all=1": "sop-qc-001-v4",
    }
    for path, leak in listings.items():
        response = site.get(path)
        assert response.status_code == 200, path
        assert leak not in response.text, path
    assert "INC-0142" not in site.get("/servicedesk").text
    assert "Staff promotion" not in site.get("/wiki").text


def test_every_page_is_escaped_and_forbids_scripts(corpus_copy, tmp_path):
    page = corpus_copy / "wiki/pages/40218.xhtml"
    page.write_text(
        page.read_text()
        + "<p>&lt;script&gt;alert(1)&lt;/script&gt; &lt;img src=x onerror=alert(2)&gt;</p>"
    )
    build_index(corpus_copy, tmp_path / "snapshots")
    site = TestClient(create_site(IndexStore(tmp_path / "snapshots")))
    response = site.get("/wiki/display/MCGC/40218")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script" not in response.text and "<img" not in response.text
    policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in policy and "script-src" not in policy
    assert response.headers["referrer-policy"] == "no-referrer"


def test_citations_open_the_snapshot_they_were_made_against(corpus_copy, tmp_path):
    directory = tmp_path / "snapshots"
    original, _ = build_index(corpus_copy, directory, current=False)
    sop = corpus_copy / "qms/files/SOP-QC-001_v3.md"
    sop.write_text(
        sop.read_text().replace(
            "Review the sample and library", "Always review the sample and library"
        )
    )
    current, _ = build_index(corpus_copy, directory)
    assert current != original
    site = TestClient(create_site(IndexStore(directory)))
    path = "/qms/documents/SOP-QC-001/v3"
    pinned = site.get(f"{path}?snapshot={original}&lines=14")
    assert parsed(pinned.text).highlighted == {14}
    assert "Always review" not in pinned.text
    assert "The document has changed since" in pinned.text
    latest = site.get(f"{path}?snapshot={current}&lines=14")
    assert "Always review" in latest.text and "changed since" not in latest.text
    unchanged = site.get(f"/wiki/display/MCGC/40100?snapshot={original}")
    assert "changed since" not in unchanged.text
    expired = site.get(f"{path}?snapshot={'0' * 64}&lines=14")
    assert "no longer retained" in expired.text
    assert not parsed(expired.text).highlighted
