"""Provider-agnostic LLM interface."""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    messages: list[ChatMessage]
    # JSON schema for structured output. Providers that can't honour it fall
    # back to prompt-only JSON; callers always validate the result themselves.
    json_schema: dict[str, Any] | None = None
    schema_name: str = "response"
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    attempts: int
    structured: bool
    usage: dict[str, int] = field(default_factory=dict)


class LLMError(Exception):
    """Base error. ``code`` is safe to persist and show to learners."""

    code = "provider_error"
    retryable = False

    def __init__(self, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = attempts


class ProviderNotConfigured(LLMError):
    code = "provider_not_configured"


class ProviderUnavailable(LLMError):
    code = "provider_unavailable"
    retryable = True


class ProviderTimeout(LLMError):
    code = "provider_timeout"
    retryable = True


class ProviderRateLimited(LLMError):
    code = "provider_rate_limited"
    retryable = True


class ProviderRejected(LLMError):
    """Auth failure, unknown model, bad request: retrying won't help."""

    code = "provider_rejected"


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    async def check(self) -> bool:
        """Cheap reachability check for status pages. Never raises."""
        ...

    async def aclose(self) -> None: ...
