from datetime import datetime

import pytest

from tests import error, success


def test_lookup_by_code_token_and_scanner_prefix(staff_client, make_participant, participant_row):
    participant = make_participant(code="G-QR")
    for query in ({"code": "G-QR"}, {"token": participant["qr_token"]},
                  {"token": "GRAD:" + participant["qr_token"]}):
        found = success(staff_client.get("/api/lookup", query_string=query))
        assert found == {key: value for key, value in participant.items() if key != "qr_token"}
    assert participant_row(participant["id"])["status"] == "registered"


@pytest.mark.parametrize("path", ["/api/lookup", "/api/checkin", "/api/stage/queue"])
@pytest.mark.parametrize("query,status,code", [
    ({"token": "!not-a-token!"}, 404, "INVALID_QR"),
    ({"token": "A" * 16}, 404, "INVALID_QR"),
    ({"code": "ABSENT"}, 404, "PARTICIPANT_NOT_FOUND"),
    ({"code": "EXISTING", "token": "A" * 16}, 400, "VALIDATION_ERROR"),
    ({}, 400, "VALIDATION_ERROR"),
])
def test_invalid_identifier(staff_client, make_participant, participant_row, audit_for, path, query, status, code):
    participant = make_participant(code="EXISTING")
    if path == "/api/lookup":
        response = staff_client.get(path, query_string=query)
    else:
        response = staff_client.post(path, json=query)
    details = error(response, status, code)["details"]
    if code == "VALIDATION_ERROR":
        assert details["fields"]
    if code == "PARTICIPANT_NOT_FOUND":
        assert details["code"] == query["code"]
    assert participant_row(participant["id"])["status"] == "registered"
    assert [row["action"] for row in audit_for(participant["id"])] == ["create"]


def test_checkin_preserves_first_operator_and_timestamp(admin_client, staff_client, make_participant,
                                                       participant_row, audit_for):
    participant = make_participant()
    pid = participant["id"]
    staff = success(staff_client.get("/api/auth/me"))["user"]
    operator = {"id": staff["id"], "name": staff["display_name"]}
    first = success(staff_client.post("/api/checkin", json={"token": "GRAD:" + participant["qr_token"]}))
    stored = participant_row(pid)
    assert first["id"] == pid
    assert first["status"] == stored["status"] == "checked_in"
    assert first["checked_in_by"] == operator
    assert stored["checked_in_by"] == staff["id"]
    assert datetime.fromisoformat(first["checked_in_at"]) == stored["checked_in_at"]
    assert "qr_token" not in first

    retry = admin_client.post("/api/checkin", json={"code": participant["participant_code"]})
    details = error(retry, 409, "ALREADY_CHECKED_IN")["details"]
    assert details["checked_in_at"] == first["checked_in_at"]
    assert details["checked_in_by"] == operator
    assert details["participant"] == first
    assert participant_row(pid) == stored
    assert [row for row in audit_for(pid) if row["action"] == "check_in"] == [
        {"action": "check_in", "operator_id": staff["id"]}
    ]
