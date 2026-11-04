"""Process-wide spending guard for the LLM provider.

Every model call in FORGE goes through the provider built in ``factory``, so a
cap here bounds total spend even when per-learner limits are bypassed (for
example by creating many anonymous learners). Over budget, calls fail with
``ProviderRateLimited`` before reaching the provider; every caller already
treats that as "ungraded, retry later", never as a score.

The window is per API process. Run one API process, or divide the budget by the
number of processes.
"""

import asyncio
import time
from collections import deque

from app.llm.base import CompletionRequest, CompletionResult, ProviderRateLimited


class BudgetedProvider:
    def __init__(self, inner, max_calls_per_hour: int, clock=time.monotonic) -> None:
        self.inner = inner
        self.name = inner.name
        self.model = inner.model
        self.max_calls = max_calls_per_hour
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    def used(self) -> int:
        cutoff = self._clock() - 3600
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        return len(self._calls)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        async with self._lock:
            if self.used() >= self.max_calls:
                raise ProviderRateLimited("The server's hourly AI budget is used up", attempts=0)
            self._calls.append(self._clock())
        return await self.inner.complete(request)

    async def check(self) -> bool:
        return await self.inner.check()

    async def aclose(self) -> None:
        await self.inner.aclose()
