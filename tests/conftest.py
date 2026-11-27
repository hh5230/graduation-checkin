from itertools import count

import pytest
from sqlalchemy import text

from app import create_app
from app.extensions import db, get_redis, socketio
from app.models import init_database
from tests import login, success


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    with application.app_context():
        url = db.engine.url
        if url.get_backend_name() != "postgresql" or url.database != "graduation_test":
            pytest.fail("Test setup requires the PostgreSQL graduation_test database")
    init_database(application)
    return application


@pytest.fixture(autouse=True)
def clean_state(app):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql("TRUNCATE participants, audit_logs RESTART IDENTITY CASCADE")
        get_redis().delete("stats:v1")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app):
    client = app.test_client()
    login(client, "admin")
    return client


@pytest.fixture
def staff_client(app):
    client = app.test_client()
    login(client, "staff1")
    return client


@pytest.fixture
def make_participant(admin_client):
    numbers = count(1)

    def make(code=None, name=None, email=None):
        number = next(numbers)
        result = success(admin_client.post("/api/participants", json={
            "participant_code": code if code is not None else f"G{number:05}",
            "name": name if name is not None else f"Graduate {number}",
            "email": email if email is not None else f"grad{number}@example.org",
        }), 201)
        assert result["qr_token"]
        return result

    return make


@pytest.fixture
def socket_client(app, staff_client):
    client = socketio.test_client(app, flask_test_client=staff_client)
    try:
        assert client.is_connected()
        yield client
    finally:
        if client.is_connected():
            client.disconnect()


@pytest.fixture
def rows(app):
    """Read committed state independently of the request that wrote it."""
    def query(statement, **params):
        with app.app_context(), db.engine.connect() as conn:
            return conn.execute(text(statement), params).mappings().all()

    return query


@pytest.fixture
def participant_row(rows):
    def read(participant_id):
        row, = rows("SELECT * FROM participants WHERE id = :id", id=participant_id)
        return row

    return read


@pytest.fixture
def audit_for(rows):
    def read(participant_id):
        return rows("""
            SELECT action, operator_id FROM audit_logs
            WHERE participant_id = :id ORDER BY id
        """, id=participant_id)

    return read
