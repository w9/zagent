import yaml
from knowledge_fixtures import *  # noqa: F403
from zknowledge.evaluate import EVALS, evaluate, wilson_lower


def test_retrieval_meets_its_gate_without_label_errors_or_access_leaks(published_index):
    store, _identifier, _warnings = published_index
    spec = yaml.safe_load(EVALS.read_text())
    index = store.open()
    try:
        report = evaluate(index, spec)
    finally:
        index.close()
    assert report["gold_errors"] == []
    assert report["access_violations"] == []
    assert report["queries"] >= 150
    assert set(report["by_source"]) == {"qms", "wiki", "ticketing", "reference", "wikipedia"}
    assert report["recall_lower_bound"] >= spec["gate"]["min_recall_lower_bound"], report["misses"]


def test_wilson_lower_bound():
    assert wilson_lower(0, 0) == 0.0
    assert round(wilson_lower(150, 160), 3) == 0.889
