import csv
from datetime import UTC
from io import StringIO

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..errors import ApiError, invalid_fields, is_db_text
from ..extensions import db
from ..i18n import csv_row_message, get_lang
from ..models import AuditLog, Participant, User, serialize_participant
from . import commit_changes, record_change
from .participants import get_participant, new_token, profile_values
from .stage import current_on_stage, lock_stage

CSV_COLUMNS = ("participant_code", "name", "email")
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 5000
# Let the profile validator report an oversized cell as a row error.
csv.field_size_limit(MAX_CSV_BYTES)
IMPORT_LOCK_KEY = 2026002

RECORD_HEADERS = ("编号", "姓名", "邮箱", "状态", "签到时间", "签到入口", "签到人", "入队时间",
                  "呼叫时间", "呼叫人", "完成时间", "完成人", "放回队尾次数")


def read_csv_rows(stream):
    raw = stream.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise invalid_fields(file="max_2_mib")
    try:
        source = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise invalid_fields(file="expected_utf8") from None
    reader = csv.reader(StringIO(source, newline=""), strict=True)
    rows = []
    try:
        header = next(reader, [])
        if tuple(value.strip().lower() for value in header) != CSV_COLUMNS:
            raise ApiError("VALIDATION_ERROR", 400, {"fields": {"file": "invalid_header"},
                                                     "line": 1, "expected_header": list(CSV_COLUMNS)})
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                break
            if len(rows) == MAX_CSV_ROWS:
                raise invalid_fields(file="max_5000_rows")
            rows.append((line, row))
    except csv.Error:
        raise ApiError("VALIDATION_ERROR", 400, {"fields": {"file": "invalid_csv"}, "line": reader.line_num}) from None
    return rows


def insert_import_row(values):
    # A concurrent profile creation or edit can win a unique key during the import.
    # DO NOTHING keeps the surrounding batch transaction usable after that conflict.
    while True:
        stmt = pg_insert(Participant).values(**values, qr_token=new_token()).on_conflict_do_nothing()
        created_id = db.session.scalar(stmt.returning(Participant.id))
        if created_id is not None:
            return created_id
        if db.session.scalar(select(Participant.id).where(Participant.participant_code == values["participant_code"])):
            return None
        if db.session.scalar(select(Participant.id).where(func.lower(Participant.email) == values["email"])):
            raise ApiError("DUPLICATE_EMAIL", 409, {"email": values["email"]})
        # A token collision or a concurrent edit released both profile keys. Retry with a fresh token.


def import_participants(stream, operator_id):
    rows = read_csv_rows(stream)
    # Two files can contain the same unique keys in opposite orders. Serialize just the imports.
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK_KEY})
    audits = []
    errors = []
    skipped = 0
    lang = get_lang()
    for line, row in rows:
        try:
            if len(row) != len(CSV_COLUMNS):
                raise invalid_fields(row="expected_three_columns")
            values = profile_values(dict(zip(CSV_COLUMNS, row)), partial=False)
            created_id = insert_import_row(values)
        except ApiError as error:
            errors.append({"line": line, "participant_code": row[0].strip() if row else "",
                           "code": error.code, "message": csv_row_message(error.code, error.details.get("fields"), lang)})
            continue
        if created_id is None:
            skipped += 1
        else:
            audits.append({"action": "import", "participant_id": created_id, "operator_id": operator_id,
                           "details": {"line": line}})
    if audits:
        db.session.execute(insert(AuditLog), audits)
        commit_changes(stats_changed=True)
    else:
        db.session.commit()
    return {"created": len(audits), "skipped_existing": skipped, "errors": errors}


def participant_timeline(participant_id):
    get_participant(participant_id)
    stmt = select(AuditLog, User).outerjoin(User, User.id == AuditLog.operator_id).where(
        AuditLog.participant_id == participant_id
    ).order_by(AuditLog.created_at, AuditLog.id)
    return [{"action": log.action, "at": log.created_at.astimezone(UTC).isoformat(),
             "operator": {"id": user.id, "name": user.display_name} if user else None, "details": log.details}
            for log, user in db.session.execute(stmt)]


UNDO_TRANSITIONS = {
    "checked_in": ("registered", {"checked_in_at": None, "checked_in_by": None, "checked_in_entrance": None}),
    "queued": ("checked_in", {"queued_at": None, "queued_by": None}),
    "on_stage": ("queued", {"called_at": None, "called_by": None}),
    "completed": ("on_stage", {"completed_at": None, "completed_by": None}),
}


def undo(participant_id, reason, operator_id):
    if not is_db_text(reason):
        raise invalid_fields(reason="required" if reason is None else "invalid")
    reason = reason.strip()
    if not reason:
        raise invalid_fields(reason="required")
    if len(reason) > 200:
        raise invalid_fields(reason="too_long")
    participant = get_participant(participant_id)
    previous = participant.status
    if previous not in UNDO_TRANSITIONS:
        raise ApiError("INVALID_STATE", 409, {"status": previous, "participant": serialize_participant(participant)})
    target, clear_fields = UNDO_TRANSITIONS[previous]
    if previous != "checked_in":
        lock_stage()
    if previous == "completed":
        current = current_on_stage()
        if current:
            raise ApiError("STAGE_BUSY", 409, {"current": current})
    stmt = (
        update(Participant).where(Participant.id == participant_id, Participant.status == previous)
        .values(status=target, updated_at=func.now(), **clear_fields).returning(Participant.id)
    )
    if db.session.scalar(stmt) is None:
        actual = get_participant(participant_id)
        raise ApiError("INVALID_STATE", 409, {"status": actual.status, "participant": serialize_participant(actual)})
    event = record_change("undo", get_participant(participant_id), operator_id,
                          {"reason": reason, "from": previous, "to": target})
    commit_changes(event)
    return event["participant"]


def excel_cell(value):
    # Excel interprets formula prefixes even inside CSV quotation marks.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def records_csv():
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(RECORD_HEADERS)
    yield "\ufeff" + buffer.getvalue()
    stmt = select(Participant).order_by(Participant.id).execution_options(yield_per=500)
    for participant in db.session.scalars(stmt):
        p = serialize_participant(participant)
        values = (p["participant_code"], p["name"], p["email"], p["status"], p["checked_in_at"],
                  p["checked_in_entrance"], (p["checked_in_by"] or {}).get("name"), p["queued_at"],
                  p["called_at"], (p["called_by"] or {}).get("name"), p["completed_at"],
                  (p["completed_by"] or {}).get("name"), p["requeue_count"])
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(map(excel_cell, values))
        yield buffer.getvalue()
