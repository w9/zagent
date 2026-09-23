import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

import docker
from docker.errors import APIError, NotFound

from zagent.drafts import CATALOG
from zagent.jobs import JobLease


class Executor(Protocol):
    async def ensure(self, lease: JobLease) -> None: ...
    async def poll(self, name: str, after: int) -> tuple[list[str], int | None]: ...


def worker_environment(lease: JobLease, step_seconds: float) -> dict[str, str]:
    return {
        "ZAGENT_JOB_INPUT": json.dumps(lease.snapshot, sort_keys=True),
        "ZAGENT_JOB_ATTEMPT": str(lease.attempt),
        "ZAGENT_JOB_STEP_SECONDS": str(step_seconds),
        "PYTHONUNBUFFERED": "1",
    }


class DockerExecutor:
    def __init__(self, *, project: str = "zagent-plan4", step_seconds: float = 2):
        self.client = docker.from_env(timeout=10)
        self.project = project
        self.step_seconds = step_seconds

    async def ensure(self, lease: JobLease) -> None:
        await asyncio.to_thread(self._ensure, lease)

    def _ensure(self, lease: JobLease) -> None:
        environment = worker_environment(lease, self.step_seconds)
        fingerprint = hashlib.sha256(environment["ZAGENT_JOB_INPUT"].encode()).hexdigest()
        labels = {
            "zagent.managed": "job",
            "zagent.input": fingerprint,
            "com.docker.compose.project": self.project,
        }
        try:
            container = self.client.containers.get(lease.execution_name)
        except NotFound:
            app = CATALOG[lease.snapshot["app_id"]]
            try:
                container = self.client.containers.create(
                    app.execution_image,
                    app.execution_command,
                    name=lease.execution_name,
                    environment=environment,
                    labels=labels,
                    network_mode="none",
                    read_only=True,
                    user="65532:65532",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    mem_limit="192m",
                    nano_cpus=500_000_000,
                    pids_limit=64,
                    tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
                    log_config=docker.types.LogConfig(type="json-file", config={"max-size": "5m"}),
                )
            except APIError as error:
                if error.status_code != 409:
                    raise
                container = self.client.containers.get(lease.execution_name)
        if any(container.labels.get(key) != value for key, value in labels.items()):
            raise ValueError("Existing execution unit does not match the confirmed input")
        if container.status == "created":
            container.start()

    async def poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        return await asyncio.to_thread(self._poll, name, after)

    def _poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        container = self.client.containers.get(name)
        state = container.attrs["State"]
        lines = (
            container.logs(stdout=True, stderr=False).decode("utf-8", errors="strict").splitlines()
        )
        exit_code = state["ExitCode"] if state["Status"] in {"exited", "dead"} else None
        return lines[after:], exit_code

    def close(self) -> None:
        self.client.close()


class ProcessExecutor:
    def __init__(self, directory: Path, *, step_seconds: float = 0):
        self.directory = directory
        self.step_seconds = step_seconds
        self.processes: dict[str, subprocess.Popen] = {}
        self.lock = threading.Lock()

    async def ensure(self, lease: JobLease) -> None:
        await asyncio.to_thread(self._ensure, lease)

    def _ensure(self, lease: JobLease) -> None:
        with self.lock:
            if lease.execution_name in self.processes:
                return
            self.directory.mkdir(parents=True, exist_ok=True)
            environment = worker_environment(lease, self.step_seconds)
            environment["PATH"] = os.environ.get("PATH", "")
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
            with (self.directory / f"{lease.execution_name}.jsonl").open("wb") as output:
                self.processes[lease.execution_name] = subprocess.Popen(
                    [sys.executable, "-m", "zagent.job_worker"],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

    async def poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        return await asyncio.to_thread(self._poll, name, after)

    def _poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        content = (self.directory / f"{name}.jsonl").read_text()
        lines = content.splitlines(keepends=True)
        complete = [line.rstrip("\n") for line in lines if line.endswith("\n")]
        return complete[after:], self.processes[name].poll()

    def close(self) -> None:
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
