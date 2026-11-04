"""OpenAI-compatible chat completions client.

Works with local Ollama (``http://127.0.0.1:11434/v1``), Ollama Cloud
(``https://ollama.com/v1`` with an API key) and other compatible servers.
"""

import asyncio
import random
import time
from typing import Any

import httpx

from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    LLMError,
    ProviderRateLimited,
    ProviderRejected,
    ProviderTimeout,
    ProviderUnavailable,
)

StructuredMode = str  # "auto" | "json_schema" | "json_object" | "none"


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        max_retries: int,
        retry_base_delay: float,
        retry_max_delay: float,
        max_output_tokens: int,
        temperature: float,
        structured_output: StructuredMode,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._max_retries = max_retries
        self._base_delay = retry_base_delay
        self._max_delay = retry_max_delay
        self._max_tokens = max_output_tokens
        self._temperature = temperature
        self._structured = structured_output
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds)),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    CHECK_TTL_SECONDS = 30.0

    async def check(self) -> bool:
        """Cached for 30 s: status pages call this on every view, and the provider is remote."""
        now = time.monotonic()
        cached = getattr(self, "_check_cache", None)
        if cached and now - cached[0] < self.CHECK_TTL_SECONDS:
            return cached[1]
        try:
            res = await self._client.get("models", timeout=3.0)
            ok = res.status_code < 500 and res.status_code not in (401, 403)
        except httpx.HTTPError:
            ok = False
        self._check_cache = (now, ok)
        return ok

    def _response_format(self, request: CompletionRequest) -> dict[str, Any] | None:
        if request.json_schema is None or self._structured == "none":
            return None
        if self._structured == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": request.schema_name, "schema": request.json_schema},
        }

    def _backoff(self, attempt: int) -> float:
        # Exponential backoff with full jitter, bounded by retry_max_delay.
        ceiling = min(self._max_delay, self._base_delay * (2**attempt))
        return random.uniform(0, ceiling)

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        try:
            return await self._client.post("chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("The model provider timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("The model provider could not be reached") from exc

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        response_format = self._response_format(request)
        started = time.monotonic()
        attempts = 0
        last_error: LLMError | None = None

        while attempts <= self._max_retries:
            attempts += 1
            body: dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "temperature": request.temperature
                if request.temperature is not None
                else self._temperature,
                "max_tokens": request.max_tokens or self._max_tokens,
                "stream": False,
            }
            if response_format is not None:
                body["response_format"] = response_format
            try:
                res = await self._post(body)
                if res.status_code == 400 and response_format and self._structured == "auto":
                    # Provider/model doesn't support structured output: degrade
                    # to prompt-only JSON (still validated by the caller).
                    response_format = None
                    attempts -= 1
                    continue
                if res.status_code == 429:
                    raise ProviderRateLimited("The model provider is rate limiting requests")
                if res.status_code >= 500:
                    raise ProviderUnavailable(f"The model provider returned {res.status_code}")
                if res.status_code >= 400:
                    raise ProviderRejected(_rejection_message(res))
                payload = res.json()
                text = payload["choices"][0]["message"]["content"] or ""
                usage = {
                    k: int(v)
                    for k, v in (payload.get("usage") or {}).items()
                    if isinstance(v, int)
                }
                return CompletionResult(
                    text=text,
                    provider=self.name,
                    model=str(payload.get("model") or self.model),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    attempts=attempts,
                    structured=response_format is not None,
                    usage=usage,
                )
            except LLMError as exc:
                exc.attempts = attempts
                last_error = exc
                if not exc.retryable or attempts > self._max_retries:
                    raise
                await asyncio.sleep(self._backoff(attempts - 1))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ProviderRejected(
                    "The model provider returned an unexpected response", attempts=attempts
                ) from exc

        assert last_error is not None  # loop always returns or raises
        raise last_error


def _rejection_message(res: httpx.Response) -> str:
    if res.status_code in (401, 403):
        return "The model provider rejected the credentials"
    if res.status_code == 404:
        return "The configured model or endpoint was not found"
    return f"The model provider rejected the request ({res.status_code})"
