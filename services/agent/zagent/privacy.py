import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Callable, Iterable
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from zagent.faults import enabled

IdentifierKind = Literal["PT", "SP", "LB", "LIT"]
TOKEN = re.compile(r"\[(?:PT|SP|LB|LIT)_[1-9][0-9]*\]")
TOKEN_PREFIX = re.compile(
    r"\[(?:(?:P(?:T(?:_[0-9]*)?)?)|S(?:P(?:_[0-9]*)?)?|"
    r"L(?:B(?:_[0-9]*)?|I(?:T(?:_[0-9]*)?)?)?)?$"
)
SITE_MRNS = (
    r"NGC-[0-9]{7}",
    r"LHX/[0-9]{2}/[0-9]{5}",
    r"SQ-[A-Z]{2}-[0-9]{4}",
    r"CV[0-9]{8}",
    r"[0-9]{3}-[0-9]{2}-[0-9]{4}",
)
IDENTIFIER_PATTERNS = {
    "PT": re.compile(
        r"(?<!\w)(?:" + "|".join(SITE_MRNS) + r"|PAT-[A-Z]+-[0-9]{3})(?!\w)", re.IGNORECASE
    ),
    "SP": re.compile(r"(?<!\w)SPC-(?:[A-Z]+-)?[0-9]+(?:-[0-9]+)?(?!\w)", re.IGNORECASE),
    "LB": re.compile(r"(?<!\w)LIB-(?:[A-Z]+-)?[0-9]+(?:-[0-9]+)?(?!\w)", re.IGNORECASE),
}
INGRESS_PATHS = frozenset(
    {
        "user_message",
        "tool_arguments",
        "tool_result",
        "view_spec",
        "assistant_output",
        "draft_updated",
        "job_log",
        "retrieved_document",
        "view_interaction",
    }
)


class Raw[Value](BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: Value


class Tokenized[Value](BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: Value


class Identifier(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    kind: IdentifierKind = "PT"


class Binding(Identifier):
    token: str = Field(pattern=TOKEN.pattern)


class PrivacyError(RuntimeError):
    pass


class EgressBlocked(PrivacyError):
    pass


def normalize_identifier(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return
        if not isinstance(parsed, str):
            yield from string_values(parsed)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_values(item)


class Detector:
    def __init__(self, identifiers: Iterable[Identifier] = ()):
        self.identifiers = {normalize_identifier(item.value): item for item in identifiers}
        for item in self.identifiers.values():
            if TOKEN.search(item.value):
                raise ValueError("The identifier registry collides with reserved privacy tokens")
        values = sorted(self.identifiers, key=lambda value: (-len(value), value))
        self.dictionary = (
            re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(value) for value in values) + r")(?!\w)",
                re.IGNORECASE,
            )
            if values
            else None
        )

    def matches(self, text: str) -> list[tuple[int, int, Identifier]]:
        candidates = []
        if self.dictionary:
            for match in self.dictionary.finditer(text):
                item = self.identifiers[normalize_identifier(match.group())]
                candidates.append(
                    (
                        match.start(),
                        match.end(),
                        Identifier(
                            value=match.group(),
                            kind=item.kind,
                        ),
                    )
                )
        for kind, pattern in IDENTIFIER_PATTERNS.items():
            candidates.extend(
                (match.start(), match.end(), Identifier(value=match.group(), kind=kind))
                for match in pattern.finditer(text)
            )
        found = []
        end = 0
        for start, stop, item in sorted(candidates, key=lambda match: (match[0], -match[1])):
            if start >= end:
                found.append((start, stop, item))
                end = stop
        return found

    def contains(self, value: Any) -> bool:
        return any(self.matches(text) for text in string_values(value))


class SessionTokens:
    def __init__(self, detector: Detector, bindings: Iterable[Binding] = ()):
        self.bindings = list(bindings)
        self.detector = (
            Detector(
                [
                    *detector.identifiers.values(),
                    *(
                        Identifier(value=item.value, kind=item.kind)
                        for item in self.bindings
                        if item.kind != "LIT"
                    ),
                ]
            )
            if self.bindings
            else detector
        )
        self.by_value = {
            (item.kind, normalize_identifier(item.value)): item for item in self.bindings
        }
        self.by_token = {item.token: item for item in self.bindings}

    def bind(self, value: str, kind: IdentifierKind) -> str:
        identity = (kind, normalize_identifier(value))
        if identity in self.by_value:
            return self.by_value[identity].token
        number = 1 + max(
            (int(item.token.rsplit("_", 1)[1][:-1]) for item in self.bindings if item.kind == kind),
            default=0,
        )
        binding = Binding(value=value, kind=kind, token=f"[{kind}_{number}]")
        self.bindings.append(binding)
        self.by_value[identity] = binding
        self.by_token[binding.token] = binding
        if kind != "LIT" and normalize_identifier(value) not in self.detector.identifiers:
            self.detector = Detector(
                [
                    *self.detector.identifiers.values(),
                    Identifier(value=value, kind=kind),
                ]
            )
        return binding.token

    def text(self, value: str, *, external: bool = False) -> str:
        if external:
            value = TOKEN.sub(lambda match: self.bind(match.group(), "LIT"), value)
        pieces = []
        cursor = 0
        for start, stop, identifier in self.detector.matches(value):
            pieces.extend((value[cursor:start], self.bind(identifier.value, identifier.kind)))
            cursor = stop
        pieces.append(value[cursor:])
        return "".join(pieces)

    def tokenize(
        self, raw: Raw[Any], *, path: str, schema: dict | None = None, external: bool = False
    ) -> Tokenized[Any]:
        if not isinstance(raw, Raw):
            raise TypeError("Tokenization requires a Raw boundary value")
        if path not in INGRESS_PATHS:
            raise PrivacyError("Unregistered model-context ingress")
        if enabled("tokenizer_off"):
            return Tokenized(value=raw.value)

        def walk(value: Any, annotation: dict) -> Any:
            if "$ref" in annotation:
                target = schema or {}
                for part in annotation["$ref"].removeprefix("#/").split("/"):
                    target = target.get(part, {})
                annotation = target
            for keyword in ("allOf", "anyOf", "oneOf"):
                for branch in annotation.get(keyword, []):
                    if branch.get("type") in {
                        None,
                        "string" if isinstance(value, str) else "object",
                    }:
                        annotation = {**annotation, **branch}
                        break
            if isinstance(value, str):
                if kind := annotation.get("x-identifier"):
                    if TOKEN.fullmatch(value) and value in self.by_token and not external:
                        return value
                    return self.bind(value, kind)
                try:
                    parsed = json.loads(value)
                except (ValueError, TypeError):
                    parsed = None
                if isinstance(parsed, (dict, list)):
                    protected = walk(parsed, {})
                    if protected != parsed:
                        return json.dumps(protected, ensure_ascii=True, separators=(",", ":"))
                return self.text(value, external=external)
            if isinstance(value, list):
                return [walk(item, annotation.get("items", {})) for item in value]
            if isinstance(value, dict):
                return {
                    self.text(str(key), external=external): walk(
                        item,
                        annotation.get("properties", {}).get(key, {}),
                    )
                    for key, item in value.items()
                }
            return value

        return Tokenized(value=walk(raw.value, schema or {}))

    def resolve(self, value: Tokenized[Any], *, strict: bool = False) -> Raw[Any]:
        if not isinstance(value, Tokenized):
            raise TypeError("Resolution requires a Tokenized boundary value")

        def text(source: str) -> str:
            def replace(match: re.Match) -> str:
                binding = self.by_token.get(match.group())
                if binding:
                    return binding.value
                if strict:
                    raise PrivacyError("Unknown or cross-session identifier token")
                return "[unavailable identifier]"

            return TOKEN.sub(replace, source)

        def walk(source: Any) -> Any:
            if isinstance(source, str):
                return text(source)
            if isinstance(source, list):
                return [walk(item) for item in source]
            if isinstance(source, dict):
                return {text(str(key)): walk(item) for key, item in source.items()}
            return source

        return Raw(value=walk(value.value))


class DisplayHoldback:
    def __init__(self, resolve: Callable[[str], str]):
        self.resolve = resolve
        self.pending = ""

    def feed(self, chunk: str, *, final: bool = False) -> str:
        value = self.pending + chunk
        self.pending = ""
        match = TOKEN_PREFIX.search(value)
        if match:
            self.pending = match.group()
            value = value[: match.start()]
        rendered = self.resolve(value)
        if final and self.pending:
            self.pending = ""
            rendered += "[unavailable identifier]"
        return rendered


class TripwireManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digests: dict[int, list[str]]


class EgressTripwire:
    def __init__(self, key: bytes, manifest: TripwireManifest):
        if len(key) < 32:
            raise ValueError("Tripwire key must have at least 256 bits")
        self.key = key
        self.digests = {length: set(values) for length, values in manifest.digests.items()}
        self.scan = lru_cache(maxsize=2048)(self._scan)

    @staticmethod
    def manifest(key: bytes, identifiers: Iterable[Identifier]) -> TripwireManifest:
        digests: dict[int, set[str]] = {}
        for item in identifiers:
            value = normalize_identifier(item.value)
            digest = hmac.new(key, value.encode(), hashlib.sha256).hexdigest()
            digests.setdefault(len(value), set()).add(digest)
        return TripwireManifest(
            digests={length: sorted(values) for length, values in digests.items()}
        )

    def __call__(self, request: dict[str, Any]) -> None:
        if enabled("tripwire_off"):
            return
        for text in string_values(request):
            self.scan(text)

    def _scan(self, text: str) -> None:
        normalized = normalize_identifier(text)
        if any(pattern.search(normalized) for pattern in IDENTIFIER_PATTERNS.values()):
            raise EgressBlocked("Privacy tripwire blocked an identifier-bearing request")
        for length, digests in self.digests.items():
            for offset in range(max(0, len(normalized) - length + 1)):
                end = offset + length
                candidate = normalized[offset:end]
                digest = hmac.new(self.key, candidate.encode(), hashlib.sha256).hexdigest()
                if digest in digests:
                    raise EgressBlocked("Privacy tripwire blocked an identifier-bearing request")
