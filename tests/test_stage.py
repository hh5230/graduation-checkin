from datetime import datetime

from tests import check_in, enqueue, error, success


def state(client):
    return success(client.get("/api/stage/state"))


def test_registered_cannot_enqueue(staff_client, make_participant, participant_row, audit_for):
    participant = make_participant()
    response = staff_client.post("/api/stage/queue", json={"code": participant["participant_code"]})
    details = error(response, 409, "NOT_CHECKED_IN")["details"]
    assert details["participant"]["id"] == participant["id"]
    stored = participant_row(participant["id"])
    assert stored["status"] == "registered" and stored["queued_at"] is None
    assert [row["action"] for row in audit_for(participant["id"])] == ["create"]


def test_empty_stage(staff_client, rows):
    error(staff_client.post("/api/stage/call-next", json={}), 409, "QUEUE_EMPTY")
    error(staff_client.post("/api/stage/complete", json={}), 409, "NOTHING_ON_STAGE")
    assert state(staff_client) == {"queue": [], "current": None, "recent_completed": []}
    assert rows("SELECT id FROM audit_logs") == []


def test_fifo_and_duplicate_enqueue(staff_client, make_participant, participant_row, audit_for):
    # Enqueue in reverse creation order so sorting by id alone cannot pass.
    people = [make_participant(code=code) for code in ("C", "B", "A")]
    for position, person in enumerate(reversed(people), 1):
        check_in(staff_client, person)
        queued = enqueue(staff_client, person)
        assert queued["position"] == position
        assert queued["participant"]["id"] == person["id"]
        stored = participant_row(person["id"])
        assert stored["status"] == queued["participant"]["status"] == "queued"
        assert stored["queued_at"] == datetime.fromisoformat(queued["participant"]["queued_at"])
        assert stored["queued_by"] == queued["participant"]["queued_by"]["id"]

    duplicate = staff_client.post("/api/stage/queue", json={"code": "B"})
    details = error(duplicate, 409, "ALREADY_QUEUED")["details"]
    middle = people[1]["id"]
    assert details["participant"]["id"] == middle
    assert details["position"] == 2
    assert datetime.fromisoformat(details["queued_at"]) == participant_row(middle)["queued_at"]
    assert [p["participant_code"] for p in state(staff_client)["queue"]] == ["A", "B", "C"]
    assert [row["action"] for row in audit_for(middle)] == ["create", "check_in", "enqueue"]
    result = success(staff_client.post("/api/stage/call-next", json={}))
    assert result["current"]["participant_code"] == "A"
    assert [p["participant_code"] for p in state(staff_client)["queue"]] == ["B", "C"]


def test_call_complete_and_rejected_transitions(staff_client, make_participant, participant_row, audit_for):
    first, other = make_participant(), make_participant()
    pid = first["id"]
    staff = success(staff_client.get("/api/auth/me"))["user"]
    operator = {"id": staff["id"], "name": staff["display_name"]}
    for person in (first, other):
        check_in(staff_client, person)
        enqueue(staff_client, person)
    result = success(staff_client.post("/api/stage/call-next", json={}))
    current = result["current"]
    assert result["completed"] is None
    before = participant_row(pid)
    assert current["id"] == pid
    assert current["status"] == before["status"] == "on_stage"
    assert current["called_by"] == operator and before["called_by"] == staff["id"]
    assert datetime.fromisoformat(current["called_at"]) == before["called_at"]

    busy = error(staff_client.post("/api/stage/call-next", json={}), 409, "STAGE_BUSY")
    assert busy["details"]["current"] == current
    wrong = staff_client.post("/api/stage/complete", json={"participant_id": other["id"]})
    error(wrong, 409, "NOTHING_ON_STAGE")
    assert state(staff_client)["current"] == current
    assert participant_row(other["id"])["status"] == "queued"
    queue_args = {"code": first["participant_code"]}
    denied = error(staff_client.post("/api/stage/queue", json=queue_args), 409, "INVALID_STATE")
    assert denied["details"]["status"] == "on_stage"
    assert participant_row(pid) == before

    completed = success(staff_client.post("/api/stage/complete", json={"participant_id": pid}))["completed"]
    stored = participant_row(pid)
    assert completed["id"] == pid
    assert completed["status"] == stored["status"] == "completed"
    assert completed["completed_by"] == operator and stored["completed_by"] == staff["id"]
    assert datetime.fromisoformat(completed["completed_at"]) == stored["completed_at"]
    assert state(staff_client)["current"] is None
    assert state(staff_client)["recent_completed"] == [completed]

    error(staff_client.post("/api/stage/complete", json={}), 409, "NOTHING_ON_STAGE")
    denied = error(staff_client.post("/api/stage/queue", json=queue_args), 409, "INVALID_STATE")
    assert denied["details"]["status"] == "completed"
    error(staff_client.post("/api/checkin", json=queue_args), 409, "ALREADY_CHECKED_IN")
    assert participant_row(pid) == stored
    assert audit_for(pid)[1:] == [
        {"action": action, "operator_id": staff["id"]} for action in ("check_in", "enqueue", "call", "complete")
    ]


def test_complete_current_is_atomic(staff_client, make_participant, participant_row, audit_for):
    first = make_participant()
    check_in(staff_client, first)
    enqueue(staff_client, first)
    current = success(staff_client.post("/api/stage/call-next", json={}))["current"]
    before = participant_row(first["id"])
    audits = audit_for(first["id"])

    # With no successor the combined transition must roll back its completion and audit.
    response = staff_client.post("/api/stage/call-next", json={"complete_current": True})
    error(response, 409, "QUEUE_EMPTY")
    assert state(staff_client)["current"] == current
    assert participant_row(first["id"]) == before
    assert audit_for(first["id"]) == audits

    second = make_participant()
    check_in(staff_client, second)
    enqueue(staff_client, second)
    result = success(staff_client.post("/api/stage/call-next", json={"complete_current": True}))
    assert result["completed"]["id"] == first["id"]
    assert result["completed"]["status"] == participant_row(first["id"])["status"] == "completed"
    assert result["current"]["id"] == second["id"]
    assert result["current"]["status"] == participant_row(second["id"])["status"] == "on_stage"
    assert state(staff_client) == {"current": result["current"], "queue": [],
                                   "recent_completed": [result["completed"]]}
    assert [row["action"] for row in audit_for(first["id"])] == ["create", "check_in", "enqueue", "call", "complete"]
    assert [row["action"] for row in audit_for(second["id"])] == ["create", "check_in", "enqueue", "call"]
