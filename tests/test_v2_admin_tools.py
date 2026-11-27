import codecs
import csv
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO, StringIO
from threading import Barrier

import pytest
from sqlalchemy import event

from app.extensions import db
from app.services import admin_tools
from tests import check_in, enqueue, error, login, success


IMPORT = "/api/participants/import"
HEADER = b"participant_code,name,email\r\n"


def upload(client, content, lang="en"):
    return client.post(IMPORT, data={"file": (BytesIO(content), "participants.csv")}, headers={"X-Lang": lang})


def test_import_mixed_rows_bom_duplicates_and_broadcast(admin_client, staff_client, make_participant, rows, socket_client):
    make_participant(code="DB", email="old@example.org")
    content = codecs.BOM_UTF8 + (
        ' Participant_Code , NAME ,Email\r\n'
        ' new ,"姓名, One",FIRST@example.org\r\n'
        'db,Existing,db@example.org\r\n'
        'bad,Someone,invalid\r\n'
        'new,Same code,other@example.org\r\n'
        'DIFF,Same email,first@example.org\r\n'
        'OLD,Same stored email,OLD@example.org\r\n'
        'MULTI,"First\nSecond",multi@example.org\r\n'
        'EXTRA,unexpected,column,count\r\n'
    ).encode()
    socket_client.get_received()
    error(upload(staff_client, content), 403, "FORBIDDEN")
    result = success(upload(admin_client, content))
    assert set(result) == {"created", "skipped_existing", "errors"}
    assert (result["created"], result["skipped_existing"]) == (2, 2)
    assert [(p["line"], p["participant_code"], p["code"]) for p in result["errors"]] == [
        (4, "bad", "VALIDATION_ERROR"), (6, "DIFF", "DUPLICATE_EMAIL"),
        (7, "OLD", "DUPLICATE_EMAIL"), (10, "EXTRA", "VALIDATION_ERROR"),
    ]
    assert all(set(p) == {"line", "participant_code", "code", "message"} and p["message"] for p in result["errors"])
    assert rows("SELECT participant_code, name, email FROM participants WHERE participant_code='NEW'") == [
        {"participant_code": "NEW", "name": "姓名, One", "email": "first@example.org"}
    ]
    audits = rows("""SELECT a.action, a.details, p.participant_code, u.role FROM audit_logs a
                     JOIN participants p ON p.id = a.participant_id JOIN users u ON u.id = a.operator_id
                     WHERE a.action = 'import' ORDER BY a.id""")
    assert [(r["participant_code"], r["details"], r["role"]) for r in audits] == [
        ("NEW", {"line": 2}, "admin"), ("MULTI", {"line": 8}, "admin"),
    ]
    packets = socket_client.get_received()
    assert [p["name"] for p in packets] == ["stats_updated"]
    assert packets[0]["args"][0] == success(staff_client.get("/api/stats"))
    retry = success(upload(admin_client, content, lang="zh"))
    assert (retry["created"], retry["skipped_existing"]) == (0, 4)
    assert retry["errors"][0]["message"] != result["errors"][0]["message"]
    assert socket_client.get_received() == []


@pytest.mark.parametrize("content,field_error", [
    (b"", "invalid_header"),
    (b"name,participant_code,email\n", "invalid_header"),
    (HEADER + b"OK,first,first@example.org\nBAD,\xff,foo@example.org", "expected_utf8"),
    (HEADER + b'OK,first,first@example.org\nBAD,"unclosed,foo@example.org', "invalid_csv"),
    (b"x" * (2 * 1024 * 1024 + 1), "max_2_mib"),
    (HEADER + b"X,Name,x@example.org\n" * 5001, "max_5000_rows"),
])
def test_whole_file_errors_are_atomic(admin_client, rows, socket_client, content, field_error):
    message = error(upload(admin_client, content), 400, "VALIDATION_ERROR")
    assert message["details"]["fields"]["file"] == field_error
    assert rows("SELECT id FROM participants") == rows("SELECT id FROM audit_logs") == []
    assert socket_client.get_received() == []


def test_csv_row_and_byte_limits_are_inclusive(admin_client, rows):
    # The long name is a row error even at the byte limit. Other rows still import.
    tail = b",p@example.org\r\nOK,OK,ok@example.org"
    prefix = HEADER + b"LONG,"
    full_size = prefix + b"x" * (2 * 1024 * 1024 - len(prefix) - len(tail)) + tail
    result = success(upload(admin_client, full_size))
    assert result["created"] == 1 and [item["line"] for item in result["errors"]] == [2]
    result = success(upload(admin_client, HEADER + b"\n" * 5000))
    assert len(result["errors"]) == 5000 and result["errors"][-1]["line"] == 5001
    assert rows("SELECT participant_code FROM participants") == [{"participant_code": "OK"}]


def test_import_database_failure_rolls_back_whole_batch(app, admin_client, rows, socket_client):
    # Inject a failure at the audit insert after the valid participant rows were inserted.
    def reject_audits(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_logs"):
            raise RuntimeError("simulated audit failure")

    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", reject_audits)
    try:
        response = upload(admin_client, HEADER + b"A,A,a@example.org\nB,B,b@example.org\n")
    finally:
        event.remove(engine, "before_cursor_execute", reject_audits)
    error(response, 500, "INTERNAL_ERROR")
    assert rows("SELECT id FROM participants") == rows("SELECT id FROM audit_logs") == []
    assert socket_client.get_received() == []


def test_undo_all_transitions_and_timeline(admin_client, staff_client, make_participant, socket_client):
    person = make_participant()
    pid = person["id"]
    root = f"/api/participants/{pid}"
    reason = "Operator corrected the record"
    admin = success(admin_client.get("/api/auth/me"))["user"]
    staff = success(staff_client.get("/api/auth/me"))["user"]
    route = root + "/undo"
    for body in ({}, {"reason": None}, {"reason": "  "}, {"reason": "x" * 201}, {"reason": 1}):
        assert "reason" in error(admin_client.post(route, json=body), 400, "VALIDATION_ERROR")["details"]["fields"]
    first = success(staff_client.post("/api/checkin", json={"code": person["participant_code"], "entrance": "South"}))
    queued = enqueue(staff_client, person)["participant"]
    called = success(staff_client.post("/api/stage/call-next", json={}))["current"]
    success(staff_client.post("/api/stage/complete", json={}))
    socket_client.get_received()
    error(staff_client.post(route, json={"reason": reason}), 403, "FORBIDDEN")
    changes = [("completed", "on_stage", called), ("on_stage", "queued", queued),
               ("queued", "checked_in", first), ("checked_in", "registered", person)]
    for previous, target, expected in changes:
        result = success(admin_client.post(route, json={"reason": f"  {reason}  "}))
        assert result == {**{k: v for k, v in expected.items() if k != "qr_token"}, "updated_at": result["updated_at"]}
        assert result["status"] == target and "qr_token" not in result
        events = {p["name"]: p["args"][0] for p in socket_client.get_received()}
        assert events["participant_updated"] == {"action": "undo", "participant": result}
        assert events["stage_updated"] == success(staff_client.get("/api/stage/state"))
        assert events["stats_updated"] == success(staff_client.get("/api/stats"))
    invalid = error(admin_client.post(route, json={"reason": reason}), 409, "INVALID_STATE")
    assert invalid["details"]["status"] == "registered"
    assert socket_client.get_received() == []
    timeline = success(admin_client.get(root + "/timeline"))
    assert all(set(item) == {"action", "at", "operator", "details"} for item in timeline)
    times = [datetime.fromisoformat(item["at"]) for item in timeline]
    assert times == sorted(times)
    assert [item["action"] for item in timeline] == ["create", "check_in", "enqueue", "call", "complete"] + ["undo"] * 4
    assert [item["operator"] for item in timeline] == [
        {"id": user["id"], "name": user["display_name"]} for user in [admin] + [staff] * 4 + [admin] * 4
    ]
    assert [item["details"] for item in timeline[-4:]] == [
        {"from": previous, "to": target, "reason": reason} for previous, target, _ in changes
    ]


def test_undo_completed_with_busy_stage(admin_client, staff_client, make_participant, audit_for, socket_client):
    first, other = make_participant(), make_participant()
    for p in (first, other):
        check_in(staff_client, p)
        enqueue(staff_client, p)
    success(staff_client.post("/api/stage/call-next", json={}))
    result = success(staff_client.post("/api/stage/call-next", json={"complete_current": True}))
    socket_client.get_received()
    denied = error(admin_client.post(f"/api/participants/{first['id']}/undo", json={"reason": "wrong button"}),
                   409, "STAGE_BUSY")
    assert denied["details"]["current"] == result["current"]
    assert audit_for(first["id"])[-1]["action"] == "complete"
    assert socket_client.get_received() == []


@pytest.mark.parametrize("completed", [False, True])
def test_concurrent_undo_of_same_observed_state(app, staff_client, make_participant, audit_for, monkeypatch, completed):
    p = make_participant()
    check_in(staff_client, p)
    enqueue(staff_client, p)
    success(staff_client.post("/api/stage/call-next", json={}))
    if completed:
        success(staff_client.post("/api/stage/complete", json={}))
    devices = [app.test_client(), app.test_client()]
    for device in devices:
        login(device, "admin")
    observed = Barrier(2, timeout=10)
    lock_stage = admin_tools.lock_stage

    def synchronize_requests():
        observed.wait()  # Both have read the same status before either acquires the real lock.
        lock_stage()

    monkeypatch.setattr(admin_tools, "lock_stage", synchronize_requests)

    def post(device):
        return device.post(f"/api/participants/{p['id']}/undo", json={"reason": "wrong button"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner, loser = sorted(pool.map(post, devices), key=lambda response: response.status_code)
    updated = success(winner)
    if completed:
        assert updated["status"] == "on_stage"
        assert error(loser, 409, "STAGE_BUSY")["details"]["current"] == updated
    else:
        assert updated["status"] == "queued"
        assert error(loser, 409, "INVALID_STATE")["details"]["participant"] == updated
    assert sum(r["action"] == "undo" for r in audit_for(p["id"])) == 1


def test_export_records_csv(admin_client, staff_client, make_participant):
    p = make_participant(code="GRAD", name='王, "Li"')
    make_participant(code="OTHER", name="=1+1")
    success(staff_client.post("/api/checkin", json={"code": "GRAD", "entrance": "东门"}))
    enqueue(staff_client, p)
    success(staff_client.post("/api/stage/call-next", json={}))
    success(staff_client.post("/api/stage/requeue", json={"participant_id": p["id"]}))
    success(staff_client.post("/api/stage/call-next", json={}))
    completed = success(staff_client.post("/api/stage/complete", json={}))["completed"]
    response = admin_client.get("/api/export/records.csv")
    assert response.status_code == 200 and response.mimetype == "text/csv"
    assert re.fullmatch(r'attachment; filename="graduation-records-\d{8}-\d{4}\.csv"', response.headers["Content-Disposition"])
    assert response.data.startswith(codecs.BOM_UTF8)
    header, first, other = csv.reader(StringIO(response.data.decode("utf-8-sig"), newline=""))
    assert header == ["编号", "姓名", "邮箱", "状态", "签到时间", "签到入口", "签到人", "入队时间",
                      "呼叫时间", "呼叫人", "完成时间", "完成人", "放回队尾次数"]
    assert first == ["GRAD", p["name"], p["email"], "completed", completed["checked_in_at"], "东门", "Staff One",
                     completed["queued_at"], completed["called_at"], "Staff One", completed["completed_at"], "Staff One", "1"]
    assert other == ["OTHER", "'=1+1", "grad2@example.org", "registered", *([""] * 8), "0"]


def test_qr_sheet_filters_and_pagination(admin_client, staff_client, make_participant):
    people = [make_participant(name=f"Name {i}") for i in range(13)]
    sheet = admin_client.get("/admin/qr-sheet", headers={"X-Lang": "en"})
    assert sheet.status_code == 200
    html = sheet.get_data(as_text=True)
    sheets = re.findall(r'<section class="sheet">(.*?)</section>', html, re.DOTALL)
    assert [page.count('<article class="card">') for page in sheets] == [12, 1]
    for p in people:
        assert f'src="/api/participants/{p["id"]}/qr.png"' in html
        assert p["name"] in html and p["participant_code"] in html
    assert "/static/css/tokens.css" in html and "size: A4 portrait" in html and "@media print" in html
    assert "grid-template-columns: repeat(3," in html and "grid-template-rows: repeat(4," in html
    check_in(staff_client, people[0])
    html = admin_client.get("/admin/qr-sheet?q=name&status=checked_in").get_data(as_text=True)
    assert html.count('<article class="card">') == 1 and people[0]["participant_code"] in html
    assert admin_client.get("/admin/qr-sheet?status=invalid").status_code == 400
    assert staff_client.get("/admin/qr-sheet").status_code == 403
