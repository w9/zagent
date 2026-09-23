import asyncio
import logging
import os
from uuid import UUID, uuid4

from opentelemetry import trace
from opentelemetry.propagate import extract

from zagent.cohort import ClinicalStore, configured_clock
from zagent.executors import DockerExecutor, Executor
from zagent.job_worker import JobRecord
from zagent.jobs import JobLease, JobStore, LeaseLost
from zagent.store import DEFAULT_DATABASE_URL, Store
from zagent.telemetry import configure_telemetry

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(
        self, jobs: JobStore, executor: Executor, *, interval: float = 0.5, concurrency: int = 4
    ):
        self.jobs, self.executor = jobs, executor
        self.interval, self.concurrency = interval, concurrency
        self.owner = uuid4()
        self.tracer = trace.get_tracer("zagent.dispatcher")

    async def execute(self, lease: JobLease) -> None:
        with self.tracer.start_as_current_span(
            "job.execute",
            context=extract(lease.snapshot.get("trace_context", {})),
            attributes={"session.id": str(lease.session_id), "job.id": lease.job_id},
            record_exception=False,
            set_status_on_exception=False,
        ):
            await self._execute(lease)

    async def _execute(self, lease: JobLease) -> None:
        if lease.terminal_exit_code is not None:
            await self._complete(lease, lease.terminal_exit_code)
            return
        await self.executor.ensure(lease)
        cursor = 0
        while True:
            await self.jobs.renew(lease)
            lines, exit_code = await self.executor.poll(lease.execution_name, cursor)
            for line in lines:
                if len(line) > 16384:
                    raise ValueError("Execution log line exceeds the ingestion limit")
                record = await self.jobs.ingest(
                    lease,
                    JobRecord.model_validate_json(line),
                    platform_retries=bool(getattr(self.executor, "platform_retries", False)),
                )
                cursor += 1
                if record is not None:
                    with self.tracer.start_as_current_span(
                        "job.log", attributes=record.attributes
                    ) as span:
                        span.add_event(record.body)
            if exit_code is not None:
                await self._complete(lease, exit_code)
                return
            await asyncio.sleep(self.interval)

    async def _complete(self, lease: JobLease, exit_code: int) -> None:
        if hasattr(self.executor, "finalize"):
            await self.jobs.record_terminal(lease, exit_code)
            await self.executor.finalize(lease)
        await self.jobs.finish(
            lease,
            exit_code,
            platform_retries=bool(getattr(self.executor, "platform_retries", False)),
        )

    async def once(self, session_id: UUID | None = None) -> bool:
        lease = await self.jobs.claim(self.owner, session_id=session_id)
        if lease is None:
            return False
        try:
            await self.execute(lease)
        except LeaseLost:
            logger.info("Execution lease was taken over")
        return True

    async def run(self) -> None:
        active: set[asyncio.Task] = set()
        try:
            while True:
                while len(active) < self.concurrency:
                    lease = await self.jobs.claim(self.owner)
                    if lease is None:
                        break
                    active.add(asyncio.create_task(self.execute(lease)))
                if not active:
                    await asyncio.sleep(self.interval)
                    continue
                done, active = await asyncio.wait(
                    active, timeout=self.interval, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    try:
                        task.result()
                    except Exception as error:
                        logger.warning("Execution monitor interrupted: %s", type(error).__name__)
        finally:
            for task in active:
                task.cancel()
            await asyncio.gather(*active, return_exceptions=True)


async def serve() -> None:
    store = await Store.open(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
    if os.environ.get("ZAGENT_EXECUTOR") == "kubernetes":
        from zagent.kubernetes_executor import KubernetesExecutor

        executor = KubernetesExecutor(
            namespace=os.environ.get("ZAGENT_JOB_NAMESPACE", "zagent-clinical"),
            image=os.environ.get("ZAGENT_JOB_IMAGE", "zagent-backend:plan9"),
            step_seconds=float(os.environ.get("ZAGENT_JOB_STEP_SECONDS", "2")),
        )
    else:
        executor = DockerExecutor(
            project=os.environ.get("COMPOSE_PROJECT_NAME", "zagent-plan4"),
            step_seconds=float(os.environ.get("ZAGENT_JOB_STEP_SECONDS", "2")),
        )
    try:
        await Dispatcher(JobStore(ClinicalStore(store, configured_clock())), executor).run()
    finally:
        executor.close()
        await store.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    configure_telemetry("zagent-dispatcher")
    try:
        asyncio.run(serve())
    finally:
        shutdown = getattr(trace.get_tracer_provider(), "shutdown", None)
        if shutdown:
            shutdown()


if __name__ == "__main__":
    main()
