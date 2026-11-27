"""Assertions shared by the graduation API integration tests."""


def json_response(response, status):
    assert response.status_code == status, f"Expected HTTP {status}, received {response.status}"
    assert response.is_json, f"Expected JSON, received {response.mimetype}"
    return response.get_json()


def success(response, status=200):
    body = json_response(response, status)
    assert body["ok"] is True
    return body["data"]


def error(response, status, code):
    body = json_response(response, status)
    assert set(body) == {"ok", "error"}
    assert body["ok"] is False
    problem = body["error"]
    assert set(problem) == {"code", "message", "details"}
    assert problem["code"] == code, f"Expected {code}, received {problem['code']}"
    assert isinstance(problem["message"], str) and problem["message"].strip()
    assert isinstance(problem["details"], dict)
    return problem


def login(client, username):
    password = "admin123" if username == "admin" else "staff123"
    return success(client.post("/api/auth/login", json={
        "username": username, "password": password,
    }))["user"]


def check_in(client, participant):
    return success(client.post("/api/checkin", json={"code": participant["participant_code"]}))


def enqueue(client, participant):
    return success(client.post("/api/stage/queue", json={"token": participant["qr_token"]}))
