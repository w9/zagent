import asyncio
import hashlib
import json
import time

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from pydantic import ValidationError

from zagent.drafts import CATALOG
from zagent.job_worker import JobRecord
from zagent.jobs import JobLease


def execution_name(lease: JobLease) -> str:
    return f"zagent-{lease.session_id.hex}-{lease.job_id}"


def job_manifest(lease: JobLease, *, image: str, step_seconds: float = 2) -> dict:
    app = CATALOG[lease.snapshot["app_id"]]
    fingerprint = hashlib.sha256(json.dumps(lease.snapshot, sort_keys=True).encode()).hexdigest()
    labels = {"app.kubernetes.io/name": "analysis-worker", "zagent.io/job": execution_name(lease)}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": execution_name(lease),
            "labels": labels,
            "annotations": {"zagent.io/input-sha256": fingerprint},
        },
        "spec": {
            "backoffLimit": 1,
            "activeDeadlineSeconds": 300,
            "podFailurePolicy": {
                "rules": [
                    {
                        "action": "FailJob",
                        "onExitCodes": {"containerName": "worker", "operator": "In", "values": [2]},
                    },
                ]
            },
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 65532,
                        "runAsGroup": 65532,
                        "fsGroup": 65532,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "worker",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "command": app.execution_command,
                            "env": [
                                {"name": "ZAGENT_JOB_INPUT", "value": json.dumps(lease.snapshot)},
                                {"name": "ZAGENT_JOB_STEP_SECONDS", "value": str(step_seconds)},
                                {
                                    "name": "ZAGENT_JOB_POD_UID",
                                    "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}},
                                },
                                {
                                    "name": "ZAGENT_JOB_DATABASE_URL",
                                    "valueFrom": {
                                        "secretKeyRef": {"name": "worker-database", "key": "url"}
                                    },
                                },
                            ],
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "resources": {
                                "requests": {"cpu": "25m", "memory": "64Mi"},
                                "limits": {"cpu": "500m", "memory": "192Mi"},
                            },
                            "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
                        }
                    ],
                    "volumes": [
                        {"name": "tmp", "emptyDir": {"medium": "Memory", "sizeLimit": "16Mi"}}
                    ],
                },
            },
        },
    }


class KubernetesExecutor:
    platform_retries = True

    def __init__(
        self,
        *,
        namespace="zagent-clinical",
        image="zagent-backend:plan9",
        step_seconds=2,
        batch=None,
        core=None,
    ):
        if batch is None:
            config.load_incluster_config()
        self.api = client.ApiClient() if batch is None else None
        self.batch = batch or client.BatchV1Api(self.api)
        self.core = core or client.CoreV1Api(self.api)
        self.namespace, self.image, self.step_seconds = namespace, image, step_seconds
        self.names: dict[str, str] = {}

    async def ensure(self, lease: JobLease) -> None:
        await asyncio.to_thread(self._ensure, lease)

    def _ensure(self, lease: JobLease) -> None:
        manifest = job_manifest(lease, image=self.image, step_seconds=self.step_seconds)
        name = execution_name(lease)
        self.names[lease.execution_name] = name
        try:
            current = self.batch.read_namespaced_job(name, self.namespace, _request_timeout=(3, 10))
        except ApiException as error:
            if error.status != 404:
                raise
            try:
                current = self.batch.create_namespaced_job(
                    self.namespace, manifest, _request_timeout=(3, 10)
                )
            except ApiException as conflict:
                if conflict.status != 409:
                    raise
                current = self.batch.read_namespaced_job(
                    name, self.namespace, _request_timeout=(3, 10)
                )
        if (current.metadata.annotations or {}).get("zagent.io/input-sha256") != manifest[
            "metadata"
        ]["annotations"]["zagent.io/input-sha256"]:
            raise ValueError("Kubernetes Job does not match the confirmed execution input")

    async def poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        return await asyncio.to_thread(self._poll, self.names[name], after)

    def _poll(self, name: str, after: int) -> tuple[list[str], int | None]:
        job = self.batch.read_namespaced_job(name, self.namespace, _request_timeout=(3, 10))
        terminal = next(
            (
                item.type
                for item in job.status.conditions or []
                if item.status == "True" and item.type in {"Complete", "Failed"}
            ),
            None,
        )
        pods = self.core.list_namespaced_pod(
            self.namespace, label_selector=f"zagent.io/job={name}", _request_timeout=(3, 10)
        ).items
        lines = []
        for ordinal, pod in enumerate(
            sorted(pods, key=lambda pod: (pod.metadata.creation_timestamp, pod.metadata.name)), 1
        ):
            try:
                output = self.core.read_namespaced_pod_log(
                    pod.metadata.name, self.namespace, container="worker", _request_timeout=(3, 10)
                )
            except ApiException as error:
                if error.status not in {400, 404}:
                    raise
                output = ""
            records = []
            for line in output.splitlines(keepends=True):
                if not line.endswith("\n"):
                    continue
                try:
                    record = JobRecord.model_validate_json(line)
                except ValidationError:
                    continue
                record.attributes["job.attempt"] = ordinal
                if record.sequence == len(records) + 1:
                    records.append(record)
            status = next(iter(pod.status.container_statuses or []), None)
            terminated = status.state.terminated if status and status.state else None
            if (terminated or pod.status.phase == "Failed") and (
                not records or records[-1].attributes.get("job.state") == "running"
            ):
                identity = hashlib.sha256(f"{name}:{ordinal}".encode()).hexdigest()
                last = records[-1] if records else None
                record = JobRecord(
                    sequence=last.sequence + 1 if last else 1,
                    timeUnixNano=str(time.time_ns()),
                    severityNumber=17,
                    severityText="ERROR",
                    body="Execution pod terminated before its final log record.",
                    traceId=identity[:32],
                    spanId=identity[32:48],
                    attributes={
                        "job.id": name,
                        "job.attempt": ordinal,
                        "job.state": "retrying"
                        if ordinal < 2 and terminal != "Failed"
                        else "failed",
                        "job.progress": last.attributes.get("job.progress", 0) if last else 0,
                        "job.code": "pod_terminated",
                    },
                )
                records.append(record)
            lines.extend(record.model_dump_json() for record in records)
        return lines[after:], 0 if terminal == "Complete" else 2 if terminal == "Failed" else None

    async def finalize(self, lease: JobLease) -> None:
        try:
            await asyncio.to_thread(
                self.batch.patch_namespaced_job,
                execution_name(lease),
                self.namespace,
                {"spec": {"ttlSecondsAfterFinished": 3600}},
                _request_timeout=(3, 10),
            )
        except ApiException as error:
            if error.status != 404:
                raise

    def close(self) -> None:
        if self.api:
            self.api.close()
