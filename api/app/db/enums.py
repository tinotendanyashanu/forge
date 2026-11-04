from enum import StrEnum


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class QuestionFormat(StrEnum):
    # Graded deterministically against the stored correct option.
    SINGLE_CHOICE = "single_choice"
    # Saved for review; requires AI evaluation, which is not implemented yet.
    FREE_TEXT = "free_text"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class EvaluationStatus(StrEnum):
    GRADED = "graded"
    PENDING_AI_EVALUATION = "pending_ai_evaluation"


class EvaluationMethod(StrEnum):
    DETERMINISTIC_CHOICE = "deterministic_choice"


class InterviewMode(StrEnum):
    TUTOR = "tutor"  # scaffolding and progressive hints
    GRILL = "grill"  # strict; no hints before a first attempt
    DEBUG = "debug"  # diagnose code and production failures
    ARCHITECT = "architect"  # design, scale, security and trade-offs


class InterviewStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class ChallengeStatus(StrEnum):
    OPEN = "open"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class TurnRole(StrEnum):
    INTERVIEWER = "interviewer"
    LEARNER = "learner"


class TurnKind(StrEnum):
    QUESTION = "question"
    ANSWER = "answer"
    DONT_KNOW = "dont_know"
    HINT_REQUEST = "hint_request"
    HINT = "hint"
    FOLLOW_UP = "follow_up"
    FEEDBACK = "feedback"
    NOTICE = "notice"


class InterviewEvaluationStatus(StrEnum):
    PENDING = "pending"  # answer saved, model call not finished
    EVALUATED = "evaluated"  # valid, validated evaluation
    UNGRADED = "ungraded"  # provider failed or output invalid; no score


class EvidenceSource(StrEnum):
    OBJECTIVE_ASSESSMENT = "objective_assessment"  # deterministic grading: verified
    AI_INTERVIEW = "ai_interview"  # model judgment: unverified
    SELF_REPORT = "self_report"  # "I don't know": counts only against mastery
    CODING_SUBMISSION = "coding_submission"  # hidden tests run in a verified sandbox: verified
    DESIGN_EVALUATION = "design_evaluation"  # AI architecture evaluation: unverified
    FAILURE_SCENARIO = "failure_scenario"  # AI-evaluated failure response: unverified
    INCIDENT_SIMULATION = "incident_simulation"  # deterministic scenario outcome: verified
    INCIDENT_REVIEW = "incident_review"  # AI root-cause analysis review: unverified
    ENGINEERING_TASK = "engineering_task"  # project hidden tests in a verified sandbox: verified


class EvidenceDimension(StrEnum):
    KNOWLEDGE = "knowledge"
    REASONING = "reasoning"
    DEBUGGING = "debugging"
    PRACTICAL = "practical"  # verified coding-lab test outcomes


class MasteryState(StrEnum):
    NOT_STARTED = "not_started"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LEARNING = "learning"
    DEVELOPING = "developing"  # beginner level demonstrated
    PROFICIENT = "proficient"  # intermediate level demonstrated
    MASTERED = "mastered"  # advanced demonstrated and retained


class TestVisibility(StrEnum):
    __test__ = False  # not a pytest test class
    PUBLIC = "public"  # inputs and expected values shown to the learner
    HIDDEN = "hidden"  # name only; definition never leaves the server


class JobKind(StrEnum):
    RUN = "run"  # public tests only; never mastery evidence
    SUBMIT = "submit"  # all tests; may become verified evidence


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"  # executed (or mock); results recorded
    FAILED = "failed"  # infrastructure failure after max attempts
    BLOCKED = "blocked"  # execution disabled or sandbox unverified


class TestOutcome(StrEnum):
    __test__ = False  # not a pytest test class
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_EXECUTED = "not_executed"  # mock backend


class ReviewStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    UNGRADED = "ungraded"


class DesignLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    SENIOR = "senior"


class DesignReviewMode(StrEnum):
    GUIDED = "guided"  # scaffolding and hints
    INTERVIEW = "interview"  # interview simulation
    SENIOR_REVIEW = "senior_review"  # demanding architecture review
    FAILURE_REVIEW = "failure_review"  # production failure focus
