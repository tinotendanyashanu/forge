import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Learner
from app.db.session import get_db
from app.services import assessments

Db = Annotated[AsyncSession, Depends(get_db)]


async def get_learner(
    db: Db,
    x_learner_id: Annotated[str | None, Header()] = None,
) -> Learner:
    """Resolves the anonymous learner from the ``X-Learner-Id`` header.

    This identifies a learner; it does not authenticate one. Anyone holding the
    id can act as that learner. Replace with real authentication before any
    multi-user deployment.
    """
    if not x_learner_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Learner-Id header")
    try:
        learner_id = uuid.UUID(x_learner_id)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Learner-Id header") from None
    learner = await assessments.get_learner(db, learner_id)
    if learner is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown learner")
    return learner


CurrentLearner = Annotated[Learner, Depends(get_learner)]


def require_local_access(request: Request) -> None:
    """There is no authentication yet, so learner data is only served to
    clients on this machine (the Next.js server). Disable only behind real auth."""
    settings = request.app.state.settings
    if not settings.local_only:
        return
    host = request.client.host if request.client else None
    if host not in settings.local_only_allowed_hosts:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This FORGE API only accepts local requests until authentication exists",
        )


def get_llm(request: Request):  # -> LLMProvider
    return request.app.state.llm


async def sync_mastery_best_effort(request: Request, db: AsyncSession, learner: Learner) -> None:
    """Updates mastery after a learner action. Failures are logged, not raised:
    every mastery read re-syncs, so nothing is lost."""
    import logging

    from app.mastery.service import sync_learner

    try:
        await sync_learner(db, learner.id, request.app.state.clock())
    except Exception:  # noqa: BLE001
        await db.rollback()
        logging.getLogger("forge.mastery").exception("Mastery sync failed")
