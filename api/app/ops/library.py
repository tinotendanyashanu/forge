"""Seeds incident scenarios into immutable, versioned rows."""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IncidentScenario, IncidentScenarioVersion, Skill
from app.ops.catalog import RUBRIC_VERSION
from app.ops.scenario import ScenarioSpec


async def sync_scenarios(db: AsyncSession, specs: list[tuple[str, ScenarioSpec]]) -> int:
    skills = {s.slug for s in (await db.scalars(select(Skill))).all()}
    created, seen = 0, set()
    for position, (level, spec) in enumerate(specs):
        if missing := set(spec.skills) - skills:
            raise ValueError(f"{spec.slug}: unknown skills {sorted(missing)}")
        sc = await db.scalar(select(IncidentScenario).where(IncidentScenario.slug == spec.slug))
        if sc is None:
            sc = IncidentScenario(slug=spec.slug, level=level, position=position)
            db.add(sc)
            await db.flush()
        sc.level, sc.position, sc.is_active = level, position, True
        digest = spec.content_hash()
        version = await db.scalar(select(IncidentScenarioVersion).where(
            IncidentScenarioVersion.scenario_id == sc.id, IncidentScenarioVersion.content_hash == digest))
        if version is None:
            number = (await db.scalar(select(func.max(IncidentScenarioVersion.number)).where(
                IncidentScenarioVersion.scenario_id == sc.id)) or 0) + 1
            version = IncidentScenarioVersion(scenario_id=sc.id, number=number, content_hash=digest,
                                              rubric_version=RUBRIC_VERSION, title=spec.title,
                                              content=spec.model_dump(mode="json"))
            db.add(version)
            await db.flush()
            created += 1
        sc.current_version_id = version.id
        seen.add(spec.slug)
    await db.execute(update(IncidentScenario).where(IncidentScenario.slug.not_in(seen)).values(is_active=False))
    await db.flush()
    return created
