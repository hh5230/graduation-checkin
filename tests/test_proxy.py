import json

import pytest
from flask import request
from flask_socketio import SocketIO

import app
from app import config


@pytest.fixture
def proxy_env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)  # Ignore deployment .env values.
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("TRUST_PROXY", raising=False)
    monkeypatch.delenv("PROXY_HOPS", raising=False)
    # Each factory call installs a server on the extension. Isolate the suite's server.
    monkeypatch.setattr(app, "socketio", SocketIO(monitor_clients=False))
    return monkeypatch


@pytest.mark.parametrize("trust,hops,expected", [
    (None, None, ("http", "localhost", "127.0.0.1")),
    ("1", None, ("https", "checkin.example.com", "203.0.113.9")),
    (" True ", "2", ("https", "checkin.example.com", "203.0.113.9")),
    ("YES", None, ("https", "checkin.example.com", "203.0.113.9")),
])
def test_forwarded_request(proxy_env, trust, hops, expected):
    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "checkin.example.com",
        "X-Forwarded-For": "203.0.113.9",
    }
    if trust is not None:
        proxy_env.setenv("TRUST_PROXY", trust)
    if hops is not None:
        proxy_env.setenv("PROXY_HOPS", hops)
        headers["X-Forwarded-Proto"] += ", http"
        headers["X-Forwarded-Host"] += ", internal.example.com"
        headers["X-Forwarded-For"] += ", 192.0.2.1"

    with app.create_app("testing").test_client() as client:
        client.get("/api/auth/me", base_url="http://localhost", headers=headers)
        assert (request.scheme, request.host, request.remote_addr) == expected


def test_engineio_polling_behind_proxy(proxy_env):
    proxy_env.setenv("TRUST_PROXY", "1")
    application = app.create_app("testing")
    client = application.test_client()
    path = "/socket.io/?EIO=4&transport=polling"
    headers = {
        "Origin": "https://checkin.example.com",
        "Host": "checkin.example.com",
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "checkin.example.com",
        "X-Forwarded-For": "203.0.113.9",
    }
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.data.startswith(b"0")  # Engine.IO OPEN packet
    sid = json.loads(response.data[1:])["sid"]
    try:
        environ = application.extensions["socketio"].server.environ[sid]
        assert (environ["wsgi.url_scheme"], environ["HTTP_HOST"], environ["REMOTE_ADDR"]) == (
            "https", "checkin.example.com", "203.0.113.9",
        )
    finally:
        client.post(f"{path}&sid={sid}", headers=headers, data="1")  # Engine.IO CLOSE

    headers["Origin"] = "https://other.example.com"
    assert client.get(path, headers=headers).status_code == 400
