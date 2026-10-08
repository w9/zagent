import os
import secrets
from pathlib import Path

from zagent.identity import write_keypair
from zagent.privacy_server import capability


def main() -> None:
    root = Path(os.environ.get("ZAGENT_PRIVACY_KEYS", "/keys"))
    master_path = root / "master/master.key"
    master_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not master_path.exists():
        descriptor = os.open(master_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(secrets.token_bytes(32))
    master = master_path.read_bytes()
    if len(master) < 32:
        raise ValueError("Invalid privacy master key")
    for role in ("tokenize", "display", "tools", "gateway"):
        path = root / role / f"{role}.key"
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(capability(master, role))
        path.chmod(0o600)
    write_keypair(
        root / "caller-signing/caller-signing.pem", root / "caller-verify/caller-verify.pem"
    )
    write_keypair(root / "site-signing/site-signing.pem", root / "site-verify/site-verify.pem")
    print("Privacy capabilities initialized; no credentials were printed.")


if __name__ == "__main__":
    main()
