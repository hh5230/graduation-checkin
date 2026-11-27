import re

import pytest

from tests import check_in, error, success


def test_create_get_and_patch(admin_client, make_participant, participant_row, audit_for):
    created = make_participant(code="grad-abc", name="Ada", email="AdA@Example.OrG")
    pid = created["id"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{16,64}", created["qr_token"])
    expected = {"participant_code": "GRAD-ABC", "email": "ada@example.org", "name": "Ada",
                "status": "registered", "qr_token": created["qr_token"]}
    stored = participant_row(pid)
    for key, value in expected.items():
        assert created[key] == stored[key] == value
    assert success(admin_client.get(f"/api/participants/{pid}")) == created

    patch = {"name": "Ada Li", "email": "ADA.LI@example.org", "participant_code": "grad-new"}
    updated = success(admin_client.patch(f"/api/participants/{pid}", json=patch))
    stored = participant_row(pid)
    for key, value in {"name": "Ada Li", "email": "ada.li@example.org", "participant_code": "GRAD-NEW",
                       "status": "registered", "qr_token": created["qr_token"]}.items():
        assert updated[key] == stored[key] == value
    assert success(admin_client.get(f"/api/participants/{pid}")) == updated
    assert [entry["action"] for entry in audit_for(pid)] == ["create", "update"]


@pytest.mark.parametrize("field,value", [
    ("name", None), ("email", None), ("participant_code", None),
    ("name", "   "), ("email", "no-domain"), ("participant_code", "X" * 33),
])
def test_invalid_profile(admin_client, rows, field, value):
    profile = {"participant_code": "GRAD-A", "name": "Ada", "email": "ada@example.org"}
    if value is None:
        del profile[field]
    else:
        profile[field] = value
    problem = error(admin_client.post("/api/participants", json=profile), 400, "VALIDATION_ERROR")
    assert problem["details"]["fields"][field]
    assert rows("SELECT id FROM participants") == []
    assert rows("SELECT id FROM audit_logs") == []


@pytest.mark.parametrize("field,value,code", [
    ("participant_code", "TAKEN", "DUPLICATE_CODE"),
    ("email", "ALICE@example.org", "DUPLICATE_EMAIL"),
])
def test_uniqueness(admin_client, make_participant, rows, field, value, code):
    existing = make_participant(code="TAKEN", email="alice@example.org")
    profile = {"participant_code": "FREE", "name": "Bob", "email": "bob@example.org", field: value}
    before = rows("SELECT * FROM participants")
    error(admin_client.post("/api/participants", json=profile), 409, code)
    assert rows("SELECT * FROM participants") == before

    other = make_participant(code="FREE", email="bob@example.org")
    before = rows("SELECT * FROM participants ORDER BY id")
    error(admin_client.patch(f"/api/participants/{other['id']}", json={field: value}), 409, code)
    assert rows("SELECT * FROM participants ORDER BY id") == before
    assert rows("SELECT participant_id, action FROM audit_logs ORDER BY id") == [
        {"participant_id": p["id"], "action": "create"} for p in (existing, other)
    ]


def test_patch_cannot_set_status(admin_client, make_participant, participant_row):
    participant = make_participant()
    pid = participant["id"]
    response = admin_client.patch(f"/api/participants/{pid}", json={"name": "Ada", "status": "completed"})
    if response.status_code == 200:
        assert success(response)["status"] == "registered"
    else:
        assert "status" in error(response, 400, "VALIDATION_ERROR")["details"]["fields"]
    stored = participant_row(pid)
    assert stored["status"] == "registered"
    assert all(stored[field] is None for field in ("checked_in_at", "queued_at", "called_at", "completed_at"))


def test_search_filter_and_pagination(admin_client, staff_client, make_participant):
    first = make_participant(code="GRAD-ONE", email="ada@alumni.org", name="Alexandra")
    second = make_participant(code="SPECIAL-TWO", email="bee@example.org", name="Benjamin")
    third = make_participant(code="GRAD-THREE", email="cee@example.org", name="Chen")
    check_in(staff_client, second)

    def listing(**query):
        return success(admin_client.get("/api/participants", query_string=query))

    for query, expected in [
        ({"q": "XAN"}, [first]), ({"q": "@ALUMNI"}, [first]), ({"q": "cial-t"}, [second]),
        ({"status": "checked_in"}, [second]), ({"status": "registered"}, [first, third]),
        ({"q": "grad-", "status": "checked_in"}, []),
    ]:
        result = listing(**query)
        assert [p["id"] for p in result["items"]] == [p["id"] for p in expected]
        assert result["total"] == len(expected)

    for page, expected in ((1, [first, second]), (2, [third]), (3, [])):
        result = listing(page=page, per_page=2)
        assert (result["page"], result["per_page"], result["total"]) == (page, 2, 3)
        assert [p["qr_token"] for p in result["items"]] == [p["qr_token"] for p in expected]
    response = admin_client.get("/api/participants", query_string={"status": "missing"})
    assert "status" in error(response, 400, "VALIDATION_ERROR")["details"]["fields"]


def test_qr_png_and_regeneration(admin_client, staff_client, make_participant, participant_row, audit_for):
    participant = make_participant()
    pid, original = participant["id"], participant["qr_token"]
    response = admin_client.get(f"/api/participants/{pid}/qr.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data.startswith(b"\x89PNG\r\n\x1a\n")

    def lookup(token):
        return staff_client.get("/api/lookup", query_string={"token": token})

    assert "qr_token" not in success(lookup(original))
    updated = success(admin_client.post(f"/api/participants/{pid}/regenerate-qr", json={}))
    replacement = updated["qr_token"]
    assert replacement != original
    assert participant_row(pid)["qr_token"] == replacement
    error(lookup(original), 404, "INVALID_QR")
    result = success(lookup(replacement))
    assert result["id"] == pid
    assert "qr_token" not in result
    assert [entry["action"] for entry in audit_for(pid)] == ["create", "regenerate_qr"]
