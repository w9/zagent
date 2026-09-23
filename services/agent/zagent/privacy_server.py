import asyncio
import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from zagent.cohort import ClinicalStore, configured_clock
from zagent.privacy import EgressTripwire, PrivacyError, Raw, Tokenized
from zagent.privacy_store import PrivacyStore
from zagent.store import DEFAULT_DATABASE_URL, Store


def capability(master: bytes, role: str) -> str:
    return hmac.new(master, f"privacy:{role}".encode(), hashlib.sha256).hexdigest()


class PrivacyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: UUID
    value: Any
    path: str = "user_message"
    value_schema: dict | None = Field(default=None, alias="schema")
    external: bool = False
    strict: bool = False


class SessionInput(BaseModel):
    session_id: UUID


def create_privacy_app(
    master: bytes | None = None,
    backend: PrivacyStore | None = None,
    *,
    allow_resolution: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        key_path = Path(os.environ.get("ZAGENT_PRIVACY_MASTER_FILE", "/run/privacy/master.key"))
        key = master or await asyncio.to_thread(key_path.read_bytes)
        app.state.master = key
        store = None
        if backend is None:
            store = await Store.open(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))
            await store.migrate()
            await ClinicalStore(store, configured_clock()).seed()
            app.state.privacy = PrivacyStore(store.pool)
            await app.state.privacy.migrate_history()
        else:
            app.state.privacy = backend
        try:
            yield
        finally:
            if store is not None:
                await store.close()

    app = FastAPI(title="Zagent privacy service", lifespan=lifespan)
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-privacy" if allow_resolution else "zagent-tokenizer", app)
    if master is not None:
        app.state.master = master
    if backend is not None:
        app.state.privacy = backend

    def authorize(authorization: str | None, roles: set[str]) -> None:
        supplied = (authorization or "").removeprefix("Bearer ")
        if not any(
            hmac.compare_digest(supplied, capability(app.state.master, role)) for role in roles
        ):
            raise HTTPException(403, "Privacy capability does not permit this operation")

    @app.exception_handler(PrivacyError)
    async def privacy_error(_request, _error):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": "Privacy operation rejected"})

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/tokenize")
    async def tokenize(body: PrivacyInput, authorization: str | None = Header(default=None)):
        authorize(authorization, {"tokenize", "display", "tools", "gateway"})
        return await app.state.privacy.tokenize(
            body.session_id,
            Raw(value=body.value),
            path=body.path,
            schema=body.value_schema,
            external=body.external,
        )

    @app.post("/resolve")
    async def resolve(body: PrivacyInput, authorization: str | None = Header(default=None)):
        authorize(authorization, {"display", "tools"})
        return await app.state.privacy.resolve(
            body.session_id,
            Tokenized(value=body.value),
            strict=body.strict,
        )

    @app.post("/bindings")
    async def bindings(body: SessionInput, authorization: str | None = Header(default=None)):
        authorize(authorization, {"display"})
        return await app.state.privacy.bindings(body.session_id)

    @app.post("/tripwire")
    async def tripwire(authorization: str | None = Header(default=None)):
        authorize(authorization, {"gateway"})
        key = bytes.fromhex(capability(app.state.master, "tripwire"))
        return {
            "key": key.hex(),
            "manifest": EgressTripwire.manifest(
                key,
                await app.state.privacy.registry(),
            ).model_dump(),
        }

    if not allow_resolution:
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", "") not in {"/resolve", "/bindings"}
        ]
    return app


def create_tokenizer_app() -> FastAPI:
    return create_privacy_app(allow_resolution=False)


app = create_privacy_app()
