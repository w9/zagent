"""Verify Compose network zones by probing from each service's network position."""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = os.environ.get("COMPOSE_PROJECT_NAME", "zagent")
INTERNET = ("1.1.1.1", 443)
AGENT_ZONE = ("agent", "gateway")
KNOWLEDGE_ZONE = ("kb",)
KNOWLEDGE_BRIDGE = "mcp-broker"
INTRANET_ZONE = ("kb-site", "intranet-ingress")
CLINICAL_DATA = (("postgres", 5432), ("privacy", 8003), ("bff", 8000), ("web", 5173))
KNOWLEDGE_DATA = (("kb", 8007),)
INTRANET_DATA = (("kb-site", 8009),)
AGENT_SERVICES = (
    ("agent", 8000),
    ("gateway", 8001),
    ("tools", 8002),
    ("jobs", 8005),
    ("tokenizer", 8006),
    ("event-db", 5432),
)
RUNTIME_DATABASE = "postgresql://zagent_runtime:zagent_runtime@event-db:5432/zagent"
COLLECTOR = ("collector", 4318)
FLOWS = {
    "agent": [
        ("gateway", 8001),
        ("tools", 8002),
        ("jobs", 8005),
        (KNOWLEDGE_BRIDGE, 8008),
        ("tokenizer", 8006),
        ("event-db", 5432),
        COLLECTOR,
    ],
    "gateway": [("tokenizer", 8006), COLLECTOR],
    KNOWLEDGE_BRIDGE: [("kb", 8007), ("tokenizer", 8006), COLLECTOR],
    "kb": [COLLECTOR],
    # Its own port is the positive control: the site needs no outbound route at all.
    "kb-site": [("kb-site", 8009)],
    "intranet-ingress": [("kb-site", 8009)],
    "tokenizer": [("postgres", 5432), COLLECTOR],
    "event-db": [("postgres", 5432)],
    "tools": [("postgres", 5432), ("privacy", 8003), COLLECTOR],
    "jobs": [("postgres", 5432), ("privacy", 8003), COLLECTOR],
    "privacy": [("postgres", 5432), COLLECTOR],
    "dispatcher": [("postgres", 5432), ("privacy", 8003), COLLECTOR],
    "bff": [
        ("postgres", 5432),
        ("privacy", 8003),
        ("jobs", 8005),
        ("display-relay", 8000),
        ("display-relay", 8001),
        COLLECTOR,
    ],
    "web": [("bff", 8000)],
    "display-relay": [("agent", 8000), ("gateway", 8001)],
    "ingress": [("web", 5173), ("bff", 8000), ("postgres", 5432), ("grafana", 3000)],
    "collector": [("tempo", 4318)],
    "grafana": [("tempo", 3200)],
}


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"docker {' '.join(args[:2])}: {result.stderr.strip()}")
    return result.stdout


def running_services() -> dict[str, dict]:
    identifiers = docker(
        "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.ID}}"
    ).split()
    if not identifiers:
        raise SystemExit(f"No running Compose project {PROJECT!r}; run `make up` first.")
    return {
        item["Config"]["Labels"]["com.docker.compose.service"]: item
        for item in json.loads(docker("inspect", *identifiers))
    }


def networks(container: dict) -> list[str]:
    return list(container["NetworkSettings"]["Networks"])


def addresses(container: dict) -> list[str]:
    return [
        network["IPAddress"]
        for network in container["NetworkSettings"]["Networks"].values()
        if network["IPAddress"]
    ]


def denied_for(source: str) -> tuple[tuple[str, int], ...]:
    if source in AGENT_ZONE or source == "worker":
        return CLINICAL_DATA + KNOWLEDGE_DATA + INTRANET_DATA
    if source in KNOWLEDGE_ZONE:
        return CLINICAL_DATA + AGENT_SERVICES + INTRANET_DATA
    if source == KNOWLEDGE_BRIDGE:
        return CLINICAL_DATA + INTRANET_DATA
    if source in INTRANET_ZONE:
        return (
            CLINICAL_DATA + AGENT_SERVICES + KNOWLEDGE_DATA + ((KNOWLEDGE_BRIDGE, 8008), COLLECTOR)
        )
    if source == "ingress":
        return INTRANET_DATA
    return ()


def denial_names(services: tuple[tuple[str, int], ...]) -> set[str]:
    return {f"deny-{target}-{kind}" for target, _port in services for kind in ("name", "ip")}


def targets_for(source: str, running: dict[str, dict]) -> list[dict]:
    targets = [
        {"name": f"allow-{host}-{port}", "host": host, "port": port, "allowed": True}
        for host, port in FLOWS.get(source, [])
    ]
    targets.append(
        {
            "name": "internet",
            "host": INTERNET[0],
            "port": INTERNET[1],
            "allowed": source == "gateway",
        }
    )
    for target, port in denied_for(source):
        targets.append(
            {"name": f"deny-{target}-name", "host": target, "port": port, "allowed": False}
        )
        targets += [
            {"name": f"deny-{target}-ip", "host": address, "port": port, "allowed": False}
            for address in addresses(running[target])
        ]
    return targets


def probe(image: str, attached: list[str], targets: list[dict], env: dict | None = None) -> dict:
    """Run the probe in a fresh container attached to exactly the given networks."""
    create = [
        "create",
        "--label",
        "zagent.zone-probe=1",
        "--network",
        attached[0] if attached else "none",
    ]
    for key, value in (env or {}).items():
        create += ["--env", f"{key}={value}"]
    container = docker(*create, image, "python", "-m", "zagent.zone_probe", json.dumps(targets))
    container = container.strip()
    try:
        for network in attached[1:]:
            docker("network", "connect", network, container)
        output = subprocess.run(
            ["docker", "start", "--attach", container], text=True, capture_output=True
        ).stdout
    finally:
        docker("rm", "--force", container)
    return json.loads(next(line for line in output.splitlines() if line.startswith('{"checks":')))


def verify() -> None:
    started = time.monotonic()
    running = running_services()
    image = running["agent"]["Config"]["Image"]

    def check(source: str) -> dict:
        attached = [] if source == "worker" else networks(running[source])
        env = (
            {"DATABASE_URL": RUNTIME_DATABASE, "ZAGENT_CHECK_RUNTIME_ROLE": "1"}
            if source == "agent"
            else None
        )
        return {"service": source, **probe(image, attached, targets_for(source, running), env)}

    with ThreadPoolExecutor(max_workers=8) as pool:
        reports = list(pool.map(check, [*sorted(running), "worker"]))
    checks = [(report["service"], check) for report in reports for check in report["checks"]]
    denials = [
        check
        for source, check in checks
        if source in AGENT_ZONE and check["name"] in denial_names(CLINICAL_DATA)
    ]
    knowledge = [
        check
        for source, check in checks
        if source in (*KNOWLEDGE_ZONE, KNOWLEDGE_BRIDGE)
        or (source in AGENT_ZONE and check["name"] in denial_names(KNOWLEDGE_DATA))
    ]
    intranet = [
        check
        for source, check in checks
        if source in INTRANET_ZONE or check["name"] in denial_names(INTRANET_DATA)
    ]
    requirements = {
        "REQ-PHI-05": bool(denials) and all(check["passed"] for check in denials),
        "REQ-PHI-06": all(check["passed"] for _, check in checks if check["name"] == "internet"),
        "REQ-KB-01": bool(knowledge) and all(check["passed"] for check in knowledge),
        "REQ-KB-06": bool(intranet) and all(check["passed"] for check in intranet),
        "REQ-ISO-02": all(
            check["passed"]
            for source, check in checks
            if source == "agent" and "expected" not in check
        ),
        "REQ-META-01": all(check["passed"] for _, check in checks if check.get("expected") is True),
    }
    report = {
        "seconds": round(time.monotonic() - started, 2),
        "passed": all(requirements.values()) and all(report["passed"] for report in reports),
        "requirements": requirements,
        "services": reports,
    }
    output = ROOT / "docs/evals/zones/results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    failures = [
        {"service": source, "check": check} for source, check in checks if not check["passed"]
    ]
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "seconds": report["seconds"],
                "requirements": requirements,
                "services": len(reports),
                "checks": len(checks),
                "failures": failures,
                "report": str(output.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if report["passed"] else 1)


ZONE_MUTATIONS = {
    "zones_off": ("clinical", CLINICAL_DATA, "REQ-PHI-05"),
    "kb_direct_route": ("knowledge", KNOWLEDGE_DATA, "REQ-KB-01"),
    "site_direct_route": ("intranet", INTRANET_DATA, "REQ-KB-06"),
}


def mutation(name: str = "zones_off") -> None:
    """Paired experiment: an agent-position probe, then one also attached to a protected zone."""
    zone, protected, requirement = ZONE_MUTATIONS[name]
    running = running_services()
    image = running["agent"]["Config"]["Image"]
    base = networks(running["agent"])
    targets = targets_for("agent", running)

    def side(attached: list[str]) -> dict:
        checks = probe(image, attached, targets)["checks"]
        controls = {check["name"]: check["passed"] for check in checks if check["expected"]}
        denials = [check for check in checks if check["name"] in denial_names(protected)]
        return {
            "healthy": bool(controls) and all(controls.values()),
            "controls": controls,
            "requirements": {requirement: all(check["passed"] for check in denials)},
            "observed": {
                "networks": attached,
                "protected_routes": sorted(
                    check["name"] for check in denials if check["connected"]
                ),
            },
        }

    print(json.dumps({"control": side(base), "mutant": side([*base, f"{PROJECT}_{zone}"])}))


if __name__ == "__main__":
    if sys.argv[1:2] == ["verify"]:
        verify()
    elif sys.argv[1:2] == ["mutation"] and sys.argv[2:3] in (
        [],
        *([name] for name in ZONE_MUTATIONS),
    ):
        mutation(*sys.argv[2:3])
    else:
        raise SystemExit(
            "Usage: zones.py verify|mutation [zones_off|kb_direct_route|site_direct_route]"
        )
