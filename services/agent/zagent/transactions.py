from contextlib import asynccontextmanager
from contextvars import ContextVar


class AtomicPool:
    def __init__(self, pool):
        self.pool = pool
        self.current = ContextVar("tool_transaction", default=None)

    @asynccontextmanager
    async def acquire(self, **options):
        connection = self.current.get()
        if connection is not None:
            yield connection
        else:
            async with self.pool.acquire(**options) as connection:
                yield connection

    @asynccontextmanager
    async def atomic(self):
        if self.current.get() is not None:
            yield self.current.get()
            return
        async with self.pool.acquire() as connection, connection.transaction():
            token = self.current.set(connection)
            try:
                yield connection
            finally:
                self.current.reset(token)

    def __getattr__(self, name):
        if name not in {"execute", "executemany", "fetch", "fetchrow", "fetchval"}:
            return getattr(self.pool, name)

        async def invoke(*arguments, **options):
            async with self.acquire() as connection:
                return await getattr(connection, name)(*arguments, **options)

        return invoke
