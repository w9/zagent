import hashlib
import json
import urllib.request

import yaml

CALICO_URL = "https://raw.githubusercontent.com/projectcalico/calico/v3.29.3/manifests/calico.yaml"
CALICO_SHA256 = "9a575859428b822a224dedafc4238555b6b0f910f2abf12983f20f871860914e"
CNI_DIRECTORY = "/etc/cni/net.d"
FLANNEL_DIRECTORY = "/var/lib/rancher/k3s/agent/etc/cni/net.d"


def configure(items):
    for item in items:
        if item["kind"] == "ConfigMap" and item["metadata"]["name"] == "calico-config":
            item["data"]["calico_backend"] = "vxlan"
            item["data"]["cni_network_config"] = json.dumps(
                {
                    "name": "k8s-pod-network",
                    "cniVersion": "0.3.1",
                    "plugins": [
                        {
                            "type": "calico",
                            "datastore_type": "kubernetes",
                            "log_level": "warning",
                            "nodename": "__KUBERNETES_NODE_NAME__",
                            "mtu": 1450,
                            "ipam": {"type": "calico-ipam"},
                            "policy": {"type": "k8s"},
                            "container_settings": {"allow_ip_forwarding": True},
                            "policy_setup_timeout_seconds": 30,
                            "endpoint_status_dir": "/var/run/calico/endpoint-status",
                            "kubernetes": {"kubeconfig": f"{CNI_DIRECTORY}/calico-kubeconfig"},
                        },
                        {"type": "portmap", "snat": True, "capabilities": {"portMappings": True}},
                        {"type": "bandwidth", "capabilities": {"bandwidth": True}},
                    ],
                }
            )
        if item["kind"] == "DaemonSet" and item["metadata"]["name"] == "calico-node":
            pod = item["spec"]["template"]["spec"]
            for volume in pod["volumes"]:
                if volume["name"] == "cni-bin-dir":
                    volume["hostPath"]["path"] = "/opt/cni/bin"
                if volume["name"] == "cni-net-dir":
                    volume["hostPath"]["path"] = CNI_DIRECTORY
                    volume["hostPath"]["type"] = "DirectoryOrCreate"
            container = pod["containers"][0]
            values = {
                "CLUSTER_TYPE": "k8s",
                "CALICO_IPV4POOL_IPIP": "Never",
                "CALICO_IPV4POOL_VXLAN": "Always",
                "CALICO_IPV4POOL_CIDR": "10.42.0.0/16",
                "FELIX_ENDPOINTSTATUSPATHPREFIX": "/var/run/calico",
                "FELIX_DEFAULTENDPOINTTOHOSTACTION": "RETURN",
                "FELIX_LOGSEVERITYSCREEN": "Warning",
            }
            container["env"] = [entry for entry in container["env"] if entry["name"] not in values]
            container["env"] += [{"name": name, "value": value} for name, value in values.items()]
            for kind, argument in (
                ("livenessProbe", "-felix-live"),
                ("readinessProbe", "-felix-ready"),
            ):
                container[kind]["exec"]["command"] = ["/bin/calico-node", argument]
    return items


def install(run, state):
    path = state / "calico.yaml"
    if not path.exists():
        with urllib.request.urlopen(CALICO_URL, timeout=60) as response:
            path.write_bytes(response.read())
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != CALICO_SHA256:
        raise RuntimeError("Pinned Calico manifest checksum mismatch")
    items = configure(list(yaml.safe_load_all(source)))
    run(
        "kubectl",
        "apply",
        "--server-side",
        "--field-manager=zagent-cluster",
        "-f",
        "-",
        data=json.dumps({"apiVersion": "v1", "kind": "List", "items": items}),
    )
    run(
        "kubectl",
        "rollout",
        "status",
        "daemonset/calico-node",
        "-n",
        "kube-system",
        "--timeout=180s",
    )
    run("kubectl", "wait", "nodes", "--all", "--for=condition=Ready", "--timeout=90s")


def migrate_flannel(run, save, state, cluster):
    configuration = state / "k3s-policy.yaml"
    save(configuration, yaml.safe_dump({"flannel-backend": "none", "disable-network-policy": True}))
    run("docker", "cp", str(configuration), f"k3d-{cluster}-server-0:/etc/rancher/k3s/config.yaml")
    run("k3d", "cluster", "stop", cluster)
    run("k3d", "cluster", "start", cluster)
    for suffix in ("server-0", "agent-0"):
        node = f"k3d-{cluster}-{suffix}"
        rules = run("docker", "exec", node, "iptables-save", capture=True)
        retained = [
            line
            for line in rules.splitlines()
            if not any(prefix in line for prefix in ("KUBE-ROUTER", "KUBE-POD-FW", "KUBE-NWPLCY"))
        ]
        run("docker", "exec", "-i", node, "iptables-restore", data="\n".join(retained) + "\n")
        run(
            "docker",
            "exec",
            node,
            "mv",
            f"{FLANNEL_DIRECTORY}/10-flannel.conflist",
            f"{FLANNEL_DIRECTORY}/10-flannel.conflist.disabled",
        )
