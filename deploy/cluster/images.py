import os
import subprocess
import sys

FILES = {
    "backend": "services/agent/Dockerfile",
    "web": "apps/web/Dockerfile",
    "event-db": "deploy/cluster/EventDB.Dockerfile",
}

image = os.environ["EXPECTED_REF"]
subprocess.run(["docker", "build", "--file", FILES[sys.argv[1]], "--tag", image, "."], check=True)
subprocess.run(
    ["k3d", "image", "import", image, "--cluster", "zagent-plan9", "--mode", "direct"], check=True
)
for node in ("k3d-zagent-plan9-server-0", "k3d-zagent-plan9-agent-0"):
    subprocess.run(
        ["docker", "exec", node, "crictl", "inspecti", image], check=True, stdout=subprocess.DEVNULL
    )
