from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    settings = request.app.state.settings
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - any failure means the DB is unusable
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=settings.version,
        environment=settings.environment,
        database=database,
    )
