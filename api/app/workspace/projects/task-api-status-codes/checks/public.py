"""Public checks: trusted code that drives the learner's app and returns raw
observations. FORGE compares them with the expected values outside the sandbox.

Each step is [method, path, json_body_or_null, mode]. Modes: "full" returns
[status, body], "status" returns [status], "body" returns [body] and "skip"
returns null (setup steps, so one bug doesn't fail unrelated tests).
"""


def _client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def _body(response):
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text[:200]


def http(steps):
    out = []
    with _client() as client:
        for method, path, body, mode in steps:
            r = client.request(method, path, json=body)
            if mode == "skip":
                out.append(None)
            elif mode == "status":
                out.append([r.status_code])
            elif mode == "body":
                out.append([_body(r)])
            else:
                out.append([r.status_code, _body(r)])
    return out
