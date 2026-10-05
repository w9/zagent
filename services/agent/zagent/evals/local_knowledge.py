import atexit
import shutil
from functools import cache
from pathlib import Path
from tempfile import mkdtemp

from zagent.broker import KnowledgeBroker, create_broker_server
from zagent.cohort import ClinicalStore
from zagent.privacy_client import Tokenizer
from zagent.tools import McpToolClient, create_mcp_server


@cache
def published_snapshots() -> Path:
    from zknowledge.snapshot import build_snapshot, corpus_root

    directory = Path(mkdtemp(prefix="zagent-knowledge-"))
    atexit.register(shutil.rmtree, directory, True)
    build_snapshot(corpus_root() / "legacy", directory)
    return directory


def current_snapshot(snapshots: Path | None = None) -> str:
    from zknowledge.snapshot import SnapshotStore

    return SnapshotStore(snapshots or published_snapshots()).current()


def local_broker(tokenizer: Tokenizer, snapshots: Path | None = None) -> KnowledgeBroker:
    from zknowledge.server import create_server
    from zknowledge.snapshot import SnapshotStore

    upstream = create_server(SnapshotStore(snapshots or published_snapshots()))
    return KnowledgeBroker(McpToolClient(server=upstream), tokenizer)


def local_tools(clinical: ClinicalStore, *, snapshots: Path | None = None) -> McpToolClient:
    """In-process clinical tools plus the knowledge service behind a broker."""
    broker = local_broker(clinical.store.privacy, snapshots)
    return McpToolClient(
        server=create_mcp_server(clinical),
        knowledge=McpToolClient(server=create_broker_server(broker)),
    )
