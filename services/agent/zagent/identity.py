"""Simulated personas and the signed caller context the broker verifies for knowledge access."""

import os
import time
from functools import cache
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zagent.faults import enabled

CALLER_CONTEXT_META = "zagent/caller-context"
ISSUER = "zagent-bff"
AUDIENCE = "zagent-broker"
CONTEXT_TTL_SECONDS = 900
SIGNING_KEY_FILE = "ZAGENT_CALLER_SIGNING_KEY_FILE"
VERIFY_KEY_FILE = "ZAGENT_CALLER_VERIFY_KEY_FILE"
SITE_AUDIENCE = "zknowledge-site"
GRANT_TTL_SECONDS = 60
GRANT_SIGNING_KEY_FILE = "ZAGENT_SITE_SIGNING_KEY_FILE"

PersonaId = Literal["lab-technologist", "analyst", "qa-officer", "lab-director"]


class Persona(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: PersonaId
    name: str
    title: str
    roles: tuple[str, ...]
    description: str


PERSONAS: dict[str, Persona] = {
    persona.id: persona
    for persona in (
        Persona(
            id="lab-technologist",
            name="Tamsin Rook",
            title="Lab technologist",
            roles=("lab-technologist",),
            description="Published documents for this site",
        ),
        Persona(
            id="analyst",
            name="Ilse Marrow",
            title="Analyst",
            roles=("analyst",),
            description="Published documents for this site",
        ),
        Persona(
            id="qa-officer",
            name="Odile Fenn",
            title="QA officer",
            roles=("qa-officer",),
            description="Also draft procedures, QC review notes and open change proposals",
        ),
        Persona(
            id="lab-director",
            name="Caspar Wend",
            title="Lab director",
            roles=("lab-director",),
            description="Also draft procedures, QC review notes and administration pages",
        ),
    )
}
DEFAULT_PERSONA: PersonaId = "analyst"


class CallerContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    iss: Literal["zagent-bff"]
    aud: Literal["zagent-broker"]
    iat: int
    exp: int
    session: UUID
    turn: UUID
    site: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    persona: PersonaId
    roles: tuple[str, ...] = Field(max_length=8)


class CallerRejected(Exception):
    pass


@cache
def development_key() -> Ed25519PrivateKey:
    """A per-process key, so an unconfigured service can only verify its own contexts."""
    return Ed25519PrivateKey.generate()


class CallerSigner:
    """Held only by the BFF."""

    def __init__(self, key: Ed25519PrivateKey, ttl: int = CONTEXT_TTL_SECONDS):
        self.key = key
        self.ttl = ttl

    @classmethod
    def configured(cls) -> "CallerSigner":
        path = os.environ.get(SIGNING_KEY_FILE)
        if not path:
            return cls(development_key())
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("The caller signing key must be Ed25519")
        return cls(key)

    def mint(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        site: str,
        persona: str,
        now: float | None = None,
    ) -> str:
        issued = int(time.time() if now is None else now)
        claims = CallerContext(
            iss=ISSUER,
            aud=AUDIENCE,
            iat=issued,
            exp=issued + self.ttl,
            session=session_id,
            turn=turn_id,
            site=site,
            persona=persona,
            roles=PERSONAS[persona].roles,
        )
        return jwt.encode(claims.model_dump(mode="json"), self.key, algorithm="EdDSA")


class CallerVerifier:
    """Held only by the broker."""

    def __init__(self, key: Ed25519PublicKey):
        self.key = key

    @classmethod
    def configured(cls) -> "CallerVerifier":
        path = os.environ.get(VERIFY_KEY_FILE)
        if not path:
            return cls(development_key().public_key())
        key = serialization.load_pem_public_key(Path(path).read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("The caller verification key must be Ed25519")
        return cls(key)

    def verify(self, token: object, *, session_id: UUID, turn_id: UUID) -> CallerContext:
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise CallerRejected("missing caller context")
        try:
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["EdDSA"],
                audience=AUDIENCE,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "aud", "iss"]}
                if not enabled("trust_unsigned_context")
                else {"verify_signature": False},
            )
            context = CallerContext.model_validate(claims)
        except (jwt.InvalidTokenError, ValidationError) as error:
            raise CallerRejected(type(error).__name__) from error
        if context.session != session_id or context.turn != turn_id:
            raise CallerRejected("caller context belongs to another conversation turn")
        return context


@cache
def development_grant_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


class GrantSigner:
    """Held only by the BFF: one-minute, single-use grants that open a citation on the intranet."""

    def __init__(self, key: Ed25519PrivateKey, ttl: int = GRANT_TTL_SECONDS):
        self.key = key
        self.ttl = ttl

    @classmethod
    def configured(cls) -> "GrantSigner":
        path = os.environ.get(GRANT_SIGNING_KEY_FILE)
        if not path:
            return cls(development_grant_key())
        key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("The intranet grant signing key must be Ed25519")
        return cls(key)

    def mint(
        self,
        *,
        site: str,
        persona: str,
        document: str,
        snapshot: str | None = None,
        lines: str | None = None,
        quote: str | None = None,
        now: float | None = None,
    ) -> str:
        issued = int(time.time() if now is None else now)
        claims = {
            "iss": ISSUER,
            "aud": SITE_AUDIENCE,
            "iat": issued,
            "exp": issued + self.ttl,
            "jti": uuid4().hex,
            "persona": persona,
            "site": site,
            "roles": list(PERSONAS[persona].roles),
            "document": document,
            "snapshot": snapshot,
            "lines": lines,
            "q": quote,
        }
        return jwt.encode(
            {name: value for name, value in claims.items() if value is not None},
            self.key,
            algorithm="EdDSA",
        )


def write_keypair(signing: Path, verify: Path) -> None:
    """Create the BFF's signing key once and (re)derive the broker's verification key."""
    signing.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    verify.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not signing.exists():
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        descriptor = os.open(signing, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(pem)
    key = serialization.load_pem_private_key(signing.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Invalid caller signing key")
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    descriptor = os.open(verify, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(public)
    verify.chmod(0o600)
