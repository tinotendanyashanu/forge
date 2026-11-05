"""Per-item presentation order for single-choice options.

Authored option keys must never reach the learner: authoring order is not
random (most correct answers were written as option ``b``), so showing options
in key order lets position alone predict the answer.

Each session item gets a deterministic permutation derived from the item id
and the option ids. Options are relabelled ``a``, ``b``, ``c`` ... by
displayed position. The server maps a displayed key back to the real option
when grading, and answers keep storing the real ``selected_option_id``, so
correctness, option ids and stored history are unaffected. The same item
always produces the same order, so refreshing never reshuffles a question.
"""

import hashlib
import uuid
from collections.abc import Sequence

from app.db.models import QuestionOption

PRESENTATION_KEYS = "abcdef"


def _rank(item_id: uuid.UUID, option: QuestionOption) -> bytes:
    return hashlib.sha256(f"{item_id}:{option.id}".encode()).digest()


def presented_options(
    item_id: uuid.UUID, options: Sequence[QuestionOption]
) -> list[tuple[str, QuestionOption]]:
    """Options in display order, each paired with its displayed key."""
    ordered = sorted(options, key=lambda o: _rank(item_id, o))
    return [(PRESENTATION_KEYS[i], o) for i, o in enumerate(ordered)]


def option_for_key(
    item_id: uuid.UUID, options: Sequence[QuestionOption], key: str
) -> QuestionOption | None:
    return next((o for k, o in presented_options(item_id, options) if k == key), None)


def key_for_option(
    item_id: uuid.UUID, options: Sequence[QuestionOption], option_id: int | None
) -> str | None:
    if option_id is None:
        return None
    return next((k for k, o in presented_options(item_id, options) if o.id == option_id), None)
