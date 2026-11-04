from fastapi.testclient import TestClient


def test_health_reports_database(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["database"] == "ok"


def test_cors_allows_local_frontend_only(client: TestClient) -> None:
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


def test_oversized_request_bodies_are_rejected(client) -> None:
    res = client.post("/api/v1/learners", content=b"x" * 2_100_000, headers={"content-type": "application/json"})
    assert res.status_code == 413

    def chunks():
        for _ in range(30):
            yield b"y" * 100_000

    # A streamed body without Content-Length is cut off while it is being read.
    lid = client.post("/api/v1/learners").json()["id"]
    res = client.post("/api/v1/assessments", content=chunks(),
                      headers={"content-type": "application/json", "X-Learner-Id": lid})
    assert res.status_code == 413
    assert client.post("/api/v1/learners").status_code == 201  # normal requests unaffected
