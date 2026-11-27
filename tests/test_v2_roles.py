import pytest
from sqlalchemy import select, update
from werkzeug.security import generate_password_hash

from app.extensions import db, socketio
from app.models import User, init_database
from tests import error, success


@pytest.mark.parametrize("username,password,name,role,home", [
    ("admin", "admin123", "Administrator", "admin", "/admin"),
    ("staff1", "staff123", "Staff One", "staff", "/entry"),
    ("checkin1", "checkin123", "Entrance One", "checkin", "/entry"),
    ("stage1", "stage123", "Stage One", "stage", "/stage"),
    ("viewer1", "viewer123", "Organizer", "viewer", "/dashboard"),
])
def test_role_matrix(app, client, username, password, name, role, home):
    user = success(client.post("/api/auth/login", json={"username": username, "password": password}))["user"]
    assert (user["role"], user["display_name"], user["home"]) == (role, name, home)
    assert success(client.get("/api/auth/me")) == {"user": user}
    for path in ("/", "/login"):
        response = client.get(path)
        assert response.status_code == 302 and response.location == home
    socket = socketio.test_client(app, flask_test_client=client)
    try:
        assert socket.is_connected()
    finally:
        if socket.is_connected():
            socket.disconnect()

    checkin = role in {"admin", "staff", "checkin"}
    stage = role in {"admin", "staff", "stage"}
    admin = role == "admin"
    display = stage or role == "viewer"
    for path, allowed in [("/admin", admin), ("/admin/qr-sheet", admin), ("/entry", checkin), ("/stage", stage),
                          ("/dashboard", True), ("/display", display)]:
        response = client.get(path)
        assert response.status_code == (200 if allowed else 403), path

    # Expected business-level statuses prove the request passed the appropriate role gate.
    for method, path, allowed, status in [
        ("get", "/api/participants", admin, 200),
        ("post", "/api/participants", admin, 400),
        ("get", "/api/participants/1", admin, 404),
        ("patch", "/api/participants/1", admin, 400),
        ("post", "/api/participants/1/regenerate-qr", admin, 404),
        ("get", "/api/participants/1/qr.png", admin, 404),
        ("post", "/api/participants/import", admin, 400),
        ("get", "/api/participants/1/timeline", admin, 404),
        ("post", "/api/participants/1/undo", admin, 400),
        ("get", "/api/export/records.csv", admin, 200),
        ("get", "/api/lookup?code=missing", checkin or stage, 404),
        ("get", "/api/checkin/search?q=x", checkin, 200),
        ("post", "/api/checkin", checkin, 400),
        ("post", "/api/stage/queue", stage, 400),
        ("post", "/api/stage/call-next", stage, 409),
        ("post", "/api/stage/complete", stage, 409),
        ("post", "/api/stage/requeue", stage, 400),
        ("get", "/api/stage/state", display, 200),
        ("get", "/api/stats", True, 200),
        ("get", "/api/stats/timeline", True, 200),
    ]:
        response = client.open(path, method=method.upper(), json={} if method != "get" else None, buffered=True)
        if allowed:
            assert response.status_code == status, path
        else:
            assert error(response, 403, "FORBIDDEN")["details"]["role"] == role


def test_init_preserves_changed_default_password_and_inactive_account(app, client):
    with app.app_context(), db.engine.begin() as conn:
        original = conn.execute(select(User.password_hash, User.is_active).where(User.username == "viewer1")).one()
    changed = generate_password_hash("changed-after-deployment")
    account = update(User).where(User.username == "viewer1")
    try:
        with app.app_context(), db.engine.begin() as conn:
            conn.execute(account.values(password_hash=changed, is_active=False))
        init_database(app)
        init_database(app)
        with app.app_context(), db.engine.begin() as conn:
            assert conn.execute(select(User.password_hash, User.is_active).where(User.username == "viewer1")).one() == (
                changed, False,
            )
        with client.session_transaction() as session:
            with app.app_context():
                session["user_id"] = db.session.scalar(select(User.id).where(User.username == "viewer1"))
        assert not socketio.test_client(app, flask_test_client=client).is_connected()
        error(client.get("/api/stats"), 401, "UNAUTHORIZED")
    finally:
        with app.app_context(), db.engine.begin() as conn:
            conn.execute(account.values(password_hash=original.password_hash, is_active=original.is_active))
