import asyncio
import os
from functools import partial


async def forward_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, host: str, port: int
) -> None:
    remote_writer = None
    transfers = []

    async def copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        while chunk := await source.read(65536):
            destination.write(chunk)
            await destination.drain()
        if destination.can_write_eof():
            destination.write_eof()

    try:
        async with asyncio.timeout(10):
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        transfers = [
            asyncio.create_task(copy(reader, remote_writer)),
            asyncio.create_task(copy(remote_reader, writer)),
        ]
        await asyncio.gather(*transfers)
    except (OSError, TimeoutError):
        pass
    finally:
        for transfer in transfers:
            transfer.cancel()
        await asyncio.gather(*transfers, return_exceptions=True)
        writers = [writer] + ([remote_writer] if remote_writer is not None else [])
        for destination in writers:
            destination.close()
        await asyncio.gather(
            *(destination.wait_closed() for destination in writers), return_exceptions=True
        )


def parse_routes(value: str) -> dict[int, tuple[str, int]]:
    routes = {}
    for entry in value.split(","):
        listen, target = entry.strip().split("=")
        host, port = target.rsplit(":", 1)
        routes[int(listen)] = (host, int(port))
    return routes


async def serve(routes: dict[int, tuple[str, int]]) -> None:
    servers = [
        await asyncio.start_server(
            partial(forward_connection, host=host, port=port), "0.0.0.0", listen
        )
        for listen, (host, port) in routes.items()
    ]
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    asyncio.run(serve(parse_routes(os.environ["ZAGENT_RELAY_ROUTES"])))
