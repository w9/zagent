import asyncio
import fcntl
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

from zagent.llm import CompletionRequest, GatewayError, ModelRoute, canonical_json


class BudgetExceeded(GatewayError):
    pass


class ProviderBudget:
    def __init__(self, path: Path, *, dollars: float, prices: dict[str, dict], max_calls=500):
        if not 0 < dollars <= 2 or not 1 <= max_calls <= 500:
            raise ValueError("Evaluation budget must be positive, at most $2 and 500 calls")
        self.path, self.limit, self.prices, self.max_calls = (
            path,
            Decimal(str(dollars)),
            prices,
            max_calls,
        )

    async def reserve(self, request: CompletionRequest, route: ModelRoute) -> None:
        if route.provider != "openrouter" or route.model not in self.prices:
            raise BudgetExceeded("Model route is not in the approved evaluation budget")
        price = self.prices[route.model]
        input_bytes = len(canonical_json(request.model_dump()).encode()) + 1024
        bound = Decimal("2") * (
            input_bytes * Decimal(str(price["prompt"]))
            + request.max_tokens * Decimal(str(price["completion"]))
        )
        await asyncio.to_thread(
            self._reserve,
            route.model,
            bound,
            hashlib.sha256(
                canonical_json(request.model_dump(exclude={"metadata"})).encode()
            ).hexdigest(),
        )

    def _reserve(self, model, bound, digest):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "r+") as output:
            fcntl.flock(output, fcntl.LOCK_EX)
            raw = output.read()
            state = (
                json.loads(raw)
                if raw
                else {"reserved_usd": "0", "calls": [], "limit_usd": str(self.limit)}
            )
            total = Decimal(state["reserved_usd"]) + bound
            if Decimal(state["limit_usd"]) != self.limit:
                raise BudgetExceeded("Existing budget ledger has a different approved limit")
            if total > self.limit or len(state["calls"]) >= self.max_calls:
                raise BudgetExceeded(
                    "Approved evaluation budget exhausted; no provider call was made"
                )
            state["reserved_usd"] = str(total)
            state["calls"].append(
                {"model": model, "request_hash": digest, "reserved_usd": str(bound)}
            )
            output.seek(0)
            output.truncate()
            json.dump(state, output)
            output.flush()
            os.fsync(output.fileno())
