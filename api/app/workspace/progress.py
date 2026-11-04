"""Engineering competency progress and follow-up recommendations.

Three separate kinds of signal, never blended into one number:

* **verified**: hidden and public test outcomes from submissions executed in a
  verified sandbox, per competency tag on each test (latest submission per project);
* **ai_review**: rubric ratings from completed AI reviews (subjective, advisory);
* **exercises**: AI-reviewed collaboration write-ups (subjective, advisory).
"""

import uuid
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import ReviewStatus, TestOutcome
from app.db.models import (
    EngExerciseResponse,
    EngJob,
    EngProject,
    EngProjectVersion,
    EngPullRequest,
    EngReview,
    EngSubmission,
    EngTestResult,
    EngWorkspace,
    Skill,
    SkillMastery,
)
from app.workspace.content import COMPETENCIES

LABELS = {
    "codebase_comprehension": "Codebase comprehension", "implementation": "Software implementation",
    "debugging": "Debugging", "testing": "Testing", "database": "Database engineering", "api": "API development",
    "frontend": "Frontend development", "refactoring": "Refactoring", "maintainability": "Maintainability",
    "security": "Security", "performance": "Performance", "communication": "Technical communication",
    "judgment": "Engineering judgment",
}
RATING_SCORE = {"meets": 1.0, "partial": 0.5, "missing": 0.0}
DEMONSTRATED_STATES = {"developing", "proficient", "mastered"}


async def progress(db: AsyncSession, learner_id: uuid.UUID) -> dict:
    projects = list((await db.scalars(
        select(EngProject).where(EngProject.is_active)
        .options(selectinload(EngProject.current_version), selectinload(EngProject.skill))
        .order_by(EngProject.position))).all())
    workspaces = {w.project_id: w for w in (await db.scalars(
        select(EngWorkspace).where(EngWorkspace.learner_id == learner_id))).all()}
    subs = list((await db.scalars(select(EngSubmission).where(EngSubmission.learner_id == learner_id)
                                  .order_by(EngSubmission.created_at))).all())
    prs = list((await db.scalars(select(EngPullRequest).where(EngPullRequest.learner_id == learner_id)
                                 .options(selectinload(EngPullRequest.revisions)))).all())
    by_project: dict[int, list[EngSubmission]] = defaultdict(list)
    for s in subs:
        by_project[s.project_id].append(s)

    # Test outcomes with their competency tags, for every submission.
    job_ids = [s.job_id for s in subs]
    outcome_rows = (await db.execute(
        select(EngTestResult.job_id, EngTestResult.outcome, EngTestResult.test_id)
        .where(EngTestResult.job_id.in_(job_ids or [uuid.uuid4()]))
    )).all()
    version_ids = {s.version_id for s in subs}
    tests = {}
    for v in (await db.scalars(select(EngProjectVersion).where(EngProjectVersion.id.in_(version_ids or [0]))
                               .options(selectinload(EngProjectVersion.tests)))).all():
        for t in v.tests:
            tests[t.id] = t
    results_by_job: dict[uuid.UUID, list[tuple[TestOutcome, int]]] = defaultdict(list)
    for job_id, outcome, test_id in outcome_rows:
        results_by_job[job_id].append((outcome, test_id))

    verified: dict[str, list[int]] = {k: [0, 0] for k in COMPETENCIES}  # passed, total
    failing_competencies: Counter[str] = Counter()
    repeated: list[dict] = []
    project_rows = []
    for p in projects:
        mine = by_project.get(p.id, [])
        latest = mine[-1] if mine else None
        if latest and latest.verified:
            for outcome, test_id in results_by_job.get(latest.job_id, []):
                comp = tests[test_id].competency
                verified[comp][1] += 1
                if outcome is TestOutcome.PASSED:
                    verified[comp][0] += 1
                else:
                    failing_competencies[comp] += 1
        # The same test failing in two or more verified submissions: a repeated bug.
        fails: Counter[str] = Counter()
        for s in mine:
            if s.verified:
                for outcome, test_id in results_by_job.get(s.job_id, []):
                    if outcome is not TestOutcome.PASSED:
                        fails[tests[test_id].name] += 1
        repeated += [{"project": p.slug, "test": name, "times": n} for name, n in fails.items() if n >= 2]
        ws = workspaces.get(p.id)
        pr_list = [pr for pr in prs if ws and pr.workspace_id == ws.id]
        project_rows.append({
            "slug": p.slug, "title": p.current_version.title, "level": p.level, "task_type": p.task_type,
            "skill": p.skill.slug,
            "workspace_id": str(ws.id) if ws else None, "status": ws.status if ws else "not_started",
            "submissions": len(mine),
            "verified_submissions": sum(1 for s in mine if s.verified),
            "best_hidden": max(((s.hidden_passed, s.hidden_total) for s in mine if s.verified), default=None),
            "latest_all_passed": bool(latest and latest.all_passed and latest.verified),
            "pull_requests": len(pr_list),
            "revisions": sum(len(pr.revisions) for pr in pr_list),
            "approved": any(pr.status == "approved" for pr in pr_list),
            "competencies": p.current_version.content["competencies"],
        })

    reviews = (await db.execute(
        select(EngReview, EngSubmission.project_id).join(EngSubmission, EngSubmission.id == EngReview.submission_id)
        .where(EngReview.learner_id == learner_id, EngReview.status == ReviewStatus.COMPLETED))).all()
    ai: dict[str, list[float]] = defaultdict(list)
    weak_architecture = 0
    comp_of = {p.id: p.current_version.content["competencies"] for p in projects}
    for rv, project_id in reviews:
        r = rv.review or {}
        scores = [RATING_SCORE[x["rating"]] for x in r.get("rubric", []) if x["rating"] in RATING_SCORE]
        if scores:
            mean = sum(scores) / len(scores)
            for comp in comp_of.get(project_id, []):
                ai[comp].append(mean)
            ai["maintainability"].append(mean)
        if any(f["dimension"] == "architecture" and f["severity"] in ("major", "blocker") for f in r.get("findings", [])):
            weak_architecture += 1

    exercises = list((await db.scalars(select(EngExerciseResponse).where(
        EngExerciseResponse.learner_id == learner_id, EngExerciseResponse.status == "evaluated"))).all())
    for e in exercises:
        target = "communication" if e.exercise_slug and "explain" in e.exercise_slug else "judgment"
        ai[target].append(float(e.score))

    competencies = []
    for key in COMPETENCIES:
        passed, total = verified[key]
        ai_scores = ai.get(key, [])
        competencies.append({
            "key": key, "label": LABELS[key],
            "verified": {"passed": passed, "total": total, "rate": round(passed / total, 3) if total else None},
            "ai_review": {"count": len(ai_scores), "mean": round(sum(ai_scores) / len(ai_scores), 3) if ai_scores else None},
        })

    recommendations = await _recommend(db, learner_id, projects, project_rows, failing_competencies, repeated,
                                       weak_architecture)
    return {
        "projects": project_rows,
        "competencies": competencies,
        "recommendations": recommendations,
        "repeated_failures": repeated,
        "totals": {
            "projects_started": sum(1 for r in project_rows if r["workspace_id"]),
            "projects_approved": sum(1 for r in project_rows if r["approved"]),
            "verified_submissions": sum(r["verified_submissions"] for r in project_rows),
            "exercises_reviewed": len(exercises),
        },
        "note": "Verified figures come only from tests executed in the verified sandbox. AI review figures are "
                "subjective and advisory, and are never used to mark a task complete. Simulated collaboration is "
                "not real-world employment experience.",
    }


async def _recommend(db: AsyncSession, learner_id: uuid.UUID, projects: list[EngProject], rows: list[dict],
                     failing: Counter, repeated: list[dict], weak_architecture: int) -> list[dict]:
    states = {slug: state for slug, state in (await db.execute(
        select(Skill.slug, SkillMastery.state).join(SkillMastery, SkillMastery.skill_id == Skill.id)
        .where(SkillMastery.learner_id == learner_id))).all()}
    by_slug = {r["slug"]: r for r in rows}
    out: list[dict] = []
    for comp, n in failing.most_common(3):
        candidates = [p for p in projects if comp in p.current_version.content["competencies"]
                      and not by_slug[p.slug]["approved"]]
        target = next((p for p in candidates if by_slug[p.slug]["submissions"] == 0), candidates[0] if candidates else None)
        out.append({
            "kind": "failed_tests", "competency": comp, "label": LABELS[comp],
            "reason": f"{n} test(s) tagged {LABELS[comp].lower()} failed in your latest verified submission(s).",
            "project": target.slug if target else None,
        })
    for r in repeated[:3]:
        out.append({"kind": "repeated_bug", "competency": None, "label": "Repeated failure",
                    "reason": f"'{r['test']}' failed in {r['times']} submissions of {r['project']}. Re-read the ticket "
                              "and trace that test through the code before changing more.",
                    "project": r["project"]})
    if weak_architecture:
        target = next((p for p in projects if p.level in ("mid", "senior") and not by_slug[p.slug]["approved"]), None)
        out.append({"kind": "architecture", "competency": "judgment", "label": "Architectural reasoning",
                    "reason": f"{weak_architecture} AI review(s) raised major architecture concerns. Try a Technical "
                              "Lead review and answer its trade-off questions.",
                    "project": target.slug if target else None})
    for p in projects:
        prereqs = p.current_version.content.get("prerequisites", [])
        missing = [s for s in prereqs if states.get(s) not in DEMONSTRATED_STATES]
        if missing and by_slug[p.slug]["submissions"] == 0 and len(out) < 8:
            out.append({"kind": "prerequisites", "competency": None, "label": "Prerequisites",
                        "reason": f"Before {p.current_version.title}: demonstrate {', '.join(missing)} on your learning path.",
                        "project": p.slug, "skills": missing})
    if not out:
        nxt = next((p for p in projects if by_slug[p.slug]["status"] == "not_started"), None)
        if nxt:
            out.append({"kind": "next", "competency": None, "label": "Next project",
                        "reason": "Continue with the next project in the library.", "project": nxt.slug})
    return out


async def engineering_portfolio(db: AsyncSession, learner_id: uuid.UUID) -> dict:
    """Project evidence for FORGE Career reports. Simulated work, clearly labelled."""
    rows = (await db.execute(
        select(EngWorkspace, EngProject, EngProjectVersion)
        .join(EngProject, EngProject.id == EngWorkspace.project_id)
        .join(EngProjectVersion, EngProjectVersion.id == EngWorkspace.version_id)
        .where(EngWorkspace.learner_id == learner_id).order_by(EngWorkspace.created_at))).all()
    out = []
    for ws, project, version in rows:
        subs = list((await db.scalars(select(EngSubmission).where(EngSubmission.workspace_id == ws.id)
                                      .order_by(EngSubmission.number))).all())
        reviews = list((await db.scalars(select(EngReview).where(
            EngReview.submission_id.in_([s.id for s in subs] or [uuid.uuid4()]),
            EngReview.status == ReviewStatus.COMPLETED).order_by(EngReview.created_at))).all())
        prs = list((await db.scalars(select(EngPullRequest).where(EngPullRequest.workspace_id == ws.id)
                                     .options(selectinload(EngPullRequest.revisions)))).all())
        exercises = list((await db.scalars(select(EngExerciseResponse).where(
            EngExerciseResponse.workspace_id == ws.id, EngExerciseResponse.status == "evaluated"))).all())
        verified = [s for s in subs if s.verified]
        approved = next((pr for pr in prs if pr.status == "approved"), None)
        out.append({
            "project": project.slug, "title": version.title, "level": project.level, "task_type": project.task_type,
            "complexity": {"level": project.level, "task_type": project.task_type,
                           "estimated_minutes": version.content["estimated_minutes"], "suites": version.suites},
            "verified_outcomes": [{"attempt": s.number, "passed": s.passed, "total": s.total,
                                   "hidden_passed": s.hidden_passed, "hidden_total": s.hidden_total,
                                   "all_passed": s.all_passed, "at": s.created_at.isoformat()} for s in verified],
            "unverified_attempts": len(subs) - len(verified),
            "review_history": [{"mode": r.mode, "recommendation": (r.review or {}).get("recommendation"),
                                "rubric_version": r.rubric_version, "at": r.created_at.isoformat()} for r in reviews],
            "revisions_required": max((len(pr.revisions) - 1 for pr in prs), default=0),
            "pull_requests": [{"status": pr.status, "revisions": len(pr.revisions)} for pr in prs],
            "decisions": [{"exercise": e.exercise_slug, "score": float(e.score), "eligible": e.eligible} for e in exercises],
            "completed_at": approved.decided_at.isoformat() if approved and approved.decided_at else None,
            "status": ws.status,
        })
    return {
        "projects": out,
        "note": "Simulated engineering projects. Test outcomes are verified only when marked so; AI reviews and "
                "collaboration exercises are advisory. Completing simulated projects is not employment experience and "
                "does not by itself establish senior readiness.",
    }
