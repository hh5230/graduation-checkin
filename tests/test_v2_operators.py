from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from tests import check_in, enqueue, error, success


def test_checkin_search(staff_client, make_participant):
    exact = make_participant(code="key", name="Zed")
    by_name = make_participant(code="X_2", name="A key")
    by_email = make_participant(name="Bob", email="myKey@example.org")
    for n in range(20):
        make_participant(code=f"KEY-{n:02}", name=f"Charlie {n:02}")
    result = success(staff_client.get("/api/checkin/search?q=%20KeY%20"))
    assert len(result) == 20 and all("qr_token" not in p for p in result)
    assert [p["id"] for p in result[:3]] == [p["id"] for p in (exact, by_name, by_email)]
    assert [p["name"] for p in result[3:]] == [f"Charlie {i:02}" for i in range(17)]
    assert [p["id"] for p in success(staff_client.get("/api/checkin/search?q=_"))] == [by_name["id"]]
    assert success(staff_client.get("/api/checkin/search?q=nobody")) == []
    for suffix in ("", "?q=%20"):
        error(staff_client.get("/api/checkin/search" + suffix), 400, "VALIDATION_ERROR")


def test_entrance(staff_client, admin_client, make_participant, participant_row):
    p = make_participant()
    body = {"code": p["participant_code"]}
    assert p["checked_in_entrance"] is None and p["requeue_count"] == 0
    for entrance in (3, None, "x" * 65, "east\x00", "\ud800"):
        problem = error(staff_client.post("/api/checkin", json={**body, "entrance": entrance}), 400, "VALIDATION_ERROR")
        assert "entrance" in problem["details"]["fields"]
    first = success(staff_client.post("/api/checkin", json={**body, "entrance": "  东门 A  "}))
    assert first["checked_in_entrance"] == participant_row(p["id"])["checked_in_entrance"] == "东门 A"
    duplicate = error(admin_client.post("/api/checkin", json={**body, "entrance": "West"}), 409, "ALREADY_CHECKED_IN")
    assert duplicate["details"] == {"participant": first, **{k: first[k] for k in (
        "checked_in_at", "checked_in_by", "checked_in_entrance",
    )}}


def test_requeue_to_tail_and_broadcast(staff_client, make_participant, socket_client, audit_for):
    first, second = make_participant(), make_participant()
    for p in (first, second):
        check_in(staff_client, p)
        enqueue(staff_client, p)
    current = success(staff_client.post("/api/stage/call-next", json={}))["current"]
    socket_client.get_received()
    path = "/api/stage/requeue"
    wrong = error(staff_client.post(path, json={"participant_id": second["id"]}), 409, "NOTHING_ON_STAGE")
    assert wrong["details"] == {"participant_id": second["id"], "current": current}
    for body in ({}, {"participant_id": True}, {"participant_id": 2**64}):
        error(staff_client.post(path, json=body), 400, "VALIDATION_ERROR")
    assert socket_client.get_received() == []
    queued = success(staff_client.post(path, json={"participant_id": first["id"]}))
    p = queued["participant"]
    assert queued["position"] == 2 and p["status"] == "queued"
    assert p["requeue_count"] == 1 and p["called_at"] is None and p["called_by"] is None
    assert p["queued_at"] > current["queued_at"]
    state = success(staff_client.get("/api/stage/state"))
    assert state["current"] is None and state["next"] == state["queue"][0] and state["queue_length"] == 2
    assert [item["id"] for item in state["queue"]] == [second["id"], first["id"]]
    events = {packet["name"]: packet["args"][0] for packet in socket_client.get_received()}
    assert events["stage_updated"] == state
    assert events["participant_updated"] == {"action": "requeue", "participant": p}
    assert events["stats_updated"] == success(staff_client.get("/api/stats"))
    assert [row["action"] for row in audit_for(p["id"])] == ["create", "check_in", "enqueue", "call", "requeue"]
    assert success(staff_client.post("/api/stage/call-next", json={}))["current"]["id"] == second["id"]


def test_ten_simultaneous_requeues(app, staff_client, make_participant, audit_for, participant_row):
    person = make_participant()
    check_in(staff_client, person)
    enqueue(staff_client, person)
    success(staff_client.post("/api/stage/call-next", json={}))
    devices = [app.test_client() for _ in range(10)]
    for device in devices:
        success(device.post("/api/auth/login", json={"username": "stage1", "password": "stage123"}))
    start = Barrier(len(devices), timeout=15)

    def requeue(device):
        start.wait()
        return device.post("/api/stage/requeue", json={"participant_id": person["id"]})

    with ThreadPoolExecutor(max_workers=len(devices)) as pool:
        responses = list(pool.map(requeue, devices))
    assert Counter(response.status_code for response in responses) == {200: 1, 409: 9}
    for response in responses:
        if response.status_code == 409:
            assert error(response, 409, "NOTHING_ON_STAGE")["details"]["current"] is None
    assert participant_row(person["id"])["requeue_count"] == 1
    assert sum(row["action"] == "requeue" for row in audit_for(person["id"])) == 1
