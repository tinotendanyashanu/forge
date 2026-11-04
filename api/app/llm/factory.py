from app.core.config import Settings
from app.llm.base import CompletionRequest, CompletionResult, ProviderNotConfigured
from app.llm.budget import BudgetedProvider
from app.llm.openai_compatible import OpenAICompatibleProvider

OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"


class DisabledProvider:
    """Used when no provider is configured. Every call fails clearly."""

    name = "disabled"
    model = "none"

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        raise ProviderNotConfigured("No LLM provider is configured")

    async def check(self) -> bool:
        return False

    async def aclose(self) -> None:
        return None


def build_provider(settings: Settings):  # -> LLMProvider
    if settings.llm_provider == "disabled" or not settings.llm_model:
        return DisabledProvider()

    base_url = settings.llm_base_url
    if settings.llm_provider == "ollama":
        base_url = base_url or OLLAMA_DEFAULT_BASE_URL
    if not base_url:
        return DisabledProvider()

    provider = OpenAICompatibleProvider(
        name=settings.llm_provider,
        base_url=base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key.get_secret_value() if settings.llm_api_key else None,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        retry_base_delay=settings.llm_retry_base_delay,
        retry_max_delay=settings.llm_retry_max_delay,
        max_output_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        structured_output=settings.llm_structured_output,
    )
    # Global spending cap across every module and learner (0 disables it).
    if settings.llm_max_calls_per_hour > 0:
        return BudgetedProvider(provider, settings.llm_max_calls_per_hour)
    return provider
