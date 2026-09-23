import asyncio
import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit

import asyncpg


def probe(target):
    try:
        with socket.create_connection((target["host"], target["port"]), timeout=2):
            connected = True
    except OSError:
        connected = False
    return {
        "name": target["name"],
        "expected": target["allowed"],
        "connected": connected,
        "passed": connected == target["allowed"],
    }


async def role_checks(database):
    connection = await asyncpg.connect(database, timeout=5)
    checks = []
    try:
        role = await connection.fetchval("SELECT current_user")
        checks.append({"name": "runtime-role", "passed": role == "zagent_runtime"})
        await connection.fetchval("SELECT count(*) FROM events")
        checks.append({"name": "event-read-positive-control", "passed": True})
        for table in ("patients", "specimens", "libraries", "jobs", "privacy.job_inputs"):
            try:
                await connection.fetch(f"SELECT * FROM {table} LIMIT 0")
            except asyncpg.InsufficientPrivilegeError:
                denied = True
            else:
                denied = False
            checks.append({"name": f"role-denies-{table}", "passed": denied})
        try:
            await connection.execute("SET ROLE zagent")
        except asyncpg.InsufficientPrivilegeError:
            denied = True
        else:
            denied = False
        checks.append({"name": "role-escalation-denied", "passed": denied})
    finally:
        await connection.close()
    location = urlsplit(database)
    wrong_user = urlunsplit(
        location._replace(netloc=f"zagent:{location.password}@{location.hostname}:{location.port}")
    )
    try:
        connection = await asyncpg.connect(wrong_user, timeout=5)
    except asyncpg.InvalidAuthorizationSpecificationError:
        denied = True
    except asyncpg.ProtocolViolationError as error:
        if str(error) != "SASL authentication failed":
            raise
        denied = True
    else:
        await connection.close()
        denied = False
    checks.append({"name": "proxy-rejects-owner-login", "passed": denied})
    return checks


def main():
    targets = json.loads(sys.argv[1] if len(sys.argv) > 1 else os.environ["ZAGENT_PROBE_TARGETS"])
    with ThreadPoolExecutor(max_workers=16) as pool:
        checks = list(pool.map(probe, targets))
    if os.environ.get("ZAGENT_CHECK_RUNTIME_ROLE") == "1":
        try:
            checks.extend(asyncio.run(role_checks(os.environ["DATABASE_URL"])))
        except (OSError, asyncpg.PostgresError, TimeoutError) as error:
            checks.append(
                {"name": "runtime-role-connection", "passed": False, "error": type(error).__name__}
            )
    print(
        json.dumps({"checks": checks, "passed": all(check["passed"] for check in checks)}),
        flush=True,
    )
    raise SystemExit(0 if all(check["passed"] for check in checks) else 1)


if __name__ == "__main__":
    main()
