"""Load seed content: ``python -m app.seed`` (uses FORGE_DATABASE_URL)."""

import asyncio
import sys

from app.core.config import get_settings
from app.db.session import create_engine, create_sessionmaker
from app.coding.bank_loader import load_bank
from app.curriculum.graph import load_curriculum
from app.design.challenges import load_challenges
from app.ops.scenario import load_scenarios
from app.career.content import load_content
from app.seed.lessons import load_lessons, sync_lessons
from app.seed.loader import seed_all
from app.workspace.content import load_projects
from app.seed.schema import load_seed_files


async def main(database_url: str) -> None:
    files = load_seed_files()
    curriculum, checksum = load_curriculum()
    bank = load_bank()
    design = load_challenges()
    incidents = load_scenarios()
    career = load_content()
    projects = load_projects()
    lessons = load_lessons(curriculum, {q.slug for f in files for q in f.questions})
    engine = create_engine(database_url)
    try:
        async with create_sessionmaker(engine)() as db:
            stats = await seed_all(db, curriculum, checksum, files, bank, design, incidents, career, projects)
            # Lessons reference question ids, so they load after questions are committed.
            lesson_count = await sync_lessons(db, lessons)
    finally:
        await engine.dispose()
    print(f"Curriculum {curriculum.version}: {len(curriculum.skills)} skills.")
    print(f"Coding bank: {len(bank)} challenges.")
    print(f"Design lab: {len(design)} challenges.")
    print(f"FORGE OPS: {len(incidents)} incident scenarios.")
    print(f"FORGE Career: framework {career.framework.version}, {len(career.templates)} assessments, "
          f"{len(career.judgment)} judgment scenarios, {len(career.projects)} projects.")
    print(f"FORGE Workspace: {len(projects)} engineering projects.")
    print(f"Lessons: {lesson_count} active.")
    print(
        f"Seeded {stats.skills} skills, {stats.topics} topics, "
        f"{stats.questions} questions ({stats.deactivated} deactivated)."
    )


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else get_settings().require_database_url()
    asyncio.run(main(url))
