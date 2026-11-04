import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.enums import EvaluationStatus, QuestionFormat
from app.db.models import QuestionOption
from app.db.session import create_engine
from app.seed.schema import SeedQuestion, SeedSkillFile, load_seed_files
from app.services.grading import GradingError, evaluate

# ---------------------------------------------------------------- grading


def test_grading_choice_uses_stored_correctness() -> None:
    right = QuestionOption(key="b", text="x", is_correct=True)
    wrong = QuestionOption(key="a", text="y", is_correct=False)
    assert evaluate(QuestionFormat.SINGLE_CHOICE, selected_option=right, response_text=None).is_correct
    result = evaluate(QuestionFormat.SINGLE_CHOICE, selected_option=wrong, response_text=None)
    assert result.is_correct is False and result.score == 0


def test_grading_never_scores_free_text() -> None:
    result = evaluate(
        QuestionFormat.FREE_TEXT, selected_option=None, response_text="correct answer"
    )
    assert result.status is EvaluationStatus.PENDING_AI_EVALUATION
    assert result.is_correct is None and result.score is None


def test_grading_rejects_mismatched_input() -> None:
    with pytest.raises(GradingError):
        evaluate(QuestionFormat.SINGLE_CHOICE, selected_option=None, response_text="b")
    with pytest.raises(GradingError):
        evaluate(
            QuestionFormat.FREE_TEXT,
            selected_option=QuestionOption(key="a", text="", is_correct=True),
            response_text=None,
        )


# ---------------------------------------------------------------- seed content


def test_seed_content_meets_editorial_requirements() -> None:
    files = load_seed_files()
    questions = [q for f in files for q in f.questions]
    assert len(questions) >= 30
    for q in questions:
        assert q.rubric and q.expected_concepts and q.misconceptions and q.resources, q.slug
    formats = {q.format for q in questions}
    assert formats == {QuestionFormat.SINGLE_CHOICE, QuestionFormat.FREE_TEXT}


BASE_Q = {
    "slug": "q",
    "topic": "t",
    "difficulty": "beginner",
    "format": "single_choice",
    "title": "Title",
    "prompt": "A prompt long enough",
    "options": [{"key": "a", "text": "1", "correct": True}, {"key": "b", "text": "2"}],
    "explanation": "An explanation that is long enough.",
    "acceptance_criteria": "States the key fact and why.",
    "rubric": ["one", "two"],
    "expected_concepts": ["c"],
    "misconceptions": ["m"],
    "resources": [{"title": "Docs", "url": "https://example.com"}],
    "estimated_minutes": 2,
}


@pytest.mark.parametrize(
    "change",
    [
        {"options": [{"key": "a", "text": "1", "correct": True}, {"key": "b", "text": "2", "correct": True}]},
        {"options": [{"key": "a", "text": "1"}, {"key": "b", "text": "2"}]},
        {"format": "free_text"},
        {"rubric": ["only one"]},
        {"misconceptions": []},
        {"resources": [{"title": "Docs", "url": "http://insecure.example"}]},
    ],
    ids=["two-correct", "none-correct", "free-text-with-options", "thin-rubric", "no-misconceptions", "http-url"],
)
def test_seed_schema_rejects_bad_questions(change: dict) -> None:
    with pytest.raises(ValueError):
        SeedQuestion.model_validate({**BASE_Q, **change})


def test_seed_schema_requires_every_difficulty() -> None:
    with pytest.raises(ValueError, match="no questions for"):
        SeedSkillFile.model_validate(
            {
                "skill": {"slug": "s", "title": "Skill", "summary": "A summary.", "description": "A description."},
                "topics": [{"slug": "t", "title": "Topic"}],
                "questions": [BASE_Q],
            }
        )


def test_seed_loader_rejects_too_little_content(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text(json.dumps({"skill": {}, "topics": [], "questions": []}))
    with pytest.raises(ValueError):
        load_seed_files(tmp_path)


# ---------------------------------------------------------------- database constraints


def test_database_rejects_answer_with_option_from_another_question(settings) -> None:
    """The composite FK blocks pairing an answer with another question's option."""

    async def attempt() -> None:
        engine = create_engine(settings.require_database_url())
        try:
            async with engine.begin() as conn:
                await conn.execute(text("TRUNCATE learners CASCADE"))
                learner = (await conn.execute(text("INSERT INTO learners DEFAULT VALUES RETURNING id"))).scalar()
                q = (await conn.execute(text(
                    "SELECT id, skill_id FROM questions WHERE format='single_choice' ORDER BY id LIMIT 1"
                ))).one()
                foreign_option = (await conn.execute(text(
                    "SELECT id FROM question_options WHERE question_id <> :q LIMIT 1"
                ), {"q": q.id})).scalar()
                session = (await conn.execute(text(
                    "INSERT INTO assessment_sessions (learner_id, skill_id, difficulty, target_question_count) "
                    "VALUES (:l, :s, 'beginner', 1) RETURNING id"
                ), {"l": learner, "s": q.skill_id})).scalar()
                item = (await conn.execute(text(
                    "INSERT INTO session_items (session_id, question_id, position) "
                    "VALUES (:s, :q, 1) RETURNING id"
                ), {"s": session, "q": q.id})).scalar()
                await conn.execute(text(
                    "INSERT INTO answers (session_item_id, question_id, learner_id, selected_option_id) "
                    "VALUES (:i, :q, :l, :o)"
                ), {"i": item, "q": q.id, "l": learner, "o": foreign_option})
        finally:
            await engine.dispose()

    with pytest.raises(IntegrityError, match="fk_answers_option_question"):
        asyncio.run(attempt())
