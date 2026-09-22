import asyncio
import os
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import httpx

from zagent.privacy import Binding, EgressTripwire, PrivacyError, Raw, Tokenized, TripwireManifest


class Tokenizer(Protocol):
    async def tokenize(
        self,
        session_id: UUID,
        raw: Raw[Any],
        *,
        path: str,
        schema: dict | None = None,
        external: bool = False,
    ) -> Tokenized[Any]: ...


class Resolver(Tokenizer, Protocol):
    async def resolve(
        self, session_id: UUID, value: Tokenized[Any], *, strict: bool = False
    ) -> Raw[Any]: ...

    async def bindings(self, session_id: UUID) -> list[Binding]: ...


class PrivacyClient:
    def __init__(
        self, url: str, capability: str, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.url = url.rstrip("/")
        self.capability = capability
        self.transport = transport

    @classmethod
    def configured(cls, role: str = "tokenize") -> "PrivacyClient":
        path = os.environ.get("ZAGENT_PRIVACY_CAPABILITY_FILE", f"/run/privacy/{role}.key")
        return cls(
            os.environ.get("ZAGENT_PRIVACY_URL", "http://privacy:8003"),
            Path(path).read_text().strip(),
        )

    async def request(self, path: str, body: dict) -> Any:
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30) as client:
                response = await client.post(
                    self.url + path,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self.capability}",
                    },
                )
            if response.status_code == 403:
                raise PrivacyError("Privacy capability does not permit this operation")
            if response.is_error:
                raise PrivacyError("Privacy operation failed")
            return response.json()
        except httpx.HTTPError:
            raise PrivacyError("Privacy service is unavailable") from None

    async def tokenize(
        self,
        session_id: UUID,
        raw: Raw[Any],
        *,
        path: str,
        schema: dict | None = None,
        external: bool = False,
    ) -> Tokenized[Any]:
        if not isinstance(raw, Raw):
            raise TypeError("Tokenization requires Raw input")
        result = await self.request(
            "/tokenize",
            {
                "session_id": str(session_id),
                "value": raw.value,
                "path": path,
                "schema": schema,
                "external": external,
            },
        )
        return Tokenized(value=result["value"])

    async def resolve(
        self, session_id: UUID, value: Tokenized[Any], *, strict: bool = False
    ) -> Raw[Any]:
        if not isinstance(value, Tokenized):
            raise TypeError("Resolution requires Tokenized input")
        result = await self.request(
            "/resolve",
            {
                "session_id": str(session_id),
                "value": value.value,
                "strict": strict,
            },
        )
        return Raw(value=result["value"])

    async def bindings(self, session_id: UUID) -> list[Binding]:
        result = await self.request("/bindings", {"session_id": str(session_id)})
        return [Binding.model_validate(item) for item in result]

    async def tripwire(self) -> tuple[bytes, TripwireManifest]:
        result = await self.request("/tripwire", {})
        return bytes.fromhex(result["key"]), TripwireManifest.model_validate(result["manifest"])


class GatewayPrivacy:
    def __init__(self, client: PrivacyClient):
        self.client = client
        self.checker: EgressTripwire | None = None
        self.manifest: TripwireManifest | None = None

    async def check(self, request: dict) -> None:
        key, manifest = await self.client.tripwire()
        if self.checker is None or manifest != self.manifest:
            self.checker = EgressTripwire(key, manifest)
            self.manifest = manifest
        await asyncio.to_thread(self.checker, request)

    async def protect_response(self, request, completion):
        from zagent.llm import AssistantMessage

        session_id = request.metadata.get("session_id")
        if not session_id:
            raise PrivacyError("Model requests must carry a privacy session")
        protected = await self.client.tokenize(
            UUID(session_id),
            Raw(value=completion.message.as_message()),
            path="assistant_output",
        )
        return completion.model_copy(
            update={"message": AssistantMessage.model_validate(protected.value)}
        )
