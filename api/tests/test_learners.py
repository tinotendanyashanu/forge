import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import new_learner


def test_create_and_resolve_learner(client: TestClient) -> None:
    headers = new_learner(client)
    res = client.get("/api/v1/learners/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["id"] == headers["X-Learner-Id"]


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Learner-Id": "not-a-uuid"}, {"X-Learner-Id": str(uuid.uuid4())}],
    ids=["missing", "malformed", "unknown"],
)
def test_learner_scoped_endpoints_reject_bad_identity(
    client: TestClient, headers: dict[str, str]
) -> None:
    for method, path in [
        ("GET", "/api/v1/learners/me"),
        ("GET", "/api/v1/progress"),
        ("GET", "/api/v1/answers"),
        ("GET", "/api/v1/assessments"),
    ]:
        assert client.request(method, path, headers=headers).status_code == 401, path
    res = client.post(
        "/api/v1/assessments",
        json={"skill_slug": "python", "difficulty": "beginner"},
        headers=headers,
    )
    assert res.status_code == 401
