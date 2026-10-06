import atexit
import shutil
from functools import cache
from pathlib import Path
from tempfile import mkdtemp

from zagent.broker import KnowledgeBroker, create_broker_server
from zagent.cohort import ClinicalStore
from zagent.privacy_client import Tokenizer
from zagent.tools import McpToolClient, create_mcp_server

UNREACHABLE = "http://127.0.0.1:9/mcp"


@cache
def published_snapshots() -> Path:
    from zknowledge.index import build_index
    from zknowledge.snapshot import corpus_root

    directory = Path(mkdtemp(prefix="zagent-knowledge-"))
    atexit.register(shutil.rmtree, directory, True)
    build_index(corpus_root(), directory)
    return directory


def current_snapshot(snapshots: Path | None = None) -> str:
    return ((snapshots or published_snapshots()) / "current").read_text().strip()


def local_broker(
    tokenizer: Tokenizer, snapshots: Path | None = None, *, available: bool = True
) -> KnowledgeBroker:
    from zknowledge.index import IndexStore
    from zknowledge.server import create_server

    upstream = (
        McpToolClient(server=create_server(IndexStore(snapshots or published_snapshots())))
        if available
        else McpToolClient(url=UNREACHABLE)
    )
    return KnowledgeBroker(upstream, tokenizer)


def local_tools(
    clinical: ClinicalStore, *, snapshots: Path | None = None, knowledge: bool = True
) -> McpToolClient:
    """In-process clinical tools plus the knowledge service behind a broker."""
    broker = local_broker(clinical.store.privacy, snapshots, available=knowledge)
    return McpToolClient(
        server=create_mcp_server(clinical),
        knowledge=McpToolClient(server=create_broker_server(broker)),
    )
