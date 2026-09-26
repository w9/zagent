import asyncio
import hashlib
import inspect
import json
import os
import sqlite3
import stat
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from zagent.privacy import EgressBlocked

DEFAULT_MODEL = "openai/gpt-6-luna"
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
    metadata: dict[str, str] = Field(default_factory=dict)
    sample: int | None = Field(default=None, ge=0, le=10000)
    tool_choice: Literal["required"] | None = None
    reasoning: Literal["disabled"] | None = None


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


def usage_summary(usage: dict) -> dict[str, int | float]:
    summary = {
        name: value
        for name, value in usage.items()
        if name
        in {"prompt_tokens", "completion_tokens", "total_tokens", "cost", "reasoning_tokens"}
        and type(value) in {int, float}
    }
    details = usage.get("completion_tokens_details", {})
    if isinstance(details, dict) and type(details.get("reasoning_tokens")) in {int, float}:
        summary["reasoning_tokens"] = details["reasoning_tokens"]
    return summary


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalized_request(request: CompletionRequest, route: ModelRoute) -> dict[str, Any]:
    body = request.model_dump(exclude={"metadata", "sample"}, exclude_none=True)
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
        egress_check: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        audit_path: Path | None = None,
        protect_response: Callable[[CompletionRequest, Completion], Awaitable[Completion]]
        | None = None,
        before_provider: Callable[[CompletionRequest, ModelRoute], Awaitable[None]] | None = None,
    ):
        if mode not in {"replay", "record", "live"}:
            raise ValueError("Gateway mode must be replay, record, or live")
        from zagent.faults import configured

        if configured() and mode != "replay":
            raise ValueError("Mutation tests cannot enable model provider access")
        self.cassette_dir = cassette_dir
        self.mode = mode
        self.routes = routes if routes is not None else {"default": ModelRoute()}
        self.transport = transport
        self.egress_check = egress_check
        self.audit_path = audit_path
        self.protect_response = protect_response
        self.before_provider = before_provider
        self.record_missing = False
        self.record_locks: dict[str, asyncio.Lock] = {}

    async def complete(self, request: CompletionRequest) -> Completion:
        entry = {
            "request_id": str(uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "mode": self.mode,
            "purpose": request.metadata.get("purpose", "agent")[:80],
            "session_id": request.metadata.get("session_id", "")[:100],
            "conversation_turn_id": request.metadata.get("conversation_turn_id", "")[:100],
            "scope_hash": request.metadata.get("scope_hash", "")[:64],
            "sample": request.sample,
            "provider_calls": 0,
            "outcome": "failed",
        }
        try:
            completion = await self._complete(request, entry)
            entry["outcome"] = "completed"
            entry["usage"] = completion.usage
            entry.setdefault("finish_reason", completion.finish_reason)
            return completion
        except BaseException as error:
            entry["error_type"] = type(error).__name__
            if isinstance(error, EgressBlocked):
                entry["outcome"] = "blocked"
                entry["alert"] = "egress_identifier"
            if (
                self.mode == "record"
                and isinstance(error, GatewayError)
                and entry["provider_calls"]
            ):
                await self._record_response(
                    request,
                    {
                        "gateway_error": str(error),
                        **{key: entry[key] for key in ("finish_reason", "usage") if key in entry},
                    },
                )
            raise
        finally:
            if self.audit_path is not None:
                await asyncio.to_thread(self._audit, entry)

    def _audit(self, entry: dict) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        model_request = entry.pop("model_request", None)
        with sqlite3.connect(self.audit_path, timeout=30) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS gateway_audit "
                "(request_id TEXT PRIMARY KEY, conversation_turn_id TEXT, entry TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS gateway_audit_turn "
                "ON gateway_audit (conversation_turn_id)"
            )
            connection.execute(
                "INSERT INTO gateway_audit VALUES (?, ?, ?)",
                (entry["request_id"], entry["conversation_turn_id"], canonical_json(entry)),
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS model_requests "
                "(request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                "conversation_turn_id TEXT NOT NULL, body TEXT NOT NULL)"
            )
            if model_request is not None:
                connection.execute(
                    "INSERT INTO model_requests VALUES (?, ?, ?, ?)",
                    (
                        entry["request_id"],
                        entry["session_id"],
                        entry["conversation_turn_id"],
                        canonical_json(model_request),
                    ),
                )

    def requests_for_session(self, session_id: str) -> list[dict]:
        if self.audit_path is None or not self.audit_path.exists():
            return []
        with sqlite3.connect(self.audit_path, timeout=30) as connection:
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'model_requests'"
            ).fetchone()
            if not exists:
                return []
            rows = connection.execute(
                "SELECT requests.request_id, requests.conversation_turn_id, "
                "requests.body, audit.entry "
                "FROM model_requests AS requests JOIN gateway_audit AS audit USING (request_id) "
                "WHERE requests.session_id = ? ORDER BY requests.rowid",
                (session_id,),
            )
            return [
                {
                    "request_id": row[0],
                    "conversation_turn_id": row[1],
                    "request": json.loads(row[2]),
                    "audit": json.loads(row[3]),
                }
                for row in rows
            ]

    def audit_for_turn(self, conversation_turn_id: str) -> list[dict]:
        if self.audit_path is None or not self.audit_path.exists():
            return []
        with sqlite3.connect(self.audit_path, timeout=30) as connection:
            return [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT entry FROM gateway_audit WHERE conversation_turn_id = ? ORDER BY rowid",
                    (conversation_turn_id,),
                )
            ]

    async def _complete(self, request: CompletionRequest, audit: dict) -> Completion:
        route = self.routes.get(request.route)
        if route is None:
            raise GatewayError(f"Unknown model route: {request.route}")
        normalized = normalized_request(request, route)
        digest = request_hash(request, route)
        audit.update(
            {
                "request_hash": digest,
                "prompt_hash": normalized["prompt_hash"],
                "provider": route.provider,
                "model": route.model,
            }
        )
        path = self.cassette_dir / f"{digest}.json"
        body = {
            "model": route.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.tools:
            body["tools"] = request.tools
        if request.tool_choice is not None:
            body["tool_choice"] = request.tool_choice
        if request.reasoning == "disabled" and route.provider == "openrouter":
            body["reasoning"] = {"enabled": False}
        if self.egress_check is not None:
            checked = self.egress_check(body)
            if inspect.isawaitable(checked):
                await checked
        audit["model_request"] = body
        recorded = None
        if self.mode == "record" and self.record_missing:
            async with self.record_locks.setdefault(digest, asyncio.Lock()):
                try:
                    recorded = json.loads(await asyncio.to_thread(path.read_text))
                except FileNotFoundError:
                    recorded = None
                if recorded is not None:
                    existing = (
                        recorded.get("response")
                        if request.sample is None
                        else recorded.get("samples", {}).get(str(request.sample))
                    )
                    if existing is None:
                        recorded = None
        if self.mode == "replay" or recorded is not None:
            try:
                cassette = recorded or json.loads(await asyncio.to_thread(path.read_text))
            except FileNotFoundError:
                raise CassetteMiss(
                    f"Cassette miss: {digest}. Re-record with ZAGENT_LLM_MODE=record "
                    "and a provider key; replay never calls the provider."
                ) from None
            if (
                cassette.get("version") not in {1, 2}
                or cassette.get("request_hash") != digest
                or cassette.get("request") != normalized
            ):
                raise GatewayError(f"Invalid cassette: {digest}; re-record it.")
            response = (
                cassette.get("response")
                if request.sample is None
                else cassette.get("samples", {}).get(str(request.sample))
            )
            if response is None:
                raise CassetteMiss(
                    f"Cassette miss: {digest}, sample {request.sample}. "
                    "Re-record with ZAGENT_LLM_MODE=record; replay never calls the provider."
                )
            if "gateway_error" in response:
                if "finish_reason" in response:
                    audit["finish_reason"] = response["finish_reason"]
                if "usage" in response:
                    audit["usage"] = usage_summary(response["usage"])
                raise GatewayError(response["gateway_error"])
            return Completion.model_validate(response)

        endpoint, key_name = PROVIDERS[route.provider]
        key = await asyncio.to_thread(provider_key, key_name)
        if self.before_provider is not None:
            await self.before_provider(request, route)
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=60) as client:
                audit["provider_calls"] = 1
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {key}"},
                    json=body,
                )
                if response.is_error:
                    raise GatewayError(f"Model provider returned HTTP {response.status_code}")
                data = response.json()
                choice = data["choices"][0]
                finish_reason = choice.get("finish_reason") or "stop"
                usage = usage_summary(data.get("usage", {}))
                audit["finish_reason"] = (
                    finish_reason
                    if finish_reason
                    in {"stop", "length", "tool_calls", "function_call", "content_filter", "error"}
                    else "unknown"
                )
                audit["usage"] = usage
                if finish_reason in {"length", "content_filter"}:
                    raise GatewayError(f"Model completion interrupted: {finish_reason}")
                completion = Completion(
                    message=AssistantMessage.model_validate(choice["message"]),
                    finish_reason=finish_reason,
                    usage=usage,
                )
        except httpx.HTTPError:
            raise GatewayError(
                "Model provider request failed; check gateway connectivity"
            ) from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise GatewayError("Model provider returned an invalid completion") from None
        if self.protect_response is not None:
            completion = await self.protect_response(request, completion)
        if self.mode == "record":
            await self._record_response(request, completion.model_dump())
        return completion

    async def _record_response(self, request: CompletionRequest, response: dict) -> None:
        route = self.routes[request.route]
        normalized = normalized_request(request, route)
        digest = request_hash(request, route)
        path = self.cassette_dir / f"{digest}.json"
        cassette = {
            "version": 1,
            "request_hash": digest,
            "request": normalized,
            "response": response,
        }
        async with self.record_locks.setdefault(digest, asyncio.Lock()):
            try:
                previous = json.loads(await asyncio.to_thread(path.read_text))
            except FileNotFoundError:
                previous = None
            if previous is not None:
                if previous.get("request") != normalized:
                    raise GatewayError(f"Invalid cassette: {digest}; cannot merge samples")
                cassette = previous
            if request.sample is None:
                cassette["response"] = response
            else:
                if previous is None:
                    cassette.pop("response")
                cassette["version"] = 2
                cassette.setdefault("samples", {})[str(request.sample)] = response
            await asyncio.to_thread(self._write_cassette, path, cassette)

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
                data = response.json()
                if data.get("code") == "egress_identifier":
                    raise EgressBlocked("Privacy tripwire blocked the model request.")
                detail = data.get("detail", "Model gateway failed")
                raise GatewayError(str(detail))
            return Completion.model_validate(response.json())
        except httpx.HTTPError:
            raise GatewayError("Model gateway is unavailable") from None
