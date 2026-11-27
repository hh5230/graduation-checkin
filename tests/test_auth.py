import pytest

from tests import error, login, success


ADMIN_ENDPOINTS = [
    ("GET", "/api/participants", None),
    ("POST", "/api/participants", {"participant_code": "NEW", "email": "new@example.org", "name": "New"}),
    ("GET", "/api/participants/{id}", None),
    ("PATCH", "/api/participants/{id}", {"name": "Changed"}),
    ("POST", "/api/participants/{id}/regenerate-qr", {}),
    ("GET", "/api/participants/{id}/qr.png", None),
]
PROTECTED_ENDPOINTS = ADMIN_ENDPOINTS + [
    ("POST", "/api/auth/logout", {}),
    ("GET", "/api/auth/me", None),
    ("GET", "/api/lookup?code=EXISTING", None),
    ("POST", "/api/checkin", {"code": "EXISTING"}),
    ("POST", "/api/stage/queue", {"code": "EXISTING"}),
    ("GET", "/api/stage/state", None),
    ("POST", "/api/stage/call-next", {}),
    ("POST", "/api/stage/complete", {}),
    ("GET", "/api/stats", None),
]


def test_login_me_logout(client, rows):
    user = login(client, "staff1")
    stored, = rows("SELECT id, username, display_name, role FROM users WHERE username = 'staff1'")
    assert user == {**stored, "home": "/entry"}
    assert user["role"] == "staff"
    assert success(client.get("/api/auth/me")) == {"user": user}
    assert success(client.post("/api/auth/logout", json={})) == {}
    error(client.get("/api/auth/me"), 401, "UNAUTHORIZED")


def test_bad_password_and_localized_envelope(client):
    messages = []
    for lang in ("en", "zh"):
        response = client.post("/api/auth/login", headers={"X-Lang": lang},
                               json={"username": "staff1", "password": "incorrect"})
        problem = error(response, 401, "INVALID_CREDENTIALS")
        messages.append(problem["message"])
        error(client.get("/api/auth/me"), 401, "UNAUTHORIZED")
    assert messages[0] != messages[1]


def assert_access_denied(client, method, path, body, make_participant, rows, status, code):
    participant = make_participant(code="EXISTING")
    before = rows("SELECT * FROM participants")
    response = client.open(path.format(id=participant["id"]), method=method, json=body)
    error(response, status, code)
    assert rows("SELECT * FROM participants") == before
    assert rows("SELECT action FROM audit_logs") == [{"action": "create"}]


@pytest.mark.parametrize("method,path,body", PROTECTED_ENDPOINTS)
def test_anonymous_protected_endpoints(client, method, path, body, make_participant, rows):
    assert_access_denied(client, method, path, body, make_participant, rows, 401, "UNAUTHORIZED")


@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
def test_staff_admin_endpoints(staff_client, method, path, body, make_participant, rows):
    assert_access_denied(staff_client, method, path, body, make_participant, rows, 403, "FORBIDDEN")


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/auth/login"),
    *[(method, path) for method, path, _ in PROTECTED_ENDPOINTS if method in ("POST", "PATCH")],
])
def test_non_json_write(admin_client, make_participant, rows, method, path):
    participant = make_participant()
    before = rows("SELECT * FROM participants")
    response = admin_client.open(path.format(id=participant["id"]), method=method,
                                 data={"name": "Form submission"})
    error(response, 415, "UNSUPPORTED_MEDIA_TYPE")
    assert rows("SELECT * FROM participants") == before
    assert rows("SELECT action FROM audit_logs") == [{"action": "create"}]
    assert success(admin_client.get("/api/auth/me"))["user"]["role"] == "admin"


@pytest.mark.parametrize("content_type", ["text/plain", None], ids=["text-plain", "missing-content-type"])
@pytest.mark.parametrize("path", [
    "/api/auth/logout",
    "/api/participants/{id}/regenerate-qr",
    "/api/stage/call-next",
    "/api/stage/complete",
])
def test_non_json_empty_post(admin_client, staff_client, make_participant, participant_row, audit_for,
                             path, content_type):
    participant = make_participant()
    if path.startswith("/api/stage/"):
        body = {"code": participant["participant_code"]}
        success(staff_client.post("/api/checkin", json=body))
        success(staff_client.post("/api/stage/queue", json=body))
        if path == "/api/stage/complete":
            success(staff_client.post("/api/stage/call-next", json={}))
    before = participant_row(participant["id"])
    audits = audit_for(participant["id"])
    response = admin_client.post(path.format(id=participant["id"]), data=b"", content_type=content_type)
    error(response, 415, "UNSUPPORTED_MEDIA_TYPE")
    assert participant_row(participant["id"]) == before
    assert audit_for(participant["id"]) == audits
    assert success(admin_client.get("/api/auth/me"))["user"]["role"] == "admin"
