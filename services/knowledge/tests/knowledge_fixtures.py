import shutil

import pytest
from zknowledge.index import IndexStore, build_index
from zknowledge.snapshot import corpus_root


@pytest.fixture(scope="session")
def published_index(tmp_path_factory):
    directory = tmp_path_factory.mktemp("knowledge-index")
    identifier, warnings = build_index(corpus_root(), directory)
    return IndexStore(directory), identifier, warnings


@pytest.fixture
def corpus_copy(tmp_path):
    target = tmp_path / "corpus"
    shutil.copytree(corpus_root(), target)
    return target
