"""Deterministic provider for tests: replays scripted responses in order."""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.llm.base import CompletionRequest, CompletionResult, LLMError

Script = str | LLMError | Callable[[CompletionRequest], str]


@dataclass
class FakeProvider:
    responses: list[Script] = field(default_factory=list)
    name: str = "fake"
    model: str = "fake-model"
    requests: list[CompletionRequest] = field(default_factory=list)

    def queue(self, *items: Script) -> None:
        self.responses.extend(items)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("FakeProvider has no scripted response left")
        item = self.responses.pop(0)
        if isinstance(item, LLMError):
            raise item
        text = item(request) if callable(item) else item
        return CompletionResult(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=1,
            attempts=1,
            structured=request.json_schema is not None,
        )

    async def check(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
