import os
import subprocess
import sys
from pathlib import Path

SCOPE_FILTER = "SCOPE-*"


def main():
    Path("/evidence").mkdir(exist_ok=True)
    if sys.argv[1:] == ["workflows"]:
        commands = [[sys.executable, "deploy/cluster/workflows.py"]]
    elif sys.argv[1:] == ["agent"]:
        commands = [
            [
                "zagent",
                "evals",
                "--mode",
                "replay",
                "--filter",
                SCOPE_FILTER,
                "--no-chaos",
                "--output",
                "/evidence/scope",
            ]
        ]
    else:
        commands = [
            [sys.executable, "-m", "pytest", "-q", "--junitxml=/evidence/tests.xml"],
            [
                "zagent",
                "evals",
                "--mode",
                "replay",
                "--accept-known-findings",
                "--output",
                "/evidence/full",
                *sys.argv[1:],
            ],
            [sys.executable, "deploy/cluster/workflows.py"],
        ]
    for provider in ("OPENROUTER", "OPENAI"):
        os.environ.pop(f"{provider}_API_KEY", None)
        os.environ[f"{provider}_API_KEY_FILE"] = "/dev/null"
    for command in commands:
        result = subprocess.run(command, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
