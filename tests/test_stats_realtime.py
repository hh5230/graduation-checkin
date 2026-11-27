import json

from app.extensions import get_redis, socketio
from tests import check_in, enqueue, error, success


def test_stats_count_every_stage(staff_client, make_participant, rows):
    people = [make_participant() for _ in range(6)]
    for person in people[:4]:
        check_in(staff_client, person)
    for person in people[:3]:
        enqueue(staff_client, person)
    success(staff_client.post("/api/stage/call-next", json={}))
    success(staff_client.post("/api/stage/complete", json={}))
    success(staff_client.post("/api/stage/call-next", json={}))

    counts = {row["status"]: row["n"] for row in rows(
        "SELECT status, count(*) AS n FROM participants GROUP BY status"
    )}
    assert counts == {"registered": 2, "checked_in": 1, "queued": 1, "on_stage": 1, "completed": 1}
    assert success(staff_client.get("/api/stats")) == {
        "total": 6, "checked_in": 4, "not_checked_in": 2, "waiting": 1, "on_stage": 1, "completed": 1,
    }


def test_stats_immediately_refresh_a_primed_cache(app, staff_client, make_participant):
    def cached_counts():
        data = success(staff_client.get("/api/stats"))
        with app.app_context():
            assert json.loads(get_redis().get("stats:v1")) == data
        return data

    counts = {"total": 0, "checked_in": 0, "not_checked_in": 0, "waiting": 0, "on_stage": 0, "completed": 0}
    assert cached_counts() == counts
    person = make_participant()
    counts.update(total=1, not_checked_in=1)
    assert cached_counts() == counts
    check_in(staff_client, person)
    counts.update(checked_in=1, not_checked_in=0)
    assert cached_counts() == counts
    enqueue(staff_client, person)
    counts.update(waiting=1)
    assert cached_counts() == counts
    success(staff_client.post("/api/stage/call-next", json={}))
    counts.update(waiting=0, on_stage=1)
    assert cached_counts() == counts
    success(staff_client.post("/api/stage/complete", json={}))
    counts.update(on_stage=0, completed=1)
    assert cached_counts() == counts


def test_broadcasts_reach_other_logged_in_device(admin_client, staff_client, socket_client, make_participant):
    person = make_participant()
    socket_client.get_received()  # Discard the separate create transaction.
    steps = [
        ("/api/checkin", {"code": person["participant_code"]}, "check_in", "checked_in"),
        ("/api/stage/queue", {"token": person["qr_token"]}, "enqueue", "queued"),
        ("/api/stage/call-next", {}, "call", "on_stage"),
        ("/api/stage/complete", {}, "complete", "completed"),
    ]
    for path, body, action, status in steps:
        success(admin_client.post(path, json=body))
        packets = socket_client.get_received()
        events = {p["name"]: p["args"][0] for p in packets if p["namespace"] == "/"}
        event = events["participant_updated"]
        assert event["action"] == action
        participant = event["participant"]
        assert (participant["id"], participant["status"]) == (person["id"], status)
        assert "qr_token" not in participant
        assert events["stats_updated"] == success(staff_client.get("/api/stats"))
        if action in ("enqueue", "call", "complete"):
            assert events["stage_updated"] == success(staff_client.get("/api/stage/state"))

    error(admin_client.post("/api/stage/complete", json={}), 409, "NOTHING_ON_STAGE")
    assert not socket_client.get_received()


def test_anonymous_socket_rejected(app, client):
    observer = socketio.test_client(app, flask_test_client=client)
    try:
        assert not observer.is_connected()
    finally:
        if observer.is_connected():
            observer.disconnect()
