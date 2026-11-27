import base64
from unittest.mock import patch

import pytest
from jinja2 import TemplateNotFound
from redis.exceptions import ConnectionError
from sqlalchemy import update

from app.config import ROOT
from app.extensions import db, get_redis
from app.models import Participant
from tests import error, success

CLAIM = "/api/public/claim"


@pytest.fixture(autouse=True)
def claim_counters(app):
    with app.app_context():
        redis = get_redis()

    def clear():
        keys = list(redis.scan_iter(match="ratelimit:claim:*"))
        if keys:
            redis.delete(*keys)

    clear()
    try:
        yield redis
    finally:
        clear()


def test_claim_matches_admin_png_without_side_effects(
    client, admin_client, make_participant, socket_client, participant_row, audit_for,
):
    p = make_participant()
    before = participant_row(p["id"]), audit_for(p["id"])
    socket_client.get_received()  # discard the create notification
    response = client.post(CLAIM, json={
        "participant_code": f' {p["participant_code"].lower()} ', "email": f' {p["email"].upper()} ',
    })
    data = success(response)
    assert response.cache_control.no_store
    assert set(data) == {"participant", "qr_png_base64", "qr_filename"}
    assert data["participant"] == {key: p[key] for key in ("participant_code", "name", "status")}
    assert data["qr_filename"] == f'QR-{p["participant_code"]}.png'
    png = base64.b64decode(data["qr_png_base64"], validate=True)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert png == admin_client.get(f'/api/participants/{p["id"]}/qr.png').data
    assert p["qr_token"] not in response.get_data(as_text=True)
    assert (participant_row(p["id"]), audit_for(p["id"])) == before
    assert socket_client.get_received() == []


def test_claim_matches_mixed_case_stored_registration(app, client, make_participant):
    p = make_participant()
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(update(Participant).where(Participant.id == p["id"]).values(
            participant_code="Grad01", email="Graduate@Example.ORG",
        ))
    data = success(client.post(CLAIM, json={"participant_code": "grad01", "email": "graduate@example.org"}))
    assert data["participant"]["participant_code"] == "Grad01"


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_claim_not_found_is_identical(client, make_participant, lang):
    p, other = make_participant(), make_participant()

    def attempt(code):
        return client.post(CLAIM, headers={"X-Lang": lang},
                           json={"participant_code": code, "email": other["email"]})

    mismatch = attempt(p["participant_code"])
    unknown = attempt("UNKNOWN")
    assert error(mismatch, 404, "CLAIM_NOT_FOUND")["details"] == {}
    assert unknown.status_code == 404 and mismatch.data == unknown.data


@pytest.mark.parametrize("payload,fields", [
    ({}, {"participant_code": "required", "email": "required"}),
    ({"participant_code": " ", "email": "a@b.org"}, {"participant_code": "required"}),
    ({"participant_code": [], "email": 1}, {"participant_code": "invalid", "email": "invalid"}),
    ({"participant_code": "a/b", "email": "bad"}, {"participant_code": "invalid", "email": "invalid"}),
    ({"participant_code": "A", "email": "\ud800@example.org"}, {"email": "invalid"}),
    ([], {"body": "expected_object"}),
])
def test_validation(client, payload, fields):
    problem = error(client.post(CLAIM, json=payload), 400, "VALIDATION_ERROR")
    assert problem["details"]["fields"] == fields


def test_json_required(client):
    error(client.post(CLAIM, data={"participant_code": "A"}), 415, "UNSUPPORTED_MEDIA_TYPE")
    malformed = client.post(CLAIM, data="{", content_type="application/json")
    assert error(malformed, 400, "VALIDATION_ERROR")["details"]["fields"] == {"body": "invalid_json"}


def test_fixed_window_counts_all_attempts_by_peer_ip(client, make_participant, claim_counters, monkeypatch, app):
    monkeypatch.setitem(app.config, "CLAIM_RATE_LIMIT", 10)
    monkeypatch.setitem(app.config, "CLAIM_RATE_WINDOW", 600)
    p = make_participant()
    valid = {"participant_code": p["participant_code"], "email": p["email"]}
    key = "ratelimit:claim:127.0.0.1"
    success(client.post(CLAIM, json=valid))
    assert 0 < claim_counters.ttl(key) <= 600
    claim_counters.expire(key, 90)
    error(client.post(CLAIM, data="text"), 415, "UNSUPPORTED_MEDIA_TYPE")
    for _ in range(8):
        error(client.post(CLAIM, json={**valid, "participant_code": "UNKNOWN"}), 404, "CLAIM_NOT_FOUND")
    blocked = client.post(CLAIM, json=valid, headers={"X-Forwarded-For": "192.0.2.7"})
    retry = error(blocked, 429, "RATE_LIMITED")["details"]["retry_after"]
    assert 0 < retry <= 90
    assert claim_counters.get(key) == "11"
    success(client.post(CLAIM, json=valid, environ_overrides={"REMOTE_ADDR": "192.0.2.7"}))


def test_redis_outage_allows_claim_and_logs_warning(client, make_participant, claim_counters, caplog):
    p = make_participant()
    with patch.object(claim_counters, "pipeline", side_effect=ConnectionError("disconnected")):
        success(client.post(CLAIM, json={"participant_code": p["participant_code"], "email": p["email"]}))
    assert any(r.levelname == "WARNING" and "count_claim" in r.getMessage() for r in caplog.records)


def test_claim_page_is_public(app, client):
    try:
        app.jinja_env.get_template("claim.html")
    except TemplateNotFound as exc:
        if exc.name != "claim.html":
            raise
        pytest.skip("Task E claim.html is not present in this checkout yet")
    assert client.get("/claim").status_code == 200


def test_ca_download(app, client, monkeypatch):
    cert = ROOT / "deploy/ca.crt"
    monkeypatch.setitem(app.config, "CA_CERT_PATH", str(cert))
    response = client.get("/ca.crt")
    assert response.status_code == 200
    assert response.content_type == "application/x-x509-ca-cert"
    assert response.headers["Content-Disposition"] == 'attachment; filename="graduation-ca.crt"'
    assert response.data == cert.read_bytes()


def test_ca_missing(app, client, monkeypatch, tmp_path):
    monkeypatch.setitem(app.config, "CA_CERT_PATH", str(tmp_path / "missing.crt"))
    assert client.get("/ca.crt").status_code == 404
