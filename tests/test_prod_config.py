import runpy

import pytest

from app import config


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    for key in ("SESSION_COOKIE_SECURE", "SOCKETIO_ASYNC_MODE", "CLAIM_RATE_WINDOW", "CLAIM_RATE_LIMIT", "CA_CERT_PATH"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


@pytest.mark.parametrize("raw,secure", [
    (None, False), ("0", False), ("false", False), ("no", False), ("1", True), (" True ", True), ("YES", True),
])
def test_session_security(isolated_env, raw, secure):
    if raw is not None:
        isolated_env.setenv("SESSION_COOKIE_SECURE", raw)
    settings = config.Config()
    assert settings.SESSION_COOKIE_SECURE is secure
    assert settings.PREFERRED_URL_SCHEME == ("https" if secure else "http")


def test_async_mode_and_claim_settings(isolated_env, tmp_path):
    settings = config.Config()
    assert settings.SOCKETIO_ASYNC_MODE == "threading"
    assert (settings.CLAIM_RATE_LIMIT, settings.CLAIM_RATE_WINDOW) == (10, 600)
    assert settings.CA_CERT_PATH == str(tmp_path / "deploy/ca.crt")
    isolated_env.setenv("SOCKETIO_ASYNC_MODE", "gevent")
    isolated_env.setenv("SESSION_COOKIE_SECURE", "1")
    isolated_env.setenv("CLAIM_RATE_LIMIT", "3")
    isolated_env.setenv("CLAIM_RATE_WINDOW", "7")
    isolated_env.setenv("CA_CERT_PATH", "/example/ca.crt")
    settings = config.Config()
    assert settings.SOCKETIO_ASYNC_MODE == "gevent"
    assert (settings.CLAIM_RATE_LIMIT, settings.CLAIM_RATE_WINDOW) == (3, 7)
    assert settings.CA_CERT_PATH == "/example/ca.crt"
    testing = config.TestConfig()
    assert testing.SOCKETIO_ASYNC_MODE == "threading"
    assert testing.SESSION_COOKIE_SECURE is False


def test_gunicorn_transport_config(monkeypatch, tmp_path):
    conf = config.ROOT / "deploy/gunicorn.conf.py"
    monkeypatch.delenv("PORT", raising=False)
    cert, key = tmp_path / "server.crt", tmp_path / "server.key"
    monkeypatch.setenv("CERT_FILE", str(cert))
    monkeypatch.setenv("KEY_FILE", str(key))
    cert.touch()
    settings = runpy.run_path(str(conf))
    assert settings["bind"] == "0.0.0.0:5000"
    assert settings["workers"] == 1 and settings["worker_class"] == "gevent"
    assert "certfile" not in settings and "keyfile" not in settings
    monkeypatch.setenv("PORT", "5098")
    key.touch()
    settings = runpy.run_path(str(conf))
    assert settings["bind"] == "0.0.0.0:5098"
    assert (settings["certfile"], settings["keyfile"]) == (str(cert), str(key))
