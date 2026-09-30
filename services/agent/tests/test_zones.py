import runpy
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[3]
COMPOSE = yaml.safe_load((ROOT / "deploy/compose/compose.yaml").read_text())


def service_networks(name):
    service = COMPOSE["services"][name]
    return set(service.get("networks", [])) if "network_mode" not in service else set()


def test_agent_zone_shares_no_network_with_clinical_data():
    for name in ("agent", "gateway", "kb"):
        assert "clinical" not in service_networks(name)
    for name in ("postgres", "privacy", "bff", "web", "dispatcher"):
        assert service_networks(name) == {"clinical"}
    bridges = {
        name for name in COMPOSE["services"] if {"clinical", "agent"} <= service_networks(name)
    }
    assert bridges == {"tools", "jobs", "tokenizer", "event-db", "collector", "display-relay"}


def test_only_gateway_has_internet_egress():
    networks = COMPOSE["networks"]
    assert all(networks[name]["internal"] for name in ("clinical", "agent", "telemetry"))
    options = networks["edge"]["driver_opts"]
    assert options["com.docker.network.bridge.enable_ip_masquerade"] == "false"
    assert [name for name in COMPOSE["services"] if "egress" in service_networks(name)] == [
        "gateway"
    ]
    published = [name for name, service in COMPOSE["services"].items() if "ports" in service]
    assert published == ["ingress"]
    assert all(port.startswith("127.0.0.1:") for port in COMPOSE["services"]["ingress"]["ports"])


def test_agent_reaches_privacy_and_events_only_through_restricted_endpoints():
    agent = COMPOSE["services"]["agent"]["environment"]
    assert agent["ZAGENT_PRIVACY_URL"] == "http://tokenizer:8006"
    assert agent["DATABASE_URL"].startswith("postgresql://zagent_runtime:")
    assert "@event-db:" in agent["DATABASE_URL"]
    assert "--factory" in COMPOSE["services"]["tokenizer"]["command"]
    assert "create_tokenizer_app" in " ".join(COMPOSE["services"]["tokenizer"]["command"])
    relay = COMPOSE["services"]["display-relay"]["environment"]["ZAGENT_RELAY_ROUTES"]
    from zagent.relay import parse_routes

    assert {host for host, _ in parse_routes(relay).values()} == {"agent", "gateway"}
    pgbouncer = (ROOT / "deploy/compose/event-db/pgbouncer.ini").read_text()
    assert "user=zagent_runtime" in pgbouncer
    assert (ROOT / "deploy/compose/event-db/users.txt").read_text().count("\n") == 1


def test_zone_targets_deny_clinical_data_by_name_and_address():
    zones = runpy.run_path(str(ROOT / "deploy/compose/zones.py"))
    running = {
        name: {"NetworkSettings": {"Networks": {"zagent_clinical": {"IPAddress": f"10.0.0.{i}"}}}}
        for i, name in enumerate(("postgres", "privacy", "bff", "web"), start=1)
    }
    for source in ("agent", "gateway", "kb", "worker"):
        targets = zones["targets_for"](source, running)
        denied = {target["host"] for target in targets if not target["allowed"]}
        assert {"postgres", "privacy", "bff", "web"} <= denied
        assert {f"10.0.0.{i}" for i in range(1, 5)} <= denied
        internet = next(target for target in targets if target["name"] == "internet")
        assert internet["allowed"] is (source == "gateway")
    assert not any(
        target["host"] in {"postgres", "privacy"}
        for target in zones["targets_for"]("agent", running)
        if target["allowed"]
    )


def test_network_probe_requires_matching_positive_and_negative_results(monkeypatch):
    from zagent.zone_probe import probe

    def refused(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr("socket.create_connection", refused)
    target = {"name": "probe", "host": "example.invalid", "port": 443, "allowed": True}
    assert not probe(target)["passed"]
    assert probe({**target, "allowed": False})["passed"]
