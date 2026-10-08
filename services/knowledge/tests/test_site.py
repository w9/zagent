import re
import time
import uuid
from html.parser import HTMLParser

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from knowledge_fixtures import *  # noqa: F403
from zknowledge.index import Caller, IndexStore, build_index
from zknowledge.site import identity
from zknowledge.site.app import create_site
from zknowledge.site.pages import AREAS, classify, document_path

SIGNED_OUT = Caller(None, [])
GRANT_KEY = Ed25519PrivateKey.generate()
RESTRICTED = {
    "sop-qc-001-v4": "/qms/documents/SOP-QC-001/v4",
    "chg-0024": "/servicedesk/browse/CHG-0024",
    "inc-0142": "/servicedesk/browse/INC-0142",
    "wiki-40205": "/wiki/display/MCGC/40205",
}
INDEXES = {"wiki": "/wiki", "qms": "/qms", "ticketing": "/servicedesk", "wikipedia": "/library"}


def grant(persona="qa-officer", *, key=GRANT_KEY, now=None, lifetime=60, **changes):
    issued = int(time.time() if now is None else now)
    claims = {
        "iss": "zagent-bff",
        "aud": "zknowledge-site",
        "iat": issued,
        "exp": issued + lifetime,
        "jti": uuid.uuid4().hex,
        "persona": persona,
        "site": "northgate",
        "roles": list(identity.STAFF[persona][2]),
        "document": "sop-qc-001-v4",
        "lines": "7-9",
        **changes,
    }
    return jwt.encode(claims, key, algorithm="EdDSA")


def signed_in_client(store, persona: str, site: str = "northgate") -> TestClient:
    client = TestClient(create_site(store), follow_redirects=False)
    response = client.post("/signin", data={"persona": persona, "site": site, "next": "/qms"})
    assert response.status_code == 303 and response.headers["location"] == "/qms"
    return client


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
    def page(path):
        response = site.get(path)
        return response.status_code, response.text.replace(path, "PATH")

    missing = page("/qms/documents/SOP-QC-001/v9")
    assert missing[0] == 404
    for document, path in RESTRICTED.items():
        assert page(path) == missing, document
        assert page(f"/d/{document}") == missing, document
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


def test_each_signed_in_persona_sees_exactly_what_the_index_allows(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        rows = list(index.connection.execute("SELECT * FROM documents ORDER BY id"))
        visitors = [(persona, "northgate") for persona in identity.STAFF] + [
            ("analyst", "lakeside")
        ]
        for persona, site in visitors:
            client = signed_in_client(store, persona, site)
            caller = Caller(site, list(identity.STAFF[persona][2]))
            visible = {row["id"] for row in rows if index.is_visible(caller, row["id"])}
            hidden = {document_path(row) for row in rows if row["id"] not in visible}
            series = {f"/qms/documents/{row['series']}" for row in rows if row["source"] == "qms"}
            hidden |= series - {
                f"/qms/documents/{row['series']}"
                for row in rows
                if row["source"] == "qms" and row["id"] in visible
            }
            pages = ["/", "/reference", *INDEXES.values(), *sorted(series - hidden)]
            for row in rows:
                response = client.get(document_path(row))
                assert response.status_code == (200 if row["id"] in visible else 404), (
                    persona,
                    site,
                    row["id"],
                )
                if row["id"] in visible:
                    pages.append(document_path(row))
            # No page, version list, supersession link, glossary entry or table row links to
            # a document this visitor cannot open.
            for path in pages:
                links = set(re.findall(r'href="([^"?#]+)', client.get(path).text))
                assert not links & hidden, (persona, site, path, links & hidden)
            for source, path in INDEXES.items():
                page = client.get(path).text
                listed = {
                    row["id"]
                    for row in rows
                    if row["source"] == source and f'href="{document_path(row)}"' in page
                }
                expected = {row["id"] for row in rows if row["source"] == source} & visible
                assert listed == expected, (persona, site, source)
            found = client.get("/search?q=proposed+45x+tumor+minimum+draft&all=1").text
            assert ("sop-qc-001-v4" in found) is ("sop-qc-001-v4" in visible), persona
    finally:
        index.close()
    assert {source for source, _label, _path in AREAS} >= set(INDEXES)


def test_citation_grants_sign_the_workbench_persona_in_once(published_index):
    store, _identifier, _warnings = published_index
    verifier = identity.GrantVerifier(GRANT_KEY.public_key())
    client = TestClient(create_site(store, verifier=verifier), follow_redirects=False)
    token = grant()
    response = client.get("/signin/grant", params={"token": token})
    assert response.status_code == 303 and response.headers["cache-control"] == "no-store"
    assert response.headers["location"] == "/d/sop-qc-001-v4?lines=7-9&via=workbench"
    page = client.get(response.headers["location"], follow_redirects=True)
    assert page.status_code == 200
    assert "Opened from your workbench session as Odile Fenn" in page.text
    assert parsed(page.text).highlighted == {7, 8, 9}
    replayed = TestClient(create_site(store, verifier=verifier), follow_redirects=False)
    assert replayed.get("/signin/grant", params={"token": token}).status_code == 403
    rejected = {
        "forged": grant(key=Ed25519PrivateKey.generate()),
        "expired": grant(now=time.time() - 3600),
        "audience": grant(aud="zagent-broker"),
        "widened roles": grant("analyst", roles=["qa-officer"]),
        "long lived": grant(lifetime=3600),
        "unknown site": grant(site="atlantis"),
        "malformed": "not-a-token",
    }
    for name, token in rejected.items():
        response = replayed.get("/signin/grant", params={"token": token})
        assert response.status_code == 403, name
        assert identity.SESSION_COOKIE not in response.headers.get("set-cookie", ""), name
    unconfigured = TestClient(create_site(store, verifier=identity.GrantVerifier(None)))
    assert unconfigured.get("/signin/grant", params={"token": grant()}).status_code == 403


def test_mock_sign_in_is_signed_and_stays_on_the_site(published_index):
    store, _identifier, _warnings = published_index
    draft = "/qms/documents/SOP-QC-001/v4"
    client = TestClient(create_site(store), follow_redirects=False)
    response = client.post(
        "/signin", data={"persona": "qa-officer", "site": "northgate", "next": "//evil.example/"}
    )
    assert response.status_code == 303 and response.headers["location"] == "/"
    cookie = response.cookies[identity.SESSION_COOKIE]
    assert client.get(draft).status_code == 200
    payload, signature = cookie.rsplit(".", 1)
    other = TestClient(create_site(store), follow_redirects=False)
    for value in (cookie, f"{payload}x.{signature}", f"{payload}.{'0' * len(signature)}"):
        other.cookies.set(identity.SESSION_COOKIE, value)
        assert other.get(draft).status_code == 404
    assert client.post("/signin", data={"persona": "root", "site": "northgate"}).status_code == 400
    assert client.post("/signout").status_code == 303
    client.cookies.clear()
    assert client.get(draft).status_code == 404


def test_mutation_flags_require_an_explicit_test_mode(monkeypatch):
    from zknowledge import faults

    monkeypatch.setenv("ZKNOWLEDGE_MUTATION", "site_acl_off")
    with pytest.raises(RuntimeError):
        faults.enabled("site_acl_off")
    monkeypatch.setenv("ZKNOWLEDGE_TEST_MODE", "mutation")
    assert isinstance(identity.caller(None), identity.Everyone)
    monkeypatch.setenv("ZKNOWLEDGE_MUTATION", "something_else")
    with pytest.raises(RuntimeError):
        identity.caller(None)
