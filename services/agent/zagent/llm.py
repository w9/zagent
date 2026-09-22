import asyncio
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
}


class ModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["openrouter", "openai"] = "openrouter"
    model: str = DEFAULT_MODEL


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: str = "default"
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=256)
    tools: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_tokens: int = Field(default=1200, ge=1, le=4096)
    metadata: dict[str, str] = Field(default_factory=dict, exclude=True)


class FunctionCall(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    arguments: str = Field(max_length=16384)


class ToolCall(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    type: Literal["function"] = "function"
    function: FunctionCall


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str | None = Field(default=None, max_length=32768)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=16)

    def as_message(self) -> dict[str, Any]:
        message = self.model_dump(exclude_none=True)
        if not self.tool_calls:
            message.pop("tool_calls")
        return message


class Completion(BaseModel):
    message: AssistantMessage
    finish_reason: str = "stop"
    usage: dict[str, int | float] = Field(default_factory=dict)


class Completer(Protocol):
    async def complete(self, request: CompletionRequest) -> Completion: ...


class GatewayError(RuntimeError):
    pass


class CassetteMiss(GatewayError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalized_request(request: CompletionRequest, route: ModelRoute) -> dict[str, Any]:
    body = request.model_dump()
    call_ids: dict[str, str] = {}
    messages = []
    for original in body["messages"]:
        message = {
            key: value
            for key, value in original.items()
            if key in {"role", "content", "name", "tool_calls", "tool_call_id"}
        }
        if isinstance(message.get("content"), str):
            message["content"] = message["content"].replace("\r\n", "\n").strip()
        for call in message.get("tool_calls", []):
            original_id = call["id"]
            call["id"] = call_ids.setdefault(original_id, f"call_{len(call_ids) + 1}")
            arguments = call["function"]["arguments"]
            try:
                call["function"]["arguments"] = canonical_json(json.loads(arguments))
            except (ValueError, TypeError):
                pass
        if "tool_call_id" in message:
            message["tool_call_id"] = call_ids.get(message["tool_call_id"], message["tool_call_id"])
        messages.append(message)
    body["messages"] = messages
    body["provider"] = route.provider
    body["model"] = route.model
    body["prompt_hash"] = hashlib.sha256(
        canonical_json([item for item in messages if item["role"] == "system"]).encode()
    ).hexdigest()
    return body


def request_hash(request: CompletionRequest, route: ModelRoute) -> str:
    return hashlib.sha256(canonical_json(normalized_request(request, route)).encode()).hexdigest()


def provider_key(key_name: str) -> str:
    if key := os.environ.get(key_name):
        return key
    configured = os.environ.get(f"{key_name}_FILE")
    if not configured and key_name == "OPENROUTER_API_KEY":
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        configured = str(config_home / "zagent" / "openrouter.key")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            permissions = path.stat()
            if stat.S_IMODE(permissions.st_mode) & 0o077:
                raise GatewayError("Provider key file must be owner-only (chmod 600)")
            if permissions.st_size > 4096:
                raise GatewayError("Invalid provider key file")
            if key := path.read_text().strip():
                return key
    raise GatewayError(f"{key_name} or {key_name}_FILE is required for provider access")


class LlmGateway:
    def __init__(
        self,
        cassette_dir: Path,
        *,
        mode: Literal["replay", "record", "live"] = "replay",
        routes: dict[str, ModelRoute] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        egress_check: Callable[[dict[str, Any]], None] | None = None,
    ):
        if mode not in {"replay", "record", "live"}:
            raise ValueError("Gateway mode must be replay, record, or live")
        self.cassette_dir = cassette_dir
        self.mode = mode
        self.routes = routes if routes is not None else {"default": ModelRoute()}
        self.transport = transport
        self.egress_check = egress_check

    async def complete(self, request: CompletionRequest) -> Completion:
        route = self.routes.get(request.route)
        if route is None:
            raise GatewayError(f"Unknown model route: {request.route}")
        normalized = normalized_request(request, route)
        digest = request_hash(request, route)
        path = self.cassette_dir / f"{digest}.json"
        if self.mode == "replay":
            try:
                cassette = json.loads(await asyncio.to_thread(path.read_text))
            except FileNotFoundError:
                raise CassetteMiss(
                    f"Cassette miss: {digest}. Re-record with ZAGENT_LLM_MODE=record "
                    "and a provider key; replay never calls the provider."
                ) from None
            if (
                cassette.get("version") != 1
                or cassette.get("request_hash") != digest
                or cassette.get("request") != normalized
            ):
                raise GatewayError(f"Invalid cassette: {digest}; re-record it.")
            return Completion.model_validate(cassette["response"])

        if self.egress_check is not None:
            self.egress_check(normalized)
        endpoint, key_name = PROVIDERS[route.provider]
        key = await asyncio.to_thread(provider_key, key_name)
        body = {
            "model": route.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            body["tools"] = request.tools
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=60) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
                if response.is_error:
                    raise GatewayError(f"Model provider returned HTTP {response.status_code}")
                data = response.json()
                choice = data["choices"][0]
                completion = Completion(
                    message=AssistantMessage.model_validate(choice["message"]),
                    finish_reason=choice.get("finish_reason") or "stop",
                    usage={
                        name: value
                        for name, value in data.get("usage", {}).items()
                        if name in {"prompt_tokens", "completion_tokens", "total_tokens", "cost"}
                        and isinstance(value, (int, float))
                    },
                )
        except httpx.HTTPError:
            raise GatewayError(
                "Model provider request failed; check gateway connectivity"
            ) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise GatewayError("Model provider returned an invalid completion") from None
        if completion.finish_reason in {"length", "content_filter"}:
            raise GatewayError(f"Model completion interrupted: {completion.finish_reason}")
        if self.mode == "record":
            cassette = {
                "version": 1,
                "request_hash": digest,
                "request": normalized,
                "response": completion.model_dump(),
            }
            await asyncio.to_thread(self._write_cassette, path, cassette)
        return completion

    @staticmethod
    def _write_cassette(path: Path, cassette: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w") as output:
                output.write(json.dumps(cassette, indent=2, sort_keys=True) + "\n")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class GatewayClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    async def complete(self, request: CompletionRequest) -> Completion:
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(f"{self.url}/complete", json=request.model_dump())
            if response.is_error:
                detail = response.json().get("detail", "Model gateway failed")
                raise GatewayError(str(detail))
            return Completion.model_validate(response.json())
        except httpx.HTTPError:
            raise GatewayError("Model gateway is unavailable") from None
