import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from manifests import ZONES
from network import install, migrate_flannel

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".cluster"
CLUSTER = "zagent-plan9"


def run(*arguments, capture=False, data=None):
    return subprocess.run(
        arguments, check=True, text=True, input=data, stdout=subprocess.PIPE if capture else None
    ).stdout


def apply(items):
    run(
        "kubectl",
        "apply",
        "-f",
        "-",
        data=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}),
    )


def save(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(value)
    if "LOCAL_UID" in os.environ:
        os.chown(path, int(os.environ["LOCAL_UID"]), int(os.environ["LOCAL_GID"]))


def secret(name, zone, values):
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": name, "namespace": ZONES[zone]},
        "data": {
            key: base64.b64encode(value if isinstance(value, bytes) else value.encode()).decode()
            for key, value in values.items()
        },
    }


def bootstrap():
    STATE.mkdir(exist_ok=True, mode=0o700)
    clusters = json.loads(run("k3d", "cluster", "list", "-o", "json", capture=True))
    existing = next((cluster for cluster in clusters if cluster["name"] == CLUSTER), None)
    if existing is not None and not (STATE / "credentials.json").exists():
        raise SystemExit(
            "Existing cluster credentials are missing. Restore .cluster/credentials.json "
            "from its backup before starting; no Secrets or volumes were changed."
        )
    if existing is None:
        run(
            "k3d",
            "cluster",
            "create",
            CLUSTER,
            "--image",
            "rancher/k3s:v1.32.5-k3s1",
            "--servers",
            "1",
            "--agents",
            "1",
            "--api-port",
            "127.0.0.1:6550",
            "--k3s-arg",
            "--disable=traefik@server:*",
            "--k3s-arg",
            "--disable=servicelb@server:*",
            "--k3s-arg",
            "--flannel-backend=none@server:*",
            "--k3s-arg",
            "--disable-network-policy@server:*",
            "--kubeconfig-update-default=false",
            "--kubeconfig-switch-context=false",
            "--wait",
        )
    elif existing["serversRunning"] == 0:
        run("k3d", "cluster", "start", CLUSTER)
    save(STATE / "kubeconfig", run("k3d", "kubeconfig", "get", CLUSTER, capture=True))
    nodes = json.loads(run("kubectl", "get", "nodes", "-o", "json", capture=True))["items"]
    migration = any(
        "flannel.alpha.coreos.com/backend-type" in node["metadata"].get("annotations", {})
        for node in nodes
    )
    if migration and not (STATE / "calico-installed").exists():
        migrate_flannel(run, save, STATE, CLUSTER)
    install(run, STATE)
    if migration and not (STATE / "calico-installed").exists():
        for namespace in [*ZONES.values(), "kube-system"]:
            run(
                "kubectl",
                "delete",
                "pods",
                "-n",
                namespace,
                "--field-selector=spec.hostNetwork=false",
                "--wait=false",
            )
    save(STATE / "calico-installed", "v3.29.3\n")
    nodes = json.loads(run("kubectl", "get", "nodes", "-o", "json", capture=True))["items"]
    server = next(
        node
        for node in nodes
        if "node-role.kubernetes.io/control-plane" in node["metadata"]["labels"]
    )
    api_ip = next(
        entry["address"] for entry in server["status"]["addresses"] if entry["type"] == "InternalIP"
    )
    mode = os.environ.get("ZAGENT_CLUSTER_MODE", "replay")
    save(
        STATE / "config.json", json.dumps({"api_ip": api_ip, "mode": mode, "cni": "calico-v3.29.3"})
    )
    path = STATE / "credentials.json"
    if not path.exists():
        save(
            path,
            json.dumps(
                {
                    "master": secrets.token_hex(32),
                    **{key: secrets.token_urlsafe(32) for key in ("owner", "runtime", "worker")},
                }
            ),
        )
    credentials = json.loads(path.read_text())
    master = bytes.fromhex(credentials["master"])
    apply(
        [
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}
            for namespace in ZONES.values()
        ]
    )
    host = "postgres.zagent-clinical.svc.cluster.local."
    owner_url = f"postgresql://zagent:{credentials['owner']}@{host}:5432/zagent"
    runtime_url = (
        f"postgresql://zagent_runtime:{credentials['runtime']}@event-db.zagent-neutral:5432/zagent"
    )
    items = [
        secret(
            "owner-database",
            "clinical",
            {"url": owner_url, "password": credentials["owner"], "test_url": owner_url + "_test"},
        ),
        secret("runtime-database", "agent", {"url": runtime_url}),
        secret(
            "worker-database",
            "clinical",
            {"url": f"postgresql://zagent_worker:{credentials['worker']}@{host}:5432/zagent"},
        ),
        secret(
            "database-passwords",
            "clinical",
            {"runtime": credentials["runtime"], "worker": credentials["worker"]},
        ),
        secret("privacy-master", "clinical", {"master.key": master}),
    ]
    for role in ("tokenize", "gateway", "display", "tools"):
        value = hmac.new(master, f"privacy:{role}".encode(), hashlib.sha256).hexdigest()
        items.append(
            secret(
                f"privacy-{role}",
                "agent" if role in {"tokenize", "gateway"} else "clinical",
                {f"{role}.key": value},
            )
        )
    ini = f"""[databases]
zagent = host={host} port=5432 dbname=zagent user=zagent_runtime password={credentials["runtime"]}
[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = scram-sha-256
auth_file = /etc/event-db/users.txt
pool_mode = session
max_client_conn = 100
default_pool_size = 40
ignore_startup_parameters = extra_float_digits
log_connections = 0
log_disconnections = 0
"""
    items.append(
        secret(
            "event-db",
            "neutral",
            {"pgbouncer.ini": ini, "users.txt": f'"zagent_runtime" "{credentials["runtime"]}"\n'},
        )
    )
    if mode == "live":
        key_file = os.environ.get("CLUSTER_PROVIDER_KEY_FILE")
        if not key_file:
            raise SystemExit("Live cluster mode requires an external provider-key file.")
        items.append(secret("provider-key", "agent", {"key": Path(key_file).read_text().strip()}))
    apply(items)
    print("Cluster credentials installed without displaying their contents.")


if __name__ == "__main__":
    if sys.argv[1:] == ["bootstrap"]:
        bootstrap()
    else:
        raise SystemExit("Usage: control.py bootstrap")
