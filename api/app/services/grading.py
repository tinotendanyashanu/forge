"""Answer evaluation.

Only objective questions are graded. Free-text answers are explicitly marked as
requiring AI evaluation; FORGE never infers correctness from keywords or answer
length, because that is not reliable evidence of understanding.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.db.enums import EvaluationMethod, EvaluationStatus, QuestionFormat
from app.db.models import QuestionOption


@dataclass(frozen=True)
class Evaluation:
    status: EvaluationStatus
    method: EvaluationMethod | None
    is_correct: bool | None
    score: Decimal | None


class GradingError(ValueError):
    pass


def evaluate(
    question_format: QuestionFormat,
    *,
    selected_option: QuestionOption | None,
    response_text: str | None,
) -> Evaluation:
    if question_format is QuestionFormat.SINGLE_CHOICE:
        if selected_option is None or response_text is not None:
            raise GradingError("Single-choice questions are answered with an option key")
        correct = selected_option.is_correct
        return Evaluation(
            status=EvaluationStatus.GRADED,
            method=EvaluationMethod.DETERMINISTIC_CHOICE,
            is_correct=correct,
            score=Decimal(1) if correct else Decimal(0),
        )

    if question_format is QuestionFormat.FREE_TEXT:
        if response_text is None or selected_option is not None:
            raise GradingError("Free-text questions are answered with response_text")
        return Evaluation(
            status=EvaluationStatus.PENDING_AI_EVALUATION,
            method=None,
            is_correct=None,
            score=None,
        )

    raise GradingError(f"Unsupported question format: {question_format}")


def summarise(evaluation: Evaluation, correct_key: str | None) -> str:
    """Learner-facing one-line outcome."""
    if evaluation.status is EvaluationStatus.PENDING_AI_EVALUATION:
        return (
            "Saved, not scored: written answers in assessments are never graded. Review your "
            "answer against the rubric below, or explain it in the AI interviewer, which evaluates written answers."
        )
    if evaluation.is_correct:
        return "Correct."
    return f"Not quite. The correct answer is {correct_key.upper() if correct_key else 'shown below'}."
