from fastapi import APIRouter

from app.api.deps import Db
from app.schemas.content import SkillDetail, SkillSummary
from app.services import content

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillSummary])
async def list_skills(db: Db) -> list[SkillSummary]:
    return await content.list_skills(db)


@router.get("/{slug}", response_model=SkillDetail)
async def get_skill(slug: str, db: Db) -> SkillDetail:
    return await content.get_skill(db, slug)
