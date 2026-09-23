import json
import os
import subprocess
import sys
from uuid import uuid4

from control import ROOT, run
from manifests import ZONES, labels, metadata, secret_env
from verify import kubectl


def job_manifest(name, identity, image, arguments, run_id):
    zone = "agent" if identity == "eval-runner" else "clinical"
    env = [{"name": "ZAGENT_LLM_MODE", "value": "replay"}]
    if zone == "clinical":
        env += [
            secret_env("DATABASE_URL", "owner-database", "test_url"),
            secret_env("ZAGENT_TEST_DATABASE_URL", "owner-database", "test_url"),
            secret_env("ZAGENT_APPLICATION_DATABASE_URL", "owner-database"),
        ]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": metadata(name, zone),
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 1800,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": labels(identity)},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "containers": [
                        {
                            "name": "evidence",
                            "image": image,
                            "imagePullPolicy": "Never",
                            "command": ["python", "deploy/cluster/run_checks.py", *arguments],
                            "env": env,
                            "workingDir": "/app",
                            "resources": {
                                "requests": {"cpu": "100m", "memory": "256Mi"},
                                "limits": {"memory": "2Gi"},
                            },
                            "volumeMounts": [
                                {"name": "results", "mountPath": "/evidence", "subPath": run_id}
                            ],
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                    "volumes": [
                        {"name": "results", "persistentVolumeClaim": {"claimName": "evidence"}}
                    ],
                },
            },
        },
    }


def collect(namespace, output):
    claim = json.loads(kubectl("get", "pvc", "evidence", "-n", namespace, "-o", "json"))
    volume = json.loads(kubectl("get", "pv", claim["spec"]["volumeName"], "-o", "json"))
    node = volume["spec"]["nodeAffinity"]["required"]["nodeSelectorTerms"][0]["matchExpressions"][
        0
    ]["values"][0]
    if node not in {"k3d-zagent-plan9-server-0", "k3d-zagent-plan9-agent-0"}:
        raise ValueError("Evidence volume is outside the expected local cluster")
    output.mkdir(parents=True, exist_ok=True)
    storage = volume["spec"].get("local", volume["spec"].get("hostPath"))
    if storage is None:
        raise ValueError("Evidence collection requires a local k3d volume")
    run("docker", "cp", f"{node}:{storage['path']}/.", str(output))
    if "LOCAL_UID" in os.environ:
        for path in [output.parent, output, *output.rglob("*")]:
            os.chown(path, int(os.environ["LOCAL_UID"]), int(os.environ["LOCAL_GID"]))


def main():
    state = json.loads((ROOT / ".cluster/config.json").read_text())
    if state["mode"] != "replay":
        raise SystemExit("Cluster evidence requires replay mode; use make cluster first.")
    deployed = json.loads(
        kubectl("get", "deployment", "agent-runtime", "-n", ZONES["agent"], "-o", "json")
    )
    base = deployed["spec"]["template"]["spec"]["containers"][0]["image"]
    run_id = uuid4().hex[:12]
    image = f"zagent-evidence:{run_id}"
    run(
        "docker",
        "build",
        "--quiet",
        "--build-arg",
        f"BACKEND_IMAGE={base}",
        "--file",
        "deploy/cluster/Evidence.Dockerfile",
        "--tag",
        image,
        ".",
    )
    run("k3d", "image", "import", image, "--cluster", "zagent-plan9", "--mode", "direct")
    for node in ("k3d-zagent-plan9-server-0", "k3d-zagent-plan9-agent-0"):
        subprocess.run(
            ["docker", "exec", node, "crictl", "inspecti", image],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    selected = (
        [("evidence-runner", ["workflows"])]
        if sys.argv[1:] == ["--workflow-only"]
        else [("eval-runner", ["agent"]), ("evidence-runner", sys.argv[1:])]
    )
    for identity, arguments in selected:
        zone = "agent" if identity == "eval-runner" else "clinical"
        namespace = ZONES[zone]
        name = f"{identity}-{run_id}"
        claim = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": metadata("evidence", zone),
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "2Gi"}},
            },
        }
        kubectl("apply", "-f", "-", data=json.dumps(claim))
        kubectl(
            "create",
            "-f",
            "-",
            data=json.dumps(job_manifest(name, identity, image, arguments, run_id)),
        )
        kubectl(
            "wait",
            "pods",
            "-n",
            namespace,
            "-l",
            f"batch.kubernetes.io/job-name={name}",
            "--for=create",
            "--timeout=60s",
        )
        pod = json.loads(
            kubectl(
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                f"batch.kubernetes.io/job-name={name}",
                "-o",
                "json",
            )
        )["items"][0]
        kubectl(
            "wait",
            f"pod/{pod['metadata']['name']}",
            "-n",
            namespace,
            "--for=jsonpath={.status.containerStatuses[0].state.terminated}",
            "--timeout=31m",
        )
        run("kubectl", "logs", f"pod/{pod['metadata']['name']}", "-n", namespace)
        pod = json.loads(
            kubectl("get", "pod", pod["metadata"]["name"], "-n", namespace, "-o", "json")
        )
        collect(namespace, ROOT / ".cluster/reports" / zone)
        exit_code = pod["status"]["containerStatuses"][0]["state"]["terminated"]["exitCode"]
        print(f"Evidence: .cluster/reports/{zone}/{run_id} (exit {exit_code})", flush=True)
        if exit_code:
            raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
