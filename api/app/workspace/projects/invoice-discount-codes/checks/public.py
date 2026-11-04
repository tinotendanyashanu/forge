"""Public checks for the backend. Each test gets a fresh SQLite file in /tmp.

Steps are [method, path, json_body_or_null, mode]. Modes: "full" -> [status, body],
"status" -> [status], "skip" -> null, or a list of keys -> [status, {key: body[key]}]
(missing keys come back as "<missing>").
"""

import os
import tempfile

MISSING = "<missing>"


def fresh_db() -> str:
    fd, path = tempfile.mkstemp(dir="/tmp", suffix=".db")
    os.close(fd)
    os.unlink(path)
    return path


def client(db_path=None):
    from fastapi.testclient import TestClient

    from invoices.main import create_app

    return TestClient(create_app(db_path or fresh_db()), raise_server_exceptions=False)


def body_of(response):
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text[:200]


def observe(response, mode):
    if mode == "skip":
        return None
    if mode == "status":
        return [response.status_code]
    body = body_of(response)
    if isinstance(mode, list):
        if not isinstance(body, dict):
            return [response.status_code, body]
        return [response.status_code, {k: body.get(k, MISSING) for k in mode}]
    return [response.status_code, body]


def http(steps):
    with client() as c:
        return [observe(c.request(method, path, json=body), mode) for method, path, body, mode in steps]
