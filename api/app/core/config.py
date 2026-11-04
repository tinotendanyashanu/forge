"""Application settings, loaded from environment variables (prefix ``FORGE_``)."""

from functools import lru_cache

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FORGE API"
    version: str = "1.0.0"
    environment: str = "development"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    # SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pass@host:5432/forge.
    # Server-side only; never sent to clients.
    database_url: str | None = None
    # Database pytest may drop and recreate. Must differ from database_url.
    test_database_url: str | None = None
    # Questions per assessment session when the client doesn't specify one.
    default_session_length: int = Field(default=5, ge=1, le=20)

    # ---- LLM provider (server-side only; never sent to clients) -------------
    # disabled: interviews run but answers are saved ungraded.
    # ollama: local Ollama OpenAI-compatible API (default base URL below).
    # openai_compatible: any OpenAI-compatible endpoint, e.g. Ollama Cloud.
    llm_provider: Literal["disabled", "ollama", "openai_compatible"] = "disabled"
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_retry_base_delay: float = Field(default=0.5, ge=0, le=10)
    llm_retry_max_delay: float = Field(default=4.0, ge=0, le=60)
    llm_max_output_tokens: int = Field(default=1200, ge=128, le=8192)
    llm_temperature: float = Field(default=0.1, ge=0, le=1)
    # auto: request JSON-schema structured output, fall back to prompt-only JSON
    # if the provider rejects it. none: never send response_format.
    llm_structured_output: Literal["auto", "json_schema", "json_object", "none"] = "auto"
    llm_max_repair_attempts: int = Field(default=1, ge=0, le=3)
    # Process-wide cap on model calls per hour, across all learners and modules.
    # Bounds spend even if per-learner limits are bypassed. 0 disables the cap.
    llm_max_calls_per_hour: int = Field(default=600, ge=0, le=100_000)
    # Per-learner AI interview evaluations per hour (answers and retries).
    interview_llm_calls_per_hour: int = Field(default=60, ge=1, le=1000)

    # ---- Coding lab execution (Milestone 5) ----------------------------------
    # disabled: no code runs; jobs are refused.
    # mock: a clearly labelled runner that executes NOTHING (for UI and flow
    #       testing); results are "not executed" and never count as evidence.
    # docker: hardened per-job container, run only by the separate worker.
    sandbox_backend: Literal["disabled", "mock", "docker"] = "disabled"
    # Containers alone are not adequate isolation for hostile multi-user code.
    # The docker backend refuses to run unless this is explicitly true, which
    # acknowledges a local, single-user deployment.
    sandbox_allow_container_isolation: bool = False
    # Built from api/sandbox/python-lab (FastAPI + private PostgreSQL).
    sandbox_python_image: str = "forge-sandbox-python:2"
    sandbox_node_image: str = "node:24-alpine"
    sandbox_max_output_bytes: int = Field(default=65_536, ge=1024, le=1_048_576)
    sandbox_max_time_ms: int = Field(default=10_000, ge=500, le=60_000)
    sandbox_max_memory_mb: int = Field(default=256, ge=32, le=1024)
    sandbox_pids_limit: int = Field(default=64, ge=8, le=512)
    worker_poll_seconds: float = Field(default=1.0, gt=0, le=30)
    job_lease_seconds: int = Field(default=90, ge=10, le=900)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    coding_max_code_bytes: int = Field(default=65_536, ge=1024, le=262_144)
    coding_runs_per_minute: int = Field(default=10, ge=1, le=120)
    coding_submits_per_hour: int = Field(default=30, ge=1, le=600)
    coding_max_active_jobs: int = Field(default=2, ge=1, le=20)

    # ---- System design lab (Milestone 6) ---------------------------------------
    design_llm_calls_per_hour: int = Field(default=60, ge=1, le=1000)

    # ---- FORGE OPS (Milestone 7) ------------------------------------------------
    ops_llm_calls_per_hour: int = Field(default=60, ge=1, le=1000)

    # ---- FORGE Career (Milestone 8) ---------------------------------------------
    career_llm_calls_per_hour: int = Field(default=40, ge=1, le=1000)

    # ---- FORGE Workspace (Milestone 9) -----------------------------------------
    # Per-learner AI calls per hour (code reviews and collaboration exercises).
    workspace_llm_calls_per_hour: int = Field(default=30, ge=1, le=1000)

    # ---- HTTP ------------------------------------------------------------------
    max_request_bytes: int = Field(default=2_000_000, ge=65_536, le=50_000_000)

    # ---- Access ---------------------------------------------------------------
    # No authentication exists, so learner-scoped routes only accept requests
    # from these client hosts (the Next.js server runs on the same machine).
    local_only: bool = True
    local_only_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "::1", "localhost"]
    )

    def require_database_url(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "FORGE_DATABASE_URL is not set. Copy api/.env.example to api/.env "
                "and start Postgres with `docker compose up -d`."
            )
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
