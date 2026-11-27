from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import cycle
from threading import Barrier

import pytest

from tests import check_in, enqueue, error, login, success


WORKERS = 20


@pytest.fixture
def race(app):
    # Authenticate before the barrier. No waiting device holds a database connection.
    accounts = cycle(("staff1", "staff2", "admin"))
    devices = []
    for _ in range(WORKERS):
        client = app.test_client()
        operator = login(client, next(accounts))
        devices.append((client, operator))

    def run(path, body, conflict):
        start = Barrier(WORKERS, timeout=30)

        def post(device):
            client, operator = device
            with app.app_context():
                start.wait()
                return client.post(path, json=body), operator

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            results = list(pool.map(post, devices))

        counts = Counter(response.status_code for response, _ in results)
        assert counts == {200: 1, 409: WORKERS - 1}, [
            (response.status_code, response.get_json()) for response, _ in results
        ]
        conflicts = [
            error(response, 409, conflict)["details"] for response, _ in results if response.status_code == 409
        ]
        (winner, operator), = [
            (success(response), user) for response, user in results if response.status_code == 200
        ]
        return winner, operator, conflicts

    return run


def test_simultaneous_checkins(race, make_participant, participant_row, audit_for):
    person = make_participant()
    pid = person["id"]
    result, operator, conflicts = race("/api/checkin", {"code": person["participant_code"]}, "ALREADY_CHECKED_IN")
    stored = participant_row(pid)
    assert result["id"] == pid and result["status"] == stored["status"] == "checked_in"
    assert stored["checked_in_by"] == operator["id"]
    for details in conflicts:
        assert details["checked_in_at"] == result["checked_in_at"]
        assert details["checked_in_by"] == {"id": operator["id"], "name": operator["display_name"]}
    assert [entry for entry in audit_for(pid) if entry["action"] == "check_in"] == [
        {"action": "check_in", "operator_id": operator["id"]}
    ]


def test_simultaneous_enqueues(race, staff_client, make_participant, participant_row, audit_for):
    person = make_participant()
    check_in(staff_client, person)
    pid = person["id"]
    result, operator, conflicts = race("/api/stage/queue", {"code": person["participant_code"]}, "ALREADY_QUEUED")
    assert result["position"] == 1
    assert all(details["position"] == 1 for details in conflicts)
    stored = participant_row(pid)
    assert stored["status"] == "queued" and stored["queued_by"] == operator["id"]
    assert [p["id"] for p in success(staff_client.get("/api/stage/state"))["queue"]] == [pid]
    assert [entry for entry in audit_for(pid) if entry["action"] == "enqueue"] == [
        {"action": "enqueue", "operator_id": operator["id"]}
    ]


def test_simultaneous_calls(race, staff_client, make_participant, rows):
    people = [make_participant() for _ in range(10)]
    for person in people:
        check_in(staff_client, person)
        enqueue(staff_client, person)
    first = people[0]["id"]
    result, operator, conflicts = race("/api/stage/call-next", {}, "STAGE_BUSY")
    assert result["current"]["id"] == first
    assert all(details["current"]["id"] == first for details in conflicts)
    assert rows("SELECT id, called_by FROM participants WHERE status = 'on_stage'") == [
        {"id": first, "called_by": operator["id"]}
    ]
    assert [r["id"] for r in rows("SELECT id FROM participants WHERE status = 'queued' ORDER BY queued_at, id")] == [
        p["id"] for p in people[1:]
    ]
    assert rows("SELECT participant_id, operator_id FROM audit_logs WHERE action = 'call'") == [
        {"participant_id": first, "operator_id": operator["id"]}
    ]


def test_simultaneous_completions(race, staff_client, make_participant, rows):
    person = make_participant()
    check_in(staff_client, person)
    enqueue(staff_client, person)
    success(staff_client.post("/api/stage/call-next", json={}))
    pid = person["id"]
    result, operator, _ = race("/api/stage/complete", {}, "NOTHING_ON_STAGE")
    assert result["completed"]["id"] == pid
    assert rows("SELECT id, status, completed_by FROM participants") == [
        {"id": pid, "status": "completed", "completed_by": operator["id"]}
    ]
    assert rows("SELECT participant_id, operator_id FROM audit_logs WHERE action = 'complete'") == [
        {"participant_id": pid, "operator_id": operator["id"]}
    ]
