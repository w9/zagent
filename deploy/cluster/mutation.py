import json
import runpy
from pathlib import Path
from uuid import uuid4

from manifests import ZONES, labels, policies
from verify import kubectl


def isolated_resources(identity, image):
    namespaces = {
        namespace: f"zagent-mutation-{identity[:12]}-{zone}" for zone, namespace in ZONES.items()
    }

    def relocate(value):
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        if isinstance(value, list):
            return [relocate(item) for item in value]
        return namespaces.get(value, value) if isinstance(value, str) else value

    items = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": name,
                "labels": {"zagent.io/mutation": identity},
            },
        }
        for name in namespaces.values()
    ]
    for policy in relocate(policies()):
        policy["metadata"]["labels"]["zagent.io/mutation"] = identity
        items.append(policy)
    for name, zone, port in (
        ("postgres", "clinical", 5432),
        ("event-db", "neutral", 5432),
        ("agent-runtime", "agent", 8000),
    ):
        postgres = name == "postgres"
        namespace = namespaces[ZONES[zone]]
        container = {
            "name": "fixture",
            "image": "postgres:16-alpine" if postgres else image,
            "command": ["docker-entrypoint.sh", "postgres"]
            if postgres
            else ["python", "-m", "http.server", str(port)],
            "env": [{"name": "POSTGRES_PASSWORD", "value": "isolated-synthetic-fixture"}]
            if postgres
            else [],
            "readinessProbe": {"tcpSocket": {"port": port}, "periodSeconds": 1},
            "resources": {
                "requests": {"cpu": "20m", "memory": "32Mi"},
                "limits": {"memory": "256Mi"},
            },
        }
        items.append(
            {
                "apiVersion": "v1",
                "kind": "Pod",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": {**labels(name), "zagent.io/mutation": identity},
                },
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "containers": [container],
                },
            }
        )
        items.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": {"zagent.io/mutation": identity},
                },
                "spec": {"selector": labels(name), "ports": [{"port": port}]},
            }
        )
    return namespaces, items


def assert_owned(namespace, identity):
    if not namespace.startswith(f"zagent-mutation-{identity[:12]}-"):
        raise ValueError("Refusing to mutate a non-test namespace")
    value = json.loads(kubectl("get", "namespace", namespace, "-o", "json"))
    if value["metadata"].get("labels", {}).get("zagent.io/mutation") != identity:
        raise ValueError("Mutation namespace ownership does not match this run")


def exercise(namespaces, identity):
    clinical = namespaces[ZONES["clinical"]]
    agent = namespaces[ZONES["agent"]]
    neutral = namespaces[ZONES["neutral"]]
    pod_ip = json.loads(kubectl("get", "pod", "postgres", "-n", clinical, "-o", "json"))["status"][
        "podIP"
    ]
    code = """import json,socket,sys
def connected(host,port):
    try:
        with socket.create_connection((host,port),2): return True
    except OSError: return False
print(json.dumps({host:connected(host,int(port)) for host,port in json.loads(sys.argv[1])}))
"""

    def connection_probe(source, namespace, targets):
        return json.loads(
            kubectl(
                "exec", "-n", namespace, source, "--", "python", "-c", code, json.dumps(targets)
            )
        )

    def evidence():
        source = connection_probe(
            "agent-runtime",
            agent,
            [
                [f"event-db.{neutral}", 5432],
                ["kube-dns.kube-system", 53],
                [f"postgres.{clinical}", 5432],
                [pod_ip, 5432],
            ],
        )
        positive = connection_probe("event-db", neutral, [[f"postgres.{clinical}", 5432]])
        healthy = (
            source[f"event-db.{neutral}"]
            and source["kube-dns.kube-system"]
            and all(positive.values())
        )
        return {
            "healthy": healthy,
            "controls": {
                "agent_event_route": source[f"event-db.{neutral}"],
                "dns": source["kube-dns.kube-system"],
                "neutral_database_route": all(positive.values()),
            },
            "requirements": {
                "REQ-PHI-05": not source[f"postgres.{clinical}"] and not source[pod_ip]
            },
            "observed": {
                "clinical_service_connected": source[f"postgres.{clinical}"],
                "clinical_pod_connected": source[pod_ip],
            },
        }

    control = evidence()
    if not control["healthy"] or not control["requirements"]["REQ-PHI-05"]:
        return control, {"healthy": False, "requirements": {}, "error": "baseline_policy_failed"}
    for namespace in namespaces.values():
        assert_owned(namespace, identity)
        kubectl(
            "delete",
            "networkpolicy",
            "-n",
            namespace,
            "-l",
            f"zagent.io/mutation={identity}",
            "--wait=true",
        )
    return control, evidence()


def main():
    root = Path(__file__).resolve().parents[2]
    guard = runpy.run_path(str(root / "services/agent/zagent/faults.py"))
    if guard["configured"]() != "netpol_off":
        raise ValueError("The network experiment requires the guarded netpol_off flag")
    if kubectl("config", "current-context").strip() != "k3d-zagent-plan9":
        raise ValueError("Network mutation only targets the named local test cluster")
    deployment = json.loads(
        kubectl("get", "deployment", "agent-runtime", "-n", ZONES["agent"], "-o", "json")
    )
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    identity = uuid4().hex
    namespaces, objects = isolated_resources(identity, image)
    try:
        kubectl(
            "apply",
            "-f",
            "-",
            data=json.dumps({"apiVersion": "v1", "kind": "List", "items": objects}),
        )
        for namespace in namespaces.values():
            kubectl(
                "wait", "pods", "--all", "-n", namespace, "--for=condition=Ready", "--timeout=90s"
            )
        control, mutant = exercise(namespaces, identity)
        print(json.dumps({"control": control, "mutant": mutant, "run_id": identity}), flush=True)
    finally:
        for namespace in namespaces.values():
            existing = kubectl("get", "namespace", namespace, "--ignore-not-found", "-o", "name")
            if existing.strip():
                assert_owned(namespace, identity)
                kubectl("delete", "namespace", namespace, "--wait=false")


if __name__ == "__main__":
    main()
