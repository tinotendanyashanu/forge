"""Personalised career roadmap from a readiness report.

Order: critical gaps on gated competencies, then unmet/missing gates, then
required competencies. Each item links to real FORGE activities the learner
hasn't completed and states measurable completion criteria from the framework
rules. When FORGE has no content at the needed difficulty, it says so.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.career.content import Framework
from app.career.readiness import LEVEL_RANK
from app.db.models import (
    ArchitectureProject,
    CodingChallenge,
    CodingChallengeVersion,
    CodingSubmission,
    DesignChallenge,
    DesignChallengeVersion,
    IncidentScenario,
    IncidentScenarioVersion,
    IncidentSession,
    Question,
    Skill,
)

DIFF = {"foundation": "beginner", "junior": "beginner", "mid": "intermediate", "senior": "advanced"}
DESIGN_LEVELS = {"foundation": ["beginner"], "junior": ["beginner"], "mid": ["intermediate"], "senior": ["advanced", "senior"]}


async def build(db: AsyncSession, fw: Framework, learner_id: uuid.UUID, report: dict, goal: str = "") -> dict:
    target = report["target"]
    rows = [g | {"priority": "critical"} for g in target["gates"] if g["status"] == "critical"]
    rows += [g | {"priority": "gate"} for g in target["gates"] if g["status"] in ("unmet", "missing")]
    rows += [r | {"priority": "required"} for r in target["required"] if r["status"] in ("unmet", "missing")]
    skills = {s.slug: s for s in (await db.scalars(select(Skill))).all()}
    solved = set((await db.scalars(select(CodingSubmission.challenge_id).where(
        CodingSubmission.learner_id == learner_id, CodingSubmission.all_passed, CodingSubmission.verified))).all())
    designed = set((await db.scalars(select(ArchitectureProject.challenge_id).where(ArchitectureProject.learner_id == learner_id))).all())
    resolved = set((await db.scalars(select(IncidentSession.scenario_id).where(
        IncidentSession.learner_id == learner_id, IncidentSession.success.is_(True)))).all())
    coding = (await db.execute(select(CodingChallenge, CodingChallengeVersion.title, Skill.slug)
                               .join(CodingChallengeVersion, CodingChallengeVersion.id == CodingChallenge.current_version_id)
                               .join(Skill, Skill.id == CodingChallenge.skill_id).where(CodingChallenge.is_active))).all()
    designs = (await db.execute(select(DesignChallenge, DesignChallengeVersion)
                                .join(DesignChallengeVersion, DesignChallengeVersion.id == DesignChallenge.current_version_id)
                                .where(DesignChallenge.is_active).order_by(DesignChallenge.position))).all()
    incidents = (await db.execute(select(IncidentScenario, IncidentScenarioVersion)
                                  .join(IncidentScenarioVersion, IncidentScenarioVersion.id == IncidentScenario.current_version_id)
                                  .where(IncidentScenario.is_active).order_by(IncidentScenario.position))).all()
    question_skills = {(s, d) for s, d in (await db.execute(
        select(Skill.slug, Question.difficulty).join(Question, Question.skill_id == Skill.id).where(Question.is_active).distinct())).all()}
    r = fw.rules
    items = []
    for row in rows:
        d = fw.dim(row["dimension"])
        needed = row["needed"]
        diff = DIFF[needed]
        acts: list[dict] = []
        for s in d.skills:
            if s in skills:
                acts.append({"type": "lesson", "label": f"Review {skills[s].title}", "href": f"/tracks/{s}"})
        cands = [(c, t) for c, t, sk in coding
                 if (sk in d.skills or c.area in d.coding_areas) and LEVEL_RANK_D(c.difficulty.value) >= LEVEL_RANK_D(diff)
                 and c.id not in solved]
        for c, t in sorted(cands, key=lambda x: (LEVEL_RANK_D(x[0].difficulty.value), x[0].slug))[:3]:
            acts.append({"type": "coding", "label": f"Solve '{t}' ({c.difficulty.value})", "href": f"/lab/challenges/{c.slug}"})
        for s in d.skills:
            if (s, diff) in {(a, b.value) for a, b in question_skills}:
                acts.append({"type": "interview", "label": f"AI interview: {skills[s].title} ({diff})", "href": "/interview",
                             "params": {"skill": s, "difficulty": diff}})
        if d.all_design_evidence or d.design_competencies or d.failure_evidence:
            for c, v in designs:
                comps = set(v.content.get("competencies", []))
                if (d.all_design_evidence or d.failure_evidence or comps & set(d.design_competencies)) \
                        and c.level in DESIGN_LEVELS[needed] and c.id not in designed:
                    acts.append({"type": "design", "label": f"Design: {v.title}", "href": f"/design/challenges/{c.slug}"})
                    break
        if d.all_incident_evidence or d.incident_competencies:
            for sc, v in incidents:
                comps = set(v.content.get("competencies", []))
                if (d.all_incident_evidence or comps & set(d.incident_competencies)) \
                        and sc.level in DESIGN_LEVELS[needed] and sc.id not in resolved:
                    acts.append({"type": "incident", "label": f"Incident: {v.title}", "href": f"/ops/incidents/{sc.slug}"})
                    break
        if d.judgment_tags:
            acts.append({"type": "judgment", "label": "Practise engineering judgment scenarios",
                         "href": "/career/assessments/diagnostic"})
        criteria = [f"Reach {needed}: reliability-weighted score of at least {r.score_threshold:.0%} on evidence at "
                    f"{diff} difficulty or harder" if needed != "foundation" else
                    f"Reach foundation: score of at least {r.foundation_threshold:.0%} on any evidence"]
        if needed != "foundation":
            criteria.append(f"Evidence weight of at least {r.min_weight[needed]} (a verified result counts 1.0, an AI "
                            f"judgment 0.5) across {r.min_sessions[needed]}+ independent sessions")
            if needed in r.verified_required and d.verifiable:
                criteria.append("At least one verified result (sandbox tests, simulation outcome or objective questions)")
            if needed in r.reasoning_required:
                criteria.append("At least one evaluated explanation (interview, design or judgment)")
        if row["dangerous_actions"]:
            criteria.append("Resolve an incident in this area without any harmful action")
        verifiable_acts = [a for a in acts if a["type"] in ("coding", "incident")]
        items.append({
            "dimension": d.key, "title": d.title, "priority": row["priority"], "needed": needed,
            "demonstrated": row["demonstrated"], "status": row["status"], "why": d.why, "critical_gap": d.critical_gap,
            "expectation": d.levels.get(needed, ""), "reasons": row["reasons"], "activities": acts,
            "completion_criteria": criteria,
            "content_note": None if verifiable_acts or not d.verifiable else
            f"FORGE has no unfinished verified activity for this at {diff} difficulty; available evidence is AI-judged only.",
            "reassess_in_days": 14 if row["priority"] == "critical" else 21,
        })
    order = {"critical": 0, "gate": 1, "required": 2}
    items.sort(key=lambda i: (order[i["priority"]], -LEVEL_RANK[i["needed"]], i["title"]))
    now = datetime.now(UTC)
    return {"goal": goal, "track": report["track"], "target_level": report["target_level"],
            "framework_version": report["framework_version"], "generated_at": now.isoformat(),
            "status": target["status"], "items": items,
            "reassess_on": (now + timedelta(days=min((i["reassess_in_days"] for i in items), default=30))).date().isoformat()}


def LEVEL_RANK_D(d: str) -> int:  # noqa: N802
    return {"beginner": 1, "intermediate": 2, "advanced": 3}[d]

