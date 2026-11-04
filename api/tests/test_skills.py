from fastapi.testclient import TestClient

REQUIRED_SKILLS = {
    "python",
    "fastapi",
    "react",
    "typescript",
    "sql",
    "http",
    "testing",
    "system-design",
}


def test_lists_required_skills_with_every_difficulty(client: TestClient) -> None:
    res = client.get("/api/v1/skills")
    assert res.status_code == 200
    skills = res.json()
    # The curriculum defines more skills; these are the ones with question content.
    assert REQUIRED_SKILLS <= {s["slug"] for s in skills}
    assert [s["position"] for s in skills] == sorted(s["position"] for s in skills)
    assert sum(s["question_count"] for s in skills) >= 30
    for s in (s for s in skills if s["slug"] in REQUIRED_SKILLS):
        counts = s["questions_by_difficulty"]
        assert all(counts[d] >= 1 for d in ("beginner", "intermediate", "advanced")), s["slug"]


def test_skill_detail_lists_topics(client: TestClient) -> None:
    res = client.get("/api/v1/skills/sql")
    assert res.status_code == 200
    body = res.json()
    assert body["topic_count"] == len(body["topics"]) >= 1
    assert sum(t["question_count"] for t in body["topics"]) == body["question_count"]


def test_unknown_skill_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/skills/cobol").status_code == 404


def test_content_endpoints_do_not_require_a_learner(client: TestClient) -> None:
    assert client.get("/api/v1/skills").status_code == 200
