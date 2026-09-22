import asyncio
import json
import sys
from uuid import uuid4

import pytest
from zagent.events import normalize_transcript

pytestmark = pytest.mark.integration


async def invoke(session_id, database_url):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "zagent.cli",
        "transcript",
        str(session_id),
        "--database-url",
        database_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode(), stderr.decode()


async def test_cli_prints_the_normalized_log(store, database_url):
    session = await store.create_session()
    turn = await store.begin_conversation_turn(session.id, "Hello")
    await store.finish_conversation_turn(session.id, turn.conversation_turn_id)
    code, stdout, stderr = await invoke(session.id, database_url)
    assert code == 0
    assert stderr == ""
    assert json.loads(stdout) == normalize_transcript(await store.snapshot_events(session.id))


async def test_cli_reports_a_missing_session(database_url):
    code, stdout, stderr = await invoke(uuid4(), database_url)
    assert code == 1
    assert stdout == ""
    assert stderr == "zagent: Session not found\n"
