"""Syncs the project library into immutable, content-hashed versions.

A content change creates a new version; workspaces, jobs and submissions keep
pointing at the version they were created from, so history stays reproducible.
"""

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EngProject, EngProjectFile, EngProjectTest, EngProjectVersion, Skill
from app.workspace.content import Project


def version_content(p: Project) -> dict:
    """Descriptive content stored with each version (never tests' expected values or files)."""
    return {
        "level": p.level, "task_type": p.task_type, "skill": p.skill, "area": p.area,
        "prerequisites": p.prerequisites, "stack": p.stack, "dimensions": p.dimensions,
        "competencies": list(p.competencies), "estimated_minutes": p.estimated_minutes,
        "description": p.description.strip(), "architecture": p.architecture.strip(), "setup": p.setup.strip(),
        "misconceptions": p.misconceptions, "hints": p.hints, "rubric": p.rubric,
        "ticket": p.ticket.model_dump(), "exercises": [e.model_dump() for e in p.exercises],
    }


async def sync_projects(db: AsyncSession, projects: list[Project]) -> dict[str, int]:
    skills = {s.slug: s for s in (await db.scalars(select(Skill))).all()}
    created = 0
    seen: set[str] = set()
    for position, p in enumerate(projects):
        if p.skill not in skills:
            raise ValueError(f"{p.slug}: unknown skill '{p.skill}'")
        missing = set(p.prerequisites) - set(skills)
        if missing:
            raise ValueError(f"{p.slug}: unknown prerequisite skills {sorted(missing)}")
        project = await db.scalar(select(EngProject).where(EngProject.slug == p.slug))
        if project is None:
            project = EngProject(slug=p.slug, level=p.level, task_type=p.task_type, skill_id=skills[p.skill].id,
                                 difficulty=p.difficulty, position=position)
            db.add(project)
            await db.flush()
        project.level, project.task_type, project.skill_id = p.level, p.task_type, skills[p.skill].id
        project.difficulty, project.position, project.is_active = p.difficulty, position, True

        digest = p.content_hash()
        version = await db.scalar(select(EngProjectVersion).where(
            EngProjectVersion.project_id == project.id, EngProjectVersion.content_hash == digest))
        if version is None:
            number = (await db.scalar(select(func.max(EngProjectVersion.number))
                                      .where(EngProjectVersion.project_id == project.id)) or 0) + 1
            version = EngProjectVersion(
                project_id=project.id, number=number, content_hash=digest, title=p.title, summary=p.summary,
                content=version_content(p), rubric_version=p.rubric_version, suites=p.suites,
                time_limit_ms=p.time_limit_ms, memory_limit_mb=p.memory_limit_mb,
            )
            version.files = (
                [EngProjectFile(role="starter", path=k, content=v) for k, v in p.starter.items()]
                + [EngProjectFile(role="reference", path=k, content=v) for k, v in p.reference.items()]
                + [EngProjectFile(role="check", path=k, content=v) for k, v in p.checks.items()]
            )
            version.tests = [
                EngProjectTest(position=i, name=t.name, visibility=t.visibility, suite=t.suite, call=t.call,
                               competency=t.competency, args=t.resolved_args(), expected=t.outcome())
                for i, t in enumerate(p.tests)
            ]
            db.add(version)
            await db.flush()
            created += 1
        project.current_version_id = version.id
        seen.add(p.slug)
    await db.execute(update(EngProject).where(EngProject.slug.not_in(seen or {""})).values(is_active=False))
    await db.flush()
    return {"projects": len(projects), "new_versions": created}
