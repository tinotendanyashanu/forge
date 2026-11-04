"""Shared rubric, mistakes and postmortem structure for FORGE OPS."""

RUBRIC_VERSION = "ops-rubric-v1"

# AI-judged root-cause analysis criteria (0-2 each). Advisory only.
RCA_CRITERIA: dict[str, str] = {
    "diagnostic_accuracy": "Identifies the actual root cause and separates it from symptoms.",
    "evidence_quality": "Cites specific evidence (log lines, metrics, traces, records) that supports each claim.",
    "troubleshooting_efficiency": "Investigated in a sensible order; avoided needless or repeated steps.",
    "mitigation_safety": "Chose low-risk, reversible mitigations; avoided actions that widen impact.",
    "technical_reasoning": "Explains the causal mechanism, not just the correlation.",
    "reliability_awareness": "Considers blast radius, recovery verification and residual risk.",
    "communication": "Clear, accurate, blameless summary a stakeholder could act on.",
    "long_term_prevention": "Concrete preventive actions that address the root cause and contributing factors.",
}

# Recurring-mistake catalog: tag -> remediation. Actions reference these tags.
MISTAKES: dict[str, dict[str, str]] = {
    "restart-before-diagnosis": {
        "title": "Restarting before diagnosing",
        "lesson": "Restarts destroy evidence and rarely fix the cause. Capture state (logs, connections, heap) first, and restart only as a deliberate, time-boxed mitigation.",
        "skill": "devops",
    },
    "scale-without-bottleneck": {
        "title": "Scaling without finding the bottleneck",
        "lesson": "Adding capacity in front of a saturated shared resource (database, pool, lock) multiplies contention. Identify the constrained resource before scaling anything.",
        "skill": "system-design",
    },
    "unsafe-database-change": {
        "title": "Risky database changes during an incident",
        "lesson": "Raising limits, killing sessions or running DDL on a struggling database can turn degradation into an outage. Prefer reversible changes at the application edge.",
        "skill": "sql",
    },
    "retry-amplification": {
        "title": "Amplifying load with retries",
        "lesson": "Retries without backoff, jitter and idempotency multiply load on a failing dependency and can duplicate side effects.",
        "skill": "distributed-systems",
    },
    "rollback-blindly": {
        "title": "Rolling back without evidence",
        "lesson": "A rollback is safe only if the deployment correlates with the failure and the old version is compatible with current data. Check timing and compatibility first.",
        "skill": "devops",
    },
    "ignore-data-safety": {
        "title": "Ignoring data integrity",
        "lesson": "Mitigations that can lose or duplicate data (dropping queues, replaying blindly, forcing migrations) need explicit safeguards and verification.",
        "skill": "distributed-systems",
    },
    "weaken-security": {
        "title": "Weakening security controls under pressure",
        "lesson": "Disabling authentication checks or rate limits to restore availability trades an outage for a breach. Contain abuse instead.",
        "skill": "security",
    },
    "blunt-mitigation": {
        "title": "Blunt mitigations with avoidable customer impact",
        "lesson": "Switching off a whole feature for everyone hurts real users and often leaves the actual threat untouched. Prefer targeted controls (limits, flags for a segment) that address the cause.",
        "skill": "senior-practices",
    },
    "wrong-root-cause": {
        "title": "Misidentified root cause",
        "lesson": "Distinguish the first anomaly from its consequences. Line up the timeline: what changed first, and which signal explains all the others?",
        "skill": "devops",
    },
}

POSTMORTEM_SECTIONS: dict[str, str] = {
    "timeline": "Incident timeline",
    "impact": "Impact",
    "detection": "Detection",
    "root_cause": "Root cause",
    "contributing_factors": "Contributing factors",
    "mitigation": "Mitigation",
    "recovery_verification": "Recovery verification",
    "went_well": "What went well",
    "could_improve": "What could improve",
    "follow_ups": "Follow-up actions",
}

RCA_FIELDS = (
    "summary", "customer_impact", "evidence", "root_cause", "contributing_factors",
    "mitigation", "recovery_validation", "prevention",
)

MODES = {
    "guided": "Guided investigation: coach step by step; suggest which evidence to look at next, but let the learner draw conclusions.",
    "interview": "Production interview: a demanding interviewer. Never reveal or confirm the root cause; make the learner prove it with evidence.",
    "commander": "Senior incident commander: run the incident. Push on customer impact, risk of each change, communication and verification.",
    "postmortem": "Postmortem review: blameless, rigorous review of the write-up; probe causes, contributing factors and follow-ups.",
}

# Weights of the deterministic (verified) outcome score.
# "decisions" grades the investigation itself: diagnosing before changing things,
# choosing the right mitigations instead of trial and error, and investigating with focus.
OUTCOME_WEIGHTS = {"root_cause": 0.30, "evidence": 0.20, "safety": 0.20, "decisions": 0.20, "efficiency": 0.10}
