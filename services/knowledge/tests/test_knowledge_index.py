import json
import re

import pytest
from knowledge_fixtures import *  # noqa: F403
from zknowledge.checks import PublishError
from zknowledge.document import ROLES
from zknowledge.index import Caller, NotFound, build_index

ANALYST = Caller("northgate", ["analyst"])
QA = Caller("northgate", ["qa-officer"])
TOOL_RESULT_LIMIT = 8192


def size(value) -> int:
    return len(json.dumps(value).encode())


def test_corpus_spans_five_source_systems_with_ten_tables(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        counts = dict(
            index.connection.execute("SELECT source, count(*) FROM documents GROUP BY source")
        )
        tables = [row[0] for row in index.connection.execute("SELECT name FROM reference_tables")]
        terms = index.connection.execute("SELECT count(*) FROM terms").fetchone()[0]
    finally:
        index.close()
    assert counts["wikipedia"] >= 80
    assert counts["wiki"] + counts["qms"] + counts["ticketing"] >= 100
    assert len(tables) + 1 >= 10 and terms >= 30


def test_publication_is_byte_identical(published_index, tmp_path):
    store, identifier, _warnings = published_index
    from zknowledge.snapshot import corpus_root

    again, _ = build_index(corpus_root(), tmp_path)
    assert again == identifier
    assert (tmp_path / f"{again}.sqlite3").read_bytes() == (
        store.directory / f"{identifier}.sqlite3"
    ).read_bytes()


@pytest.mark.parametrize(
    "mutation, problem",
    [
        (lambda root: edit_json(root / "wiki/space.json", "updated_by_role", None), "provenance"),
        (
            lambda root: append(root / "wiki/pages/40230.xhtml", "<p>Call 615-555-0142.</p>"),
            "phone",
        ),
        (
            lambda root: replace(
                root / "reference/qc_thresholds.csv", ",40,x,tumor", ",45,x,tumor"
            ),
            "not stated",
        ),
        (
            lambda root: replace(
                root / "qms/register.json", '"status": "superseded"', '"status": "effective"', 1
            ),
            "exactly one effective",
        ),
        (
            lambda root: replace(
                root / "qms/register.json",
                '"roles": ["qa-officer", "lab-director"]',
                '"roles": ["all"]',
            ),
            "drafts must be restricted",
        ),
        (
            lambda root: replace(
                root / "reference/glossary.yaml", "CRAM is smaller than BAM", "Nope"
            ),
            "anchor",
        ),
    ],
)
def test_publishing_checks_reject_bad_corpora(corpus_copy, tmp_path, mutation, problem):
    mutation(corpus_copy)
    with pytest.raises(PublishError) as raised:
        build_index(corpus_copy, tmp_path / "snapshots")
    assert any(problem in item for item in raised.value.problems)
    assert not (tmp_path / "snapshots" / "current").exists()


def edit_json(path, key, value):
    data = json.loads(path.read_text())
    data["pages"][0][key] = value
    path.write_text(json.dumps(data))


def append(path, text):
    path.write_text(path.read_text() + text)


def replace(path, old, new, count=-1):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, count))


def test_forbidden_documents_are_indistinguishable_from_missing_ones(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        with pytest.raises(NotFound) as hidden:
            index.get_document(ANALYST, "sop-qc-001-v4")
        with pytest.raises(NotFound) as missing:
            index.get_document(ANALYST, "sop-qc-001-v9")
        assert str(hidden.value) == str(missing.value)
        with pytest.raises(NotFound):
            index.read_document(ANALYST, "wiki-40205", start_line=1)
        effective = index.get_document(ANALYST, "sop-qc-001-v3")
        assert [item["version"] for item in effective["versions"]] == ["2", "3"]
        assert [
            item["version"] for item in index.get_document(QA, "sop-qc-001-v3")["versions"]
        ] == [
            "2",
            "3",
            "4",
        ]
        analyst = index.search(ANALYST, "45x tumor minimum duplication", include_inactive=True)
        qa = index.search(QA, "45x tumor minimum duplication", include_inactive=True)
        hidden_ids = {"sop-qc-001-v4", "chg-0024", "wiki-40223"}
        assert not hidden_ids & {match["document"] for match in analyst["matches"]}
        assert hidden_ids & {match["document"] for match in qa["matches"]}
        assert analyst["counts"]["qms"] < qa["counts"]["qms"]
        harbor = Caller("harbor", ["analyst"])
        lakeside = index.search(harbor, "Lakeside courier cutoff", limit=8)
        assert not {"sop-acc-001a-v1", "wiki-40232", "inc-0151"} & {
            match["document"] for match in lakeside["matches"]
        }
        anonymous = index.search(Caller(), "readqc coverage")
        assert all(match["document"] != "inc-0142" for match in anonymous["matches"])
    finally:
        index.close()


def test_inactive_documents_are_excluded_unless_requested(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        default = index.search(ANALYST, "All libraries require a mean coverage of at least 30x")
        assert all(
            match["status"] not in {"superseded", "archived"} for match in default["matches"]
        )
        history = index.search(
            ANALYST, "All libraries require a mean coverage of at least 30x", include_inactive=True
        )
        assert {"sop-qc-001-v2", "wiki-40217"} & {match["document"] for match in history["matches"]}
    finally:
        index.close()


def test_reads_terms_and_tables_are_cited_and_bounded(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        section = index.read_document(ANALYST, "sop-qc-001-v3", section="2")
        assert section["text"].startswith("L7: ## 2. Coverage")
        assert "at least 40x" in section["text"]
        long = index.read_document(ANALYST, "wp-p53", start_line=2, end_line=140)
        assert long["truncated"] and long["end_line"] - long["start_line"] < 30
        with pytest.raises(ValueError, match="either a section or a start_line"):
            index.read_document(ANALYST, "sop-qc-001-v3")
        term = index.lookup_term(ANALYST, "T/N swap")
        assert term["term"] == "Sample swap" and term["source"]["document"] == "wiki-40137"
        with pytest.raises(NotFound, match="similar terms"):
            index.lookup_term(ANALYST, "swap")
        rows = index.query_reference(
            ANALYST,
            "qc_thresholds",
            {"app_id": "readqc", "specimen": "tumor", "status": "effective"},
        )
        assert [row["threshold"] for row in rows["rows"]] == [40]
        assert rows["rows"][0]["_source"] == {"document": "sop-qc-001-v3", "line": 10}
        assert index.read_document(ANALYST, "sop-qc-001-v3", start_line=10)["text"].startswith(
            "L10: Tumor libraries intended for somatic calling require a mean coverage of at least"
        )
        with pytest.raises(NotFound, match="available: assay_contacts"):
            index.query_reference(ANALYST, "thresholds")
        with pytest.raises(ValueError, match="Unknown filter columns: site; columns: app_id"):
            index.query_reference(ANALYST, "qc_thresholds", {"site": "northgate"})
    finally:
        index.close()


def test_every_tool_result_fits_the_gateway_limit(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        documents = list(index.connection.execute("SELECT id, sites FROM documents"))
        for document, sites in documents:
            site = next((name for name in json.loads(sites) if name != "all"), "northgate")
            caller = Caller(site, list(ROLES))
            assert size(index.get_document(caller, document)) < TOOL_RESULT_LIMIT, document
            for (path,) in index.connection.execute(
                "SELECT path FROM sections WHERE document=?", (document,)
            ):
                result = index.read_document(caller, document, section=path)
                assert size(result) < TOOL_RESULT_LIMIT
        for (table,) in index.connection.execute("SELECT name FROM reference_tables"):
            assert size(index.query_reference(QA, table, limit=25)) < TOOL_RESULT_LIMIT, table
        for query in (
            "coverage",
            "tumor normal swap fusion VAF purity eviction",
            "what is a biobank",
        ):
            assert size(index.search(QA, query, limit=8, include_inactive=True)) < TOOL_RESULT_LIMIT
    finally:
        index.close()


def test_planted_identifiers_exist_only_where_the_corpus_documents_them(published_index):
    store, _identifier, _warnings = published_index
    index = store.open()
    try:
        mrn = re.compile(r"NGC-\d{7}|LHX/\d{2}/\d{5}")
        found = {
            row[0]
            for row in index.connection.execute("SELECT document, text FROM lines")
            if mrn.search(row[1])
        }
    finally:
        index.close()
    assert found == {"inc-0142", "inc-0151"}
