"""Simulated single sign-on and the citation grants the workbench signs for the intranet."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zknowledge.faults import enabled
from zknowledge.index import Caller

GRANT_ISSUER = "zagent-bff"
GRANT_AUDIENCE = "zknowledge-site"
GRANT_LIFETIME_LIMIT = 120
VERIFY_KEY_FILE = "ZKNOWLEDGE_GRANT_VERIFY_KEY_FILE"
SESSION_COOKIE = "meridian_session"
SESSION_SECONDS = 8 * 3600
# The core's staff directory. It mirrors the workbench's personas, which a cross-team test checks.
STAFF = {
    "lab-technologist": ("Tamsin Rook", "Lab technologist", ("lab-technologist",)),
    "analyst": ("Ilse Marrow", "Analyst", ("analyst",)),
    "qa-officer": ("Odile Fenn", "QA officer", ("qa-officer",)),
    "lab-director": ("Caspar Wend", "Lab director", ("lab-director",)),
}
SITES = {
    "northgate": "Northgate Genomics Centre",
    "lakeside": "Lakeside Helix Hospital",
    "sequoia": "Sequoia Research Hospital",
    "cedar": "Cedar Vale Medical Centre",
    "harbor": "Harbor Light Hospital",
}


class Visitor(BaseModel):
    model_config = ConfigDict(frozen=True)
    persona: str
    site: str
    via: str = "signin"
    expires: int

    @property
    def name(self) -> str:
        return STAFF[self.persona][0]

    @property
    def title(self) -> str:
        return STAFF[self.persona][1]

    @property
    def site_name(self) -> str:
        return SITES[self.site]

    @property
    def roles(self) -> tuple[str, ...]:
        return STAFF[self.persona][2]


class Everyone(Caller):
    """The caller a broken site would use: no site or role filtering at all."""

    def sees(self, sites: list[str], roles: list[str]) -> bool:
        return True


def caller(visitor: Visitor | None) -> Caller:
    if enabled("site_acl_off"):
        return Everyone()
    if visitor is None:
        return Caller(None, [])
    return Caller(visitor.site, list(visitor.roles))


class Sessions:
    """Signed visitor cookies; the secret lives only in this process."""

    def __init__(self, secret: bytes | None = None):
        self.secret = secret or secrets.token_bytes(32)

    def issue(self, persona: str, site: str, via: str = "signin", now: float | None = None) -> str:
        if persona not in STAFF or site not in SITES:
            raise ValueError("Unknown staff member or site")
        visitor = Visitor(
            persona=persona,
            site=site,
            via=via,
            expires=int(time.time() if now is None else now) + SESSION_SECONDS,
        )
        payload = base64.urlsafe_b64encode(visitor.model_dump_json().encode()).decode()
        return f"{payload}.{self.sign(payload)}"

    def read(self, value: str | None, now: float | None = None) -> Visitor | None:
        if not value or len(value) > 1024 or "." not in value:
            return None
        payload, signature = value.rsplit(".", 1)
        if not hmac.compare_digest(signature, self.sign(payload)):
            return None
        try:
            visitor = Visitor.model_validate_json(base64.urlsafe_b64decode(payload))
        except (ValueError, ValidationError):
            return None
        current = time.time() if now is None else now
        if visitor.expires < current or visitor.persona not in STAFF or visitor.site not in SITES:
            return None
        return visitor

    def sign(self, payload: str) -> str:
        return hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()


class Grant(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    iss: str
    aud: str
    iat: int
    exp: int
    jti: str = Field(pattern=r"^[a-f0-9]{32}$")
    persona: str
    site: str
    roles: tuple[str, ...] = Field(max_length=8)
    document: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    snapshot: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    lines: str | None = Field(default=None, pattern=r"^[0-9]{1,5}(?:-[0-9]{1,5})?$")
    q: str | None = Field(default=None, max_length=300)


class GrantRejected(Exception):
    pass


class GrantVerifier:
    """Verifies workbench-signed grants and accepts each one only once."""

    def __init__(self, key: Ed25519PublicKey | None):
        self.key = key
        self.used: dict[str, int] = {}
        self.lock = threading.Lock()

    @classmethod
    def configured(cls) -> "GrantVerifier":
        path = os.environ.get(VERIFY_KEY_FILE)
        if not path:
            return cls(None)
        key = serialization.load_pem_public_key(Path(path).read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("The grant verification key must be Ed25519")
        return cls(key)

    def redeem(self, token: str | None, now: float | None = None) -> Grant:
        if self.key is None:
            raise GrantRejected("citation grants are not configured")
        if not token or len(token) > 4096 or not re.fullmatch(r"[A-Za-z0-9_.-]+", token):
            raise GrantRejected("missing grant")
        current = int(time.time() if now is None else now)
        try:
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["EdDSA"],
                audience=GRANT_AUDIENCE,
                issuer=GRANT_ISSUER,
                options={"require": ["exp", "iat", "aud", "iss", "jti"]}
                if not enabled("site_trust_unsigned_grant")
                else {"verify_signature": False},
                leeway=5,
            )
            grant = Grant.model_validate(claims)
        except (jwt.InvalidTokenError, ValidationError, ValueError) as error:
            raise GrantRejected(type(error).__name__) from error
        if grant.exp - grant.iat > GRANT_LIFETIME_LIMIT:
            raise GrantRejected("grant lifetime too long")
        if grant.persona not in STAFF or grant.site not in SITES:
            raise GrantRejected("unknown staff member or site")
        if tuple(grant.roles) != STAFF[grant.persona][2]:
            raise GrantRejected("roles disagree with the staff directory")
        with self.lock:
            self.used = {jti: expires for jti, expires in self.used.items() if expires >= current}
            if grant.jti in self.used:
                raise GrantRejected("grant already used")
            self.used[grant.jti] = grant.exp + 5
        return grant
