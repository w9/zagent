import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from manifests import APPS, FLOWS, ZONES, labels, metadata, secret_env


def kubectl(*args, data=None, allow_failure=False):
    result = subprocess.run(["kubectl", *args], input=data, text=True, capture_output=True)
    if result.returncode and not (allow_failure and '{"checks":' in result.stdout):
        raise RuntimeError(f"kubectl {' '.join(args[:3])}: {result.stderr.strip()}")
    return result.stdout


def objects(kind, namespace):
    return json.loads(kubectl("get", kind, "-n", namespace, "-o", "json"))["items"]


def targets_for(name, dns, destinations):
    targets = [
        {"name": "dns-positive-control", "host": dns, "port": 53, "allowed": True},
        {"name": "internet", "host": "1.1.1.1", "port": 443, "allowed": name == "llm-gateway"},
    ]
    for source, target, port in FLOWS:
        if source == name:
            targets.append(
                {
                    "name": f"allow-{target}-{port}",
                    "host": destinations[target][0],
                    "port": port,
                    "allowed": True,
                }
            )
    if APPS[name] == "agent" or name == "analysis-worker":
        for target, port in (("postgres", 5432), ("privacy", 8003), ("bff", 8000)):
            if name == "analysis-worker" and target == "postgres":
                continue
            for index, address in enumerate(destinations[target]):
                targets.append(
                    {
                        "name": f"deny-{target}-{'service' if index == 0 else 'pod'}",
                        "host": address,
                        "port": port,
                        "allowed": False,
                    }
                )
    if name == "analysis-worker":
        targets.append(
            {
                "name": "deny-kubernetes-api",
                "host": "kubernetes.default",
                "port": 443,
                "allowed": False,
            }
        )
    if name == "dispatcher":
        targets.append(
            {
                "name": "allow-kubernetes-api",
                "host": "kubernetes.default",
                "port": 443,
                "allowed": True,
            }
        )
    return targets


def main():
    started = time.monotonic()
    pods = [
        pod
        for namespace in ZONES.values()
        for pod in objects("pods", namespace)
        if pod["status"]["phase"] == "Running" and not pod["metadata"].get("deletionTimestamp")
    ]
    by_name = {pod["metadata"]["labels"]["app.kubernetes.io/name"]: pod for pod in pods}
    services = [
        service for namespace in ZONES.values() for service in objects("services", namespace)
    ]
    destinations = {
        service["metadata"]["name"]: [
            service["spec"]["clusterIP"],
            by_name[service["metadata"]["name"]]["status"]["podIP"],
        ]
        for service in services
    }
    dns = json.loads(kubectl("get", "service", "kube-dns", "-n", "kube-system", "-o", "json"))[
        "spec"
    ]["clusterIP"]
    image = by_name["agent-runtime"]["spec"]["containers"][0]["image"]
    probe_code = (
        Path(__file__).resolve().parents[2] / "services/agent/zagent/cluster_probe.py"
    ).read_text()

    def verify_pod(pod):
        name = pod["metadata"]["labels"]["app.kubernetes.io/name"]
        arguments = json.dumps(targets_for(name, dns, destinations))
        namespace = pod["metadata"]["namespace"]
        if name in {
            "agent-runtime",
            "llm-gateway",
            "privacy",
            "tools-gateway",
            "jobs",
            "dispatcher",
            "bff",
            "kb",
        }:
            output = kubectl(
                "exec",
                "-n",
                namespace,
                pod["metadata"]["name"],
                "-c",
                name,
                "--",
                "python",
                "-c",
                probe_code,
                arguments,
                allow_failure=True,
            )
        else:
            container = f"policy-{uuid4().hex[:8]}"
            kubectl(
                "debug",
                "-n",
                namespace,
                pod["metadata"]["name"],
                "--quiet",
                "--attach=false",
                "--profile=general",
                f"--image={image}",
                f"--container={container}",
                "--",
                "python",
                "-c",
                probe_code,
                arguments,
            )
            kubectl(
                "wait",
                "-n",
                namespace,
                f"pod/{pod['metadata']['name']}",
                "--timeout=60s",
                f'--for=jsonpath={{.status.ephemeralContainerStatuses[?(@.name=="{container}")].state.terminated}}',
            )
            output = kubectl("logs", "-n", namespace, pod["metadata"]["name"], "-c", container)
        report = json.loads(
            next(line for line in output.splitlines() if line.startswith('{"checks":'))
        )
        return {"pod": name, **report}

    def verify_job(name):
        identifier = f"policy-{name}-{uuid4().hex[:8]}"
        zone = APPS[name]
        env = [
            {
                "name": "ZAGENT_PROBE_TARGETS",
                "value": json.dumps(targets_for(name, dns, destinations)),
            }
        ]
        if name == "eval-runner":
            env += [
                secret_env("DATABASE_URL", "runtime-database"),
                {"name": "ZAGENT_CHECK_RUNTIME_ROLE", "value": "1"},
            ]
        job = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": metadata(identifier, zone),
            "spec": {
                "backoffLimit": 0,
                "ttlSecondsAfterFinished": 300,
                "template": {
                    "metadata": {"labels": labels(name)},
                    "spec": {
                        "restartPolicy": "Never",
                        "automountServiceAccountToken": False,
                        "containers": [
                            {
                                "name": "probe",
                                "image": image,
                                "command": ["python", "-c", probe_code],
                                "env": env,
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                    },
                },
            },
        }
        kubectl("create", "-f", "-", data=json.dumps(job))
        kubectl(
            "wait",
            "-n",
            ZONES[zone],
            f"job/{identifier}",
            "--for=jsonpath={.status.conditions[0].status}=True",
            "--timeout=90s",
        )
        output = kubectl(
            "logs", "-n", ZONES[zone], f"job/{identifier}", "--pod-running-timeout=60s"
        )
        report = json.loads(
            next(line for line in output.splitlines() if line.startswith('{"checks":'))
        )
        return {"pod": name, **report}

    with ThreadPoolExecutor(max_workers=8) as pool:
        reports = list(pool.map(verify_pod, pods))
        reports += list(pool.map(verify_job, ["eval-runner", "analysis-worker"]))
    report = {
        "seconds": round(time.monotonic() - started, 2),
        "passed": all(item["passed"] for item in reports),
        "requirements": ["REQ-PHI-05", "REQ-PHI-06", "REQ-ISO-02", "REQ-META-01"],
        "pods": reports,
    }
    (Path(__file__).resolve().parents[2] / ".cluster/policy-results.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "seconds": report["seconds"],
                "pods": len(reports),
                "checks": sum(len(item["checks"]) for item in reports),
                "failures": [
                    {"pod": item["pod"], "check": check}
                    for item in reports
                    for check in item["checks"]
                    if not check["passed"]
                ],
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
