"""Collects a learner's evidence for the readiness model.

Sources are the existing mastery evidence (objective answers, verified coding
submissions, AI interview evaluations, design evaluations, failure drills,
incident outcomes and reviews) plus Career's own judgment and take-home
reviews. Each item is mapped to framework dimensions by the explicit rules in
the framework (skills, coding areas, design/incident competencies, tags).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.career.content import Framework
from app.career.readiness import EvidenceItem
from app.workspace.content import LEVEL_DIFFICULTY as WORKSPACE_DIFFICULTY
from app.db.enums import EvidenceSource
from app.db.models import (
    CareerAttempt,
    CareerResponse,
    CareerSection,
    CodingChallenge,
    CodingChallengeVersion,
    DesignChallenge,
    EngExerciseResponse,
    EngProject,
    EngProjectVersion,
    DesignChallengeVersion,
    IncidentScenario,
    IncidentScenarioVersion,
    IncidentSession,
    MasteryEvidence,
    Question,
    Skill,
)

KIND = {
    EvidenceSource.OBJECTIVE_ASSESSMENT: "knowledge_objective",
    EvidenceSource.CODING_SUBMISSION: "coding_objective",
    EvidenceSource.INCIDENT_SIMULATION: "simulation",
    EvidenceSource.AI_INTERVIEW: "rubric_ai",
    EvidenceSource.INCIDENT_REVIEW: "rubric_ai",
    EvidenceSource.SELF_REPORT: "rubric_ai",
    EvidenceSource.DESIGN_EVALUATION: "architecture_ai",
    EvidenceSource.FAILURE_SCENARIO: "architecture_ai",
    EvidenceSource.ENGINEERING_TASK: "coding_objective",
}
# FORGE Workspace collaboration exercises (AI-reviewed, unverified) by exercise kind.
EXERCISE_DIMENSIONS = {
    "stakeholder_explanation": ["technical_communication"],
    "clarify_requirements": ["technical_communication", "engineering_judgment"],
    "review_junior_code": ["code_review_maintainability", "technical_communication"],
    "requirement_change": ["engineering_judgment", "technical_communication"],
    "implementation_plan": ["engineering_judgment"],
    "estimate": ["engineering_judgment"],
    "adr": ["engineering_judgment", "system_architecture"],
    "deployment_plan": ["devops_deployment", "engineering_judgment"],
}
LEVEL_DIFFICULTY = {"foundation": "beginner", "junior": "beginner", "mid": "intermediate", "senior": "advanced"}


def dimensions_for(fw: Framework, source: str, *, skill: str | None = None, area: str | None = None,
                   competencies: list[str] | None = None, tags: list[str] | None = None,
                   evidence_dimension: str | None = None, dims: list[str] | None = None) -> list[str]:
    comps = set(competencies or [])
    out = []
    for d in fw.dimensions:
        hit = False
        if source in ("objective_assessment", "ai_interview", "self_report"):
            hit = skill in d.skills
        elif source == "coding_submission":
            hit = skill in d.skills or (area is not None and area in d.coding_areas)
        elif source == "design_evaluation":
            hit = d.all_design_evidence or bool(comps & set(d.design_competencies))
        elif source == "failure_scenario":
            hit = d.failure_evidence or bool(comps & set(d.design_competencies))
        elif source == "incident_simulation":
            hit = d.all_incident_evidence or bool(comps & set(d.incident_competencies))
        elif source == "incident_review":
            hit = d.incident_review_evidence or bool(comps & set(d.incident_competencies) & {"root_cause_analysis"})
        elif source == "judgment":
            hit = bool(set(tags or []) & set(d.judgment_tags))
        elif source in ("take_home", "engineering_task", "engineering_exercise"):
            hit = d.key in (dims or [])
        if not hit and evidence_dimension and evidence_dimension in d.evidence_dimensions:
            hit = True
        if hit:
            out.append(d.key)
    return out


async def formal_map(db: AsyncSession, learner_id: uuid.UUID) -> dict[str, str]:
    """Linked activity ids (sessions, projects, submissions, responses) -> 'formal:<attempt id>'."""
    rows = (await db.execute(
        select(CareerSection, CareerAttempt).join(CareerAttempt, CareerAttempt.id == CareerSection.attempt_id)
        .where(CareerAttempt.learner_id == learner_id, CareerAttempt.purpose == "formal")
    )).all()
    out: dict[str, str] = {}
    for sec, att in rows:
        link = sec.link or {}
        for key in ("interview_session_id", "project_id", "incident_session_id"):
            if link.get(key):
                out[str(link[key])] = f"formal:{att.id}"
        for sid in (sec.result or {}).get("submission_ids", []):
            out[str(sid)] = f"formal:{att.id}"
        out[f"section:{sec.id}"] = f"formal:{att.id}"
    return out


async def collect(db: AsyncSession, fw: Framework, learner_id: uuid.UUID) -> list[EvidenceItem]:
    formal = await formal_map(db, learner_id)
    skills = {s.id: s.slug for s in (await db.scalars(select(Skill))).all()}
    rows = (await db.scalars(select(MasteryEvidence).where(MasteryEvidence.learner_id == learner_id))).all()

    q_ids = {r.question_id for r in rows if r.question_id}
    c_ids = {r.coding_challenge_id for r in rows if r.coding_challenge_id}
    d_ids = {r.design_challenge_id for r in rows if r.design_challenge_id}
    i_ids = {r.incident_scenario_id for r in rows if r.incident_scenario_id}
    questions = {q.id: q.title for q in (await db.scalars(select(Question).where(Question.id.in_(q_ids or [0])))).all()}
    coding = {c.id: (c.area, t) for c, t in (await db.execute(
        select(CodingChallenge, CodingChallengeVersion.title)
        .join(CodingChallengeVersion, CodingChallengeVersion.id == CodingChallenge.current_version_id)
        .where(CodingChallenge.id.in_(c_ids or [0])))).all()}
    design = {c.id: (v.content.get("competencies", []), v.title) for c, v in (await db.execute(
        select(DesignChallenge, DesignChallengeVersion)
        .join(DesignChallengeVersion, DesignChallengeVersion.id == DesignChallenge.current_version_id)
        .where(DesignChallenge.id.in_(d_ids or [0])))).all()}
    incident = {c.id: (v.content.get("competencies", []), v.title) for c, v in (await db.execute(
        select(IncidentScenario, IncidentScenarioVersion)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
        .where(IncidentScenario.id.in_(i_ids or [0])))).all()}
    e_ids = {r.engineering_project_id for r in rows if r.engineering_project_id}
    engineering = {p.id: v for p, v in (await db.execute(
        select(EngProject, EngProjectVersion)
        .join(EngProjectVersion, EngProjectVersion.id == EngProject.current_version_id)
        .where(EngProject.id.in_(e_ids or [0])))).all()}
    sim_ids = [r.source_id for r in rows if r.source == EvidenceSource.INCIDENT_SIMULATION]
    dangerous: dict[uuid.UUID, list[str]] = {}
    for sess, ver in (await db.execute(
        select(IncidentSession, IncidentScenarioVersion)
        .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentSession.version_id)
        .where(IncidentSession.id.in_(sim_ids or [uuid.uuid4()])))).all():
        harmful = set((sess.outcome or {}).get("harmful_actions", []))
        dangerous[sess.id] = sorted({a["mistake"] for a in ver.content["actions"] if a["id"] in harmful and a.get("mistake")})

    items: list[EvidenceItem] = []
    for r in rows:
        src = r.source.value
        skill = skills.get(r.skill_id)
        area, title, comps, mistakes, explicit = None, "", [], [], None
        if r.engineering_project_id:
            v = engineering.get(r.engineering_project_id)
            title = f"{v.title} (project)" if v else "Engineering project"
            explicit = v.content["dimensions"] if v else []
        elif r.question_id:
            title = questions.get(r.question_id, "Question")
        elif r.coding_challenge_id:
            area, title = coding.get(r.coding_challenge_id, (None, "Coding challenge"))
        elif r.design_challenge_id:
            comps, title = design.get(r.design_challenge_id, ([], "Design challenge"))
        elif r.incident_scenario_id:
            comps, title = incident.get(r.incident_scenario_id, ([], "Incident"))
            if src == "incident_simulation":
                mistakes = dangerous.get(r.source_id, [])  # mistakes behind actions rated harmful
        dims = dimensions_for(fw, src, skill=skill, area=area, competencies=comps,
                              evidence_dimension=r.dimension.value, dims=explicit)
        if not dims:
            continue
        context = formal.get(str(r.session_id)) or formal.get(str(r.source_id)) or "practice"
        items.append(EvidenceItem(
            id=f"m:{r.id}", source=src, kind=KIND[r.source], score=float(r.score), difficulty=r.difficulty.value,
            observed_at=r.observed_at, session=str(r.session_id), title=f"{title} ({skill})" if skill else title,
            dimensions=dims, verified=r.verified, context=context, mistakes=mistakes, success=r.success))

    # FORGE Workspace collaboration exercises: AI-reviewed, unverified, eligible only.
    exercise_rows = (await db.execute(
        select(EngExerciseResponse, EngProjectVersion)
        .join(EngProjectVersion, EngProjectVersion.id == EngExerciseResponse.version_id)
        .where(EngExerciseResponse.learner_id == learner_id, EngExerciseResponse.status == "evaluated",
               EngExerciseResponse.eligible)
    )).all()
    for resp, v in exercise_rows:
        ex = next((e for e in v.content.get("exercises", []) if e["slug"] == resp.exercise_slug), None)
        if ex is None:
            continue
        dims = dimensions_for(fw, "engineering_exercise", dims=EXERCISE_DIMENSIONS.get(ex["kind"], []))
        if not dims:
            continue
        items.append(EvidenceItem(
            id=f"x:{resp.id}", source="engineering_exercise", kind="communication_ai", score=float(resp.score),
            difficulty=WORKSPACE_DIFFICULTY[v.content["level"]].value, observed_at=resp.completed_at or resp.created_at,
            session=str(resp.workspace_id), title=f"{ex['title']} (simulated)", dimensions=dims, verified=False,
            context="practice", success=float(resp.score) >= 0.7))

    responses = (await db.execute(
        select(CareerResponse, CareerSection).join(CareerSection, CareerSection.id == CareerResponse.section_id)
        .where(CareerResponse.learner_id == learner_id, CareerResponse.status == "evaluated", CareerResponse.eligible)
    )).all()
    from app.career.content import load_content
    content = load_content()
    for resp, sec in responses:
        if resp.kind == "judgment":
            try:
                sc = content.scenario(resp.item_slug)
            except StopIteration:
                continue
            dims = dimensions_for(fw, "judgment", tags=list(sc.tags))
            level = sc.level
            title = sc.title
        else:
            try:
                pj = content.project(resp.item_slug)
            except StopIteration:
                continue
            dims = dimensions_for(fw, "take_home", dims=pj.dimensions)
            level, title = pj.level, pj.title
        if not dims:
            continue
        items.append(EvidenceItem(
            id=f"r:{resp.id}", source=resp.kind, kind="communication_ai" if resp.kind == "judgment" else "rubric_ai",
            score=float(resp.score), difficulty=LEVEL_DIFFICULTY[level], observed_at=resp.completed_at or resp.created_at,
            session=str(resp.id), title=title, dimensions=dims, verified=False,
            context=formal.get(f"section:{sec.id}", "practice"), success=float(resp.score) >= 0.7))
    return items
