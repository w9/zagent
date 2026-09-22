import argparse
import asyncio
import json
import os
from uuid import UUID

import asyncpg

from zagent.events import normalize_transcript
from zagent.store import DEFAULT_DATABASE_URL, NotFound, Store


async def transcript(session_id: UUID, database_url: str) -> list[dict]:
    store = await Store.open(database_url)
    try:
        return normalize_transcript(await store.snapshot_events(session_id))
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="zagent")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("transcript", help="Print a normalized session transcript")
    command.add_argument("session_id", type=UUID)
    command.add_argument(
        "--database-url", default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(transcript(args.session_id, args.database_url))
    except (NotFound, OSError, asyncpg.PostgresError) as error:
        parser.exit(1, f"zagent: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
