"""Proves every engineering project in the real sandbox:

* the reference solution passes every public and hidden test;
* the starter fails at least one hidden test (otherwise the task is trivial).

    python -m app.workspace.verify_projects [slug ...]
"""

import asyncio
import sys
from dataclasses import dataclass

from app.coding.grading import CaseSpec
from app.coding.sandbox import DockerSandbox
from app.core.config import Settings, get_settings
from app.db.enums import TestOutcome, TestVisibility
from app.workspace.content import Project, load_projects
from app.workspace.execution import SuiteCase, run_checks


@dataclass
class ProjectReport:
    slug: str
    reference_failures: list[str]
    starter_hidden_failures: int
    ok: bool


def cases_for(project: Project) -> list[SuiteCase]:
    return [SuiteCase(t.suite, CaseSpec(i + 1, i, t.name, t.visibility, t.call, t.resolved_args(), t.outcome()))
            for i, t in enumerate(project.tests)]


async def verify_project(sandbox, project: Project) -> ProjectReport:
    cases = cases_for(project)
    names = {c.spec.id: c.spec.name for c in cases}
    kw = dict(checks=project.checks, cases=cases, include_hidden=True,
              time_limit_ms=project.time_limit_ms, memory_limit_mb=project.memory_limit_mb)
    ref = await run_checks(sandbox, files=project.reference_tree(), **kw)
    ref_fail = [f"{names[r.case_id]}: {r.outcome.value} {r.message or ''}".strip()
                for r in ref if r.outcome is not TestOutcome.PASSED]
    starter = await run_checks(sandbox, files=project.starter, **kw)
    hidden_ids = {c.spec.id for c in cases if c.spec.visibility is TestVisibility.HIDDEN}
    starter_fail = sum(1 for r in starter if r.case_id in hidden_ids and r.outcome is not TestOutcome.PASSED)
    return ProjectReport(project.slug, ref_fail, starter_fail, not ref_fail and starter_fail > 0)


async def verify_all(settings: Settings, slugs: list[str] | None = None) -> list[ProjectReport]:
    sandbox = DockerSandbox(settings)
    report = await sandbox.verify()
    if not report.verified:
        raise SystemExit(f"Sandbox not verified: {report.problems}")
    projects = [p for p in load_projects() if not slugs or p.slug in slugs]
    return [await verify_project(sandbox, p) for p in projects]


def main() -> None:
    settings = get_settings().model_copy(update={"sandbox_backend": "docker", "sandbox_allow_container_isolation": True})
    reports = asyncio.run(verify_all(settings, sys.argv[1:] or None))
    for r in reports:
        status = "ok " if r.ok else "FAIL"
        print(f"{status} {r.slug}: starter fails {r.starter_hidden_failures} hidden test(s)")
        for f in r.reference_failures:
            print(f"     reference: {f}")
    if not all(r.ok for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
