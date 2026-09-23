import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from zagent.store import Store


async def main() -> None:
    database = os.environ["DATABASE_URL"]
    async with asyncio.timeout(60):
        while True:
            try:
                store = await Store.open(database)
                break
            except (OSError, asyncpg.CannotConnectNowError):
                await asyncio.sleep(1)
    try:
        await store.migrate()
        for role, variable in (
            ("zagent_runtime", "RUNTIME_PASSWORD"),
            ("zagent_worker", "WORKER_PASSWORD"),
        ):
            statement = await store.pool.fetchval(
                "SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)",
                role,
                os.environ[variable],
            )
            await store.pool.execute(statement)
    finally:
        await store.close()
    connection = await asyncpg.connect(database)
    try:
        if not await connection.fetchval("SELECT 1 FROM pg_database WHERE datname='zagent_test'"):
            await connection.execute("CREATE DATABASE zagent_test OWNER zagent")
    finally:
        await connection.close()
    location = urlsplit(database)
    test = await Store.open(urlunsplit(location._replace(path="/zagent_test")))
    try:
        await test.migrate(seed=False)
    finally:
        await test.close()
    print("Cluster schema and scoped database roles are ready.")


if __name__ == "__main__":
    asyncio.run(main())
