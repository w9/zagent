import asyncio
import json
import os
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from zagent.llm import (
    DEFAULT_MODEL,
    Completion,
    CompletionRequest,
    GatewayError,
    LlmGateway,
    ModelRoute,
)
from zagent.privacy import EgressBlocked, PrivacyError
from zagent.privacy_client import GatewayPrivacy, PrivacyClient


def configured_gateway(
    mode: str | None = None, *, egress_check=None, protect_response=None
) -> LlmGateway:
    mode = mode or os.environ.get("ZAGENT_LLM_MODE", "replay")
    routes = {
        name: ModelRoute.model_validate(route)
        for name, route in json.loads(os.environ.get("ZAGENT_MODEL_ROUTES") or "{}").items()
    } or {"default": ModelRoute(model=os.environ.get("ZAGENT_MODEL") or DEFAULT_MODEL)}
    if os.environ.get("ZAGENT_PRIVACY_URL"):
        privacy = GatewayPrivacy(PrivacyClient.configured("gateway"))
        egress_check = privacy.check
        protect_response = privacy.protect_response
    elif egress_check is None:

        def unconfigured(_request):
            raise PrivacyError("Configure the privacy service before model access")

        egress_check = unconfigured
    return LlmGateway(
        Path(os.environ.get("ZAGENT_CASSETTE_DIR", str(files("zagent").joinpath("cassettes")))),
        mode=mode,
        routes=routes,
        egress_check=egress_check,
        protect_response=protect_response,
        audit_path=Path(
            os.environ.get(
                "ZAGENT_GATEWAY_AUDIT",
                str(
                    Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
                    / "zagent/gateway-audit.sqlite3"
                ),
            )
        ),
    )


def create_gateway_app(gateway: LlmGateway | None = None) -> FastAPI:
    gateway = gateway or configured_gateway()
    app = FastAPI(title="Zagent model gateway")
    from zagent.telemetry import configure_telemetry

    configure_telemetry("zagent-llm-gateway", app)

    @app.exception_handler(PrivacyError)
    async def privacy_error(_request: Request, error: PrivacyError):
        return JSONResponse(
            status_code=502,
            content={
                "code": "egress_identifier"
                if isinstance(error, EgressBlocked)
                else "privacy_unavailable",
                "detail": str(error),
            },
        )

    @app.exception_handler(GatewayError)
    async def gateway_error(_request: Request, error: GatewayError):
        return JSONResponse(status_code=502, content={"detail": str(error)})

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": gateway.mode}

    @app.post("/complete", response_model=Completion)
    async def complete(request: CompletionRequest):
        return await gateway.complete(request)

    @app.get("/sessions/{session_id}/model-requests")
    async def model_requests(session_id: str):
        return await asyncio.to_thread(gateway.requests_for_session, session_id)

    return app


app = create_gateway_app()
