import json
import os
from pathlib import Path

ZONES = {zone: f"zagent-{zone}" for zone in ("clinical", "agent", "neutral")}
BACKEND = "zagent-backend:plan9"
APPS = {
    "postgres": "clinical",
    "privacy": "clinical",
    "tools-gateway": "clinical",
    "jobs": "clinical",
    "dispatcher": "clinical",
    "bff": "clinical",
    "web": "clinical",
    "agent-runtime": "agent",
    "llm-gateway": "agent",
    "eval-runner": "agent",
    "event-db": "neutral",
    "kb": "neutral",
    "otel-collector": "neutral",
    "tempo": "neutral",
    "analysis-worker": "clinical",
    "evidence-runner": "clinical",
    "cluster-init": "clinical",
}
FLOWS = [
    ("web", "bff", 8000),
    ("bff", "agent-runtime", 8000),
    ("bff", "postgres", 5432),
    ("bff", "privacy", 8003),
    ("bff", "jobs", 8005),
    ("bff", "llm-gateway", 8001),
    ("agent-runtime", "event-db", 5432),
    ("agent-runtime", "privacy", 8006),
    ("agent-runtime", "tools-gateway", 8002),
    ("agent-runtime", "jobs", 8005),
    ("agent-runtime", "kb", 8007),
    ("agent-runtime", "llm-gateway", 8001),
    ("llm-gateway", "privacy", 8006),
    ("event-db", "postgres", 5432),
    ("privacy", "postgres", 5432),
    ("tools-gateway", "postgres", 5432),
    ("tools-gateway", "privacy", 8003),
    ("jobs", "postgres", 5432),
    ("jobs", "privacy", 8003),
    ("dispatcher", "postgres", 5432),
    ("dispatcher", "privacy", 8003),
    ("analysis-worker", "postgres", 5432),
    ("cluster-init", "postgres", 5432),
    ("evidence-runner", "postgres", 5432),
    ("evidence-runner", "bff", 8000),
    ("evidence-runner", "tempo", 3200),
    ("eval-runner", "event-db", 5432),
    ("eval-runner", "privacy", 8006),
    ("otel-collector", "tempo", 4318),
]
FLOWS += [
    (app, "otel-collector", 4318)
    for app in (
        "bff",
        "agent-runtime",
        "llm-gateway",
        "privacy",
        "tools-gateway",
        "jobs",
        "dispatcher",
        "kb",
    )
]


def labels(name):
    return {"app.kubernetes.io/name": name}


def metadata(name, zone):
    return {"name": name, "namespace": ZONES[zone], "labels": labels(name)}


def peer(name):
    return {
        "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": ZONES[APPS[name]]}},
        "podSelector": {"matchLabels": labels(name)},
    }


def policies(api_ip="172.30.0.2"):
    resources = []
    dns = {
        "to": [
            {
                "namespaceSelector": {
                    "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                },
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }
        ],
        "ports": [{"protocol": protocol, "port": 53} for protocol in ("UDP", "TCP")],
    }
    for zone in ZONES:
        resources.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": metadata("default-deny", zone),
                "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
            }
        )
    for name, zone in APPS.items():
        incoming, outgoing = [], [dns]
        for source, target, port in FLOWS:
            if source == name:
                outgoing.append(
                    {"to": [peer(target)], "ports": [{"protocol": "TCP", "port": port}]}
                )
            if target == name:
                incoming.append(
                    {"from": [peer(source)], "ports": [{"protocol": "TCP", "port": port}]}
                )
        if name == "llm-gateway":
            outgoing.append(
                {
                    "to": [
                        {
                            "ipBlock": {
                                "cidr": "0.0.0.0/0",
                                "except": [
                                    "10.0.0.0/8",
                                    "172.16.0.0/12",
                                    "192.168.0.0/16",
                                    "127.0.0.0/8",
                                    "169.254.0.0/16",
                                    "100.64.0.0/10",
                                ],
                            }
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": 443}],
                }
            )
        if name == "dispatcher":
            outgoing.extend(
                [
                    {
                        "to": [{"ipBlock": {"cidr": f"{api_ip}/32"}}],
                        "ports": [{"protocol": "TCP", "port": 6443}],
                    },
                    {
                        "to": [{"ipBlock": {"cidr": "10.43.0.1/32"}}],
                        "ports": [{"protocol": "TCP", "port": 443}],
                    },
                ]
            )
        resources.append(
            {
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": metadata(f"allow-{name}", zone),
                "spec": {
                    "podSelector": {"matchLabels": labels(name)},
                    "policyTypes": ["Ingress", "Egress"],
                    "ingress": incoming,
                    "egress": outgoing,
                },
            }
        )
    return resources


def secret_env(variable, secret, key="url"):
    return {"name": variable, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}}


def workload(name, image, command, ports=(), env=None, *, role=None, storage=None, config=None):
    zone = APPS[name]
    if image == BACKEND:
        env = {"OTEL_SERVICE_NAME": f"zagent-{name}", **(env or {})}
    container = {
        "name": name,
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "command": command,
        "env": [{"name": key, "value": str(value)} for key, value in (env or {}).items()],
        "resources": {"requests": {"cpu": "20m", "memory": "64Mi"}, "limits": {"memory": "768Mi"}},
        "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
        "volumeMounts": [],
    }
    pod = {
        "automountServiceAccountToken": False,
        "containers": [container],
        "volumes": [],
        "terminationGracePeriodSeconds": 20,
    }
    if ports:
        container["ports"] = [{"containerPort": port} for port in ports]
        container["readinessProbe"] = {
            "tcpSocket": {"port": ports[0]},
            "periodSeconds": 2,
            "timeoutSeconds": 2,
            "failureThreshold": 30,
        }
        container["startupProbe"] = {
            "tcpSocket": {"port": ports[0]},
            "periodSeconds": 2,
            "timeoutSeconds": 2,
            "failureThreshold": 60,
        }
        container["livenessProbe"] = {
            "tcpSocket": {"port": ports[0]},
            "periodSeconds": 10,
            "timeoutSeconds": 2,
            "failureThreshold": 6,
        }
    if role:
        pod["volumes"].append(
            {"name": "privacy", "secret": {"secretName": f"privacy-{role}", "defaultMode": 256}}
        )
        container["volumeMounts"].append(
            {"name": "privacy", "mountPath": "/run/privacy", "readOnly": True}
        )
    if storage:
        pod["volumes"].append({"name": "data", "persistentVolumeClaim": {"claimName": name}})
        container["volumeMounts"].append({"name": "data", "mountPath": storage})
    if config:
        pod["volumes"].append({"name": "config", "configMap": {"name": name}})
        container["volumeMounts"].append({"name": "config", "mountPath": config, "readOnly": True})
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": metadata(name, zone),
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": labels(name)},
            "template": {"metadata": {"labels": labels(name)}, "spec": pod},
        },
    }


def uvicorn(module, port, factory=False):
    return [
        "uvicorn",
        module,
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--no-access-log",
        "--timeout-graceful-shutdown",
        "2",
        "--reload",
        "--reload-dir",
        "/app/services/agent/zagent",
    ] + (["--factory"] if factory else [])


def resources(api_ip="172.30.0.2", mode="replay"):
    items = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": namespace, "labels": {"zagent.io/zone": zone}},
        }
        for zone, namespace in ZONES.items()
    ]
    items.extend(policies(api_ip))
    for name in ("postgres", "tempo", "llm-gateway"):
        items.append(
            {
                "apiVersion": "v1",
                "kind": "PersistentVolumeClaim",
                "metadata": metadata(name, APPS[name]),
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "5Gi"}},
                },
            }
        )
    common = {
        "ZAGENT_LLM_MODE": mode,
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector.zagent-neutral:4318",
        "OTEL_BSP_SCHEDULE_DELAY": "1000",
        "WATCHFILES_FORCE_POLLING": "true",
    }
    owner = secret_env("DATABASE_URL", "owner-database")
    private = {"ZAGENT_PRIVACY_URL": "http://privacy:8003"}
    tokenized = {"ZAGENT_PRIVACY_URL": "http://privacy.zagent-clinical:8006"}
    deployments = []
    postgres = workload(
        "postgres",
        "postgres:16-alpine",
        ["docker-entrypoint.sh", "postgres", "-c", "max_connections=200"],
        [5432],
        {"POSTGRES_USER": "zagent", "POSTGRES_DB": "zagent"},
        storage="/var/lib/postgresql/data",
    )
    postgres["spec"]["template"]["spec"]["containers"][0]["env"].append(
        secret_env("POSTGRES_PASSWORD", "owner-database", "password")
    )
    postgres["spec"]["template"]["spec"]["containers"][0]["securityContext"] = {}
    deployments.append(postgres)
    privacy = workload(
        "privacy",
        BACKEND,
        uvicorn("zagent.privacy_server:app", 8003),
        [8003, 8006],
        common,
        role="master",
    )
    pod = privacy["spec"]["template"]["spec"]
    pod["containers"][0]["env"].append(owner)
    tokenizer = json.loads(json.dumps(pod["containers"][0]))
    for entry in tokenizer["env"]:
        if entry["name"] == "OTEL_SERVICE_NAME":
            entry["value"] = "zagent-tokenizer"
    tokenizer.update(
        name="tokenizer",
        command=uvicorn("zagent.privacy_server:create_tokenizer_app", 8006, True),
        ports=[{"containerPort": 8006}],
        readinessProbe={"httpGet": {"port": 8006, "path": "/health"}},
        startupProbe={"tcpSocket": {"port": 8006}, "periodSeconds": 2, "failureThreshold": 60},
        livenessProbe={"tcpSocket": {"port": 8006}, "periodSeconds": 10, "failureThreshold": 6},
    )
    pod["containers"].append(tokenizer)
    pod["initContainers"] = [
        {
            "name": "schema",
            "image": BACKEND,
            "command": ["python", "-m", "zagent.cluster_init"],
            "env": [
                owner,
                secret_env("RUNTIME_PASSWORD", "database-passwords", "runtime"),
                secret_env("WORKER_PASSWORD", "database-passwords", "worker"),
            ],
        }
    ]
    deployments.append(privacy)
    for name, module, port in (
        ("tools-gateway", "zagent.tools_server:app", 8002),
        ("jobs", "zagent.jobs_server:app", 8005),
    ):
        item = workload(
            name,
            BACKEND,
            uvicorn(module, port),
            [port],
            {**common, **private, "ZAGENT_PRIVACY_CAPABILITY_FILE": "/run/privacy/tools.key"},
            role="tools",
        )
        item["spec"]["template"]["spec"]["containers"][0]["env"].append(owner)
        deployments.append(item)
    dispatcher = workload(
        "dispatcher",
        BACKEND,
        [
            "watchfiles",
            "--filter",
            "python",
            "python -m zagent.dispatcher",
            "/app/services/agent/zagent",
        ],
        env={
            **common,
            **private,
            "ZAGENT_PRIVACY_CAPABILITY_FILE": "/run/privacy/tools.key",
            "ZAGENT_EXECUTOR": "kubernetes",
            "ZAGENT_JOB_NAMESPACE": ZONES["clinical"],
            "ZAGENT_JOB_IMAGE": "zagent-worker:plan9",
        },
        role="tools",
    )
    pod = dispatcher["spec"]["template"]["spec"]
    pod.update(serviceAccountName="dispatcher", automountServiceAccountToken=True)
    pod["containers"][0]["env"].append(owner)
    deployments.append(dispatcher)
    bff = workload(
        "bff",
        BACKEND,
        uvicorn("zagent.app:app", 8000),
        [8000],
        {
            **common,
            **private,
            "ZAGENT_DISPLAY_MODE": "1",
            "ZAGENT_MIGRATE": "0",
            "ZAGENT_RUNTIME_URL": "http://agent-runtime.zagent-agent:8000",
            "ZAGENT_GATEWAY_URL": "http://llm-gateway.zagent-agent:8001",
            "ZAGENT_JOBS_URL": "http://jobs:8005/mcp",
            "ZAGENT_PRIVACY_CAPABILITY_FILE": "/run/privacy/display.key",
        },
        role="display",
    )
    bff["spec"]["template"]["spec"]["containers"][0]["env"].append(owner)
    deployments.append(bff)
    web = workload(
        "web",
        "zagent-web:plan9",
        ["npm", "run", "dev", "--", "--host", "0.0.0.0"],
        [5173],
        {"AGENT_URL": "http://bff:8000"},
    )
    web["spec"]["template"]["spec"]["containers"][0]["resources"] = {
        "requests": {"cpu": "20m", "memory": "128Mi"},
        "limits": {"memory": "2Gi"},
    }
    deployments.append(web)
    runtime = workload(
        "agent-runtime",
        BACKEND,
        uvicorn("zagent.app:app", 8000),
        [8000],
        {
            **common,
            **tokenized,
            "ZAGENT_DISPLAY_MODE": "0",
            "ZAGENT_MIGRATE": "0",
            "ZAGENT_AGENT": "llm",
            "ZAGENT_GATEWAY_URL": "http://llm-gateway:8001",
            "ZAGENT_TOOLS_URL": "http://tools-gateway.zagent-clinical:8002/mcp",
            "ZAGENT_JOBS_URL": "http://jobs.zagent-clinical:8005/mcp",
            "ZAGENT_KB_URL": "http://kb.zagent-neutral:8007/mcp",
            "ZAGENT_PRIVACY_CAPABILITY_FILE": "/run/privacy/tokenize.key",
        },
        role="tokenize",
    )
    runtime["spec"]["template"]["spec"]["containers"][0]["env"].append(
        secret_env("DATABASE_URL", "runtime-database")
    )
    deployments.append(runtime)
    gateway = workload(
        "llm-gateway",
        BACKEND,
        uvicorn("zagent.gateway:app", 8001),
        [8001],
        {
            **common,
            **tokenized,
            "ZAGENT_MODEL": "deepseek/deepseek-v4.1-flash",
            "ZAGENT_LOCAL_INGRESS": "0",
            "ZAGENT_GATEWAY_AUDIT": "/var/lib/zagent/gateway-audit.sqlite3",
            "ZAGENT_PRIVACY_CAPABILITY_FILE": "/run/privacy/gateway.key",
        },
        role="gateway",
        storage="/var/lib/zagent",
    )
    if mode == "live":
        gateway["spec"]["template"]["spec"]["containers"][0]["env"].append(
            secret_env("OPENROUTER_API_KEY", "provider-key", "key")
        )
    deployments.append(gateway)
    event_db = workload(
        "event-db", "zagent-event-db:plan9", ["pgbouncer", "/etc/event-db/pgbouncer.ini"], [5432]
    )
    pod = event_db["spec"]["template"]["spec"]
    pod["containers"][0]["securityContext"].update(runAsUser=65534, runAsGroup=65534)
    pod["volumes"].append(
        {"name": "config", "secret": {"secretName": "event-db", "defaultMode": 292}}
    )
    pod["containers"][0]["volumeMounts"].append(
        {"name": "config", "mountPath": "/etc/event-db", "readOnly": True}
    )
    deployments.append(event_db)
    deployments.append(
        workload("kb", BACKEND, uvicorn("zagent.kb_server:app", 8007), [8007], common)
    )
    deployments.append(
        workload(
            "otel-collector",
            "otel/opentelemetry-collector:0.120.0",
            ["/otelcol", "--config=/etc/otel/config.yaml"],
            [4318, 13133],
            config="/etc/otel",
        )
    )
    tempo = workload(
        "tempo",
        "grafana/tempo:2.7.2",
        ["/tempo", "-config.file=/etc/tempo/config.yaml"],
        [3200, 4318],
        storage="/var/tempo",
        config="/etc/tempo",
    )
    tempo["spec"]["template"]["spec"]["securityContext"] = {"fsGroup": 10001}
    deployments.append(tempo)
    items.extend(deployments)
    for deployment in deployments:
        name = deployment["metadata"]["name"]
        ports = deployment["spec"]["template"]["spec"]["containers"][0].get("ports", [])
        if not ports:
            continue
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": metadata(name, APPS[name]),
            "spec": {
                "selector": labels(name),
                "ports": [
                    {
                        "name": f"tcp-{port['containerPort']}",
                        "port": port["containerPort"],
                        "targetPort": port["containerPort"],
                    }
                    for port in ports
                ],
            },
        }
        items.append(service)
    for name, filename in (("otel-collector", "otel.yaml"), ("tempo", "tempo.yaml")):
        items.append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": metadata(name, "neutral"),
                "data": {"config.yaml": (Path(__file__).parent / filename).read_text()},
            }
        )
    items.extend(
        [
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": metadata("dispatcher", "clinical"),
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "Role",
                "metadata": metadata("dispatcher", "clinical"),
                "rules": [
                    {
                        "apiGroups": ["batch"],
                        "resources": ["jobs"],
                        "verbs": ["create", "get", "list", "watch", "patch"],
                    },
                    {
                        "apiGroups": [""],
                        "resources": ["pods", "pods/log"],
                        "verbs": ["get", "list", "watch"],
                    },
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "RoleBinding",
                "metadata": metadata("dispatcher", "clinical"),
                "subjects": [
                    {"kind": "ServiceAccount", "name": "dispatcher", "namespace": ZONES["clinical"]}
                ],
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "Role",
                    "name": "dispatcher",
                },
            },
        ]
    )
    return items


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "apiVersion": "v1",
                "kind": "List",
                "items": resources(
                    os.environ.get("ZAGENT_API_IP", "172.30.0.2"),
                    os.environ.get("ZAGENT_CLUSTER_MODE", "replay"),
                ),
            }
        )
    )
