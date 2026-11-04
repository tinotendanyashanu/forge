from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.body_limit import BodySizeLimit
from app.api.deps import require_local_access
from app.api.routes import career, coding, design, health, interviews, learners, mastery, ops, skills, workspace
from app.core.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker
from app.llm.factory import build_provider
from app.services.errors import DomainError


def create_app(settings: Settings | None = None, llm=None, clock=None) -> FastAPI:
    """``llm`` and ``clock`` let tests inject a provider and a fixed time."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One engine (and connection pool) per process, created on the running loop.
        engine = create_engine(settings.require_database_url())
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.llm = llm if llm is not None else build_provider(settings)
        try:
            yield
        finally:
            await app.state.llm.aclose()
            await engine.dispose()

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock or (lambda: datetime.now(UTC))

    # Largest legitimate body is a 256 KB source file plus JSON overhead.
    app.add_middleware(BodySizeLimit, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-Learner-Id"],
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(health.router)
    app.include_router(skills.router, prefix="/api/v1")
    app.include_router(mastery.public, prefix="/api/v1")
    app.include_router(coding.public, prefix="/api/v1")
    app.include_router(design.public, prefix="/api/v1")
    app.include_router(ops.public, prefix="/api/v1")
    app.include_router(career.public, prefix="/api/v1")
    app.include_router(workspace.public, prefix="/api/v1")
    local_only = [Depends(require_local_access)]
    app.include_router(learners.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(interviews.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(mastery.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(coding.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(design.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(ops.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(career.router, prefix="/api/v1", dependencies=local_only)
    app.include_router(workspace.router, prefix="/api/v1", dependencies=local_only)
    return app


app = create_app()
