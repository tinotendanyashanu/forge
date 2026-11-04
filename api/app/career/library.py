"""Seeds FORGE Career content as immutable versions (career_content_versions)."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.career.content import Content, digest
from app.db.models import CareerContentVersion, CodingChallenge, Skill


async def _upsert(db: AsyncSession, kind: str, key: str, content: dict) -> CareerContentVersion:
    h = digest(content)
    row = await db.scalar(select(CareerContentVersion).where(
        CareerContentVersion.kind == kind, CareerContentVersion.key == key, CareerContentVersion.content_hash == h))
    if row is None:
        n = (await db.scalar(select(func.max(CareerContentVersion.number)).where(
            CareerContentVersion.kind == kind, CareerContentVersion.key == key)) or 0) + 1
        row = CareerContentVersion(kind=kind, key=key, number=n, content_hash=h, content=content)
        db.add(row)
        await db.flush()
    await db.execute(update(CareerContentVersion).where(
        CareerContentVersion.kind == kind, CareerContentVersion.key == key, CareerContentVersion.id != row.id
    ).values(is_current=False))
    row.is_current = True
    return row


async def sync_career(db: AsyncSession, content: Content) -> int:
    skills = {s for s in (await db.scalars(select(Skill.slug))).all()}
    challenges = {s for s in (await db.scalars(select(CodingChallenge.slug))).all()}
    for d in content.framework.dimensions:
        if unknown := set(d.skills) - skills:
            raise ValueError(f"dimension {d.key}: unknown skills {sorted(unknown)}")
    for p in content.projects:
        if unknown := set(p.linked_challenges) - challenges:
            raise ValueError(f"project {p.slug}: unknown coding challenges {sorted(unknown)}")
    for t in content.templates:
        for s in t.sections:
            for pick in s.params.get("picks", []):
                if pick.get("skill") and pick["skill"] not in skills:
                    raise ValueError(f"{t.slug}/{s.key}: unknown skill {pick['skill']}")
            if s.kind == "interview" and s.params.get("skill") not in skills:
                raise ValueError(f"{t.slug}/{s.key}: unknown interview skill")
    created = 0
    before = await db.scalar(select(func.count()).select_from(CareerContentVersion))
    await _upsert(db, "framework", "framework", content.framework.model_dump(mode="json"))
    for t in content.templates:
        await _upsert(db, "template", t.slug, t.model_dump(mode="json"))
    for s in content.judgment:
        await _upsert(db, "judgment", s.slug, s.model_dump(mode="json"))
    for p in content.projects:
        await _upsert(db, "project", p.slug, p.model_dump(mode="json"))
    await db.flush()
    created = (await db.scalar(select(func.count()).select_from(CareerContentVersion))) - before
    return created
