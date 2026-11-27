from sqlalchemy import func, or_, select, text, tuple_, update

from ..errors import ApiError, invalid_fields
from ..extensions import db
from ..models import Participant, serialize_participant
from . import commit_changes, record_change
from .participants import get_participant, transition_by_identifier

# Call, complete, requeue and stage-related undo share this transaction lock.
STAGE_LOCK_KEY = 2026001


def lock_stage():
    db.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": STAGE_LOCK_KEY})


def position(p):
    stmt = select(func.count()).select_from(Participant).where(
        Participant.status == "queued",
        tuple_(Participant.queued_at, Participant.id) < tuple_(p.queued_at, p.id),
    )
    return 1 + db.session.scalar(stmt)


def enqueue(data, operator_id):
    p, changed = transition_by_identifier(
        data, "checked_in", status="queued", queued_at=func.clock_timestamp(), queued_by=operator_id,
    )
    if not changed:
        details = {"participant": serialize_participant(p)}
        if p.status == "registered":
            raise ApiError("NOT_CHECKED_IN", 409, details)
        if p.status == "queued":
            details.update(queued_at=details["participant"]["queued_at"], position=position(p))
            raise ApiError("ALREADY_QUEUED", 409, details)
        details["status"] = p.status
        raise ApiError("INVALID_STATE", 409, details)
    event = record_change("enqueue", p, operator_id)
    result = {"participant": event["participant"], "position": position(p)}
    commit_changes(event)
    return result


def current_on_stage():
    stmt = select(Participant).where(Participant.status == "on_stage").execution_options(populate_existing=True)
    p = db.session.scalar(stmt)
    return serialize_participant(p) if p else None


def stage_state():
    # A single statement gives current, queue and history the same MVCC snapshot.
    recent = select(Participant.id).where(Participant.status == "completed").order_by(
        Participant.completed_at.desc(), Participant.id.desc()
    ).limit(5)
    stmt = select(Participant).where(
        or_(Participant.status.in_(("on_stage", "queued")), Participant.id.in_(recent))
    ).order_by(Participant.queued_at, Participant.id)
    current, queue, completed = None, [], []
    for p in db.session.scalars(stmt.execution_options(populate_existing=True)):
        if p.status == "on_stage":
            current = serialize_participant(p)
        elif p.status == "queued":
            queue.append(serialize_participant(p))
        else:
            completed.append(p)
    completed.sort(key=lambda p: (p.completed_at, p.id), reverse=True)
    return {"current": current, "queue": queue, "recent_completed": [serialize_participant(p) for p in completed],
            "next": queue[0] if queue else None, "queue_length": len(queue)}


def nothing_on_stage(expected_id):
    return ApiError("NOTHING_ON_STAGE", 409, {"participant_id": expected_id, "current": current_on_stage()})


def participant_id_from_body(data):
    value = data.get("participant_id")
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise invalid_fields(participant_id="invalid_integer" if "participant_id" in data else "required")
    return value


def requeue(operator_id, data):
    expected_id = participant_id_from_body(data)
    lock_stage()
    stmt = (
        update(Participant).where(Participant.id == expected_id, Participant.status == "on_stage")
        .values(status="queued", queued_at=func.clock_timestamp(), called_at=None, called_by=None,
                requeue_count=Participant.requeue_count + 1, updated_at=func.now())
        .returning(Participant.id)
    )
    if db.session.scalar(stmt) is None:
        raise nothing_on_stage(expected_id)
    participant = get_participant(expected_id)
    event = record_change("requeue", participant, operator_id)
    result = {"participant": event["participant"], "position": position(participant)}
    commit_changes(event)
    return result


def finish_current(operator_id, expected_id=None):
    stmt = update(Participant).where(Participant.status == "on_stage")
    if expected_id is not None:
        stmt = stmt.where(Participant.id == expected_id)
    stmt = stmt.values(status="completed", completed_at=func.now(), completed_by=operator_id,
                       updated_at=func.now()).returning(Participant.id)
    updated = db.session.scalar(stmt)
    if updated is None:
        raise nothing_on_stage(expected_id)
    return record_change("complete", get_participant(updated), operator_id)


def complete(operator_id, data):
    expected_id = participant_id_from_body(data) if "participant_id" in data else None
    lock_stage()
    event = finish_current(operator_id, expected_id)
    commit_changes(event)
    return {"completed": event["participant"]}


def call_next(operator_id, data):
    auto_complete = data.get("complete_current", False)
    if not isinstance(auto_complete, bool):
        raise invalid_fields(complete_current="expected_boolean")
    lock_stage()
    current = current_on_stage()
    events = []
    completed = None
    if current:
        if not auto_complete:
            raise ApiError("STAGE_BUSY", 409, {"current": current})
        event = finish_current(operator_id, current["id"])
        completed = event["participant"]
        events.append(event)

    next_id = db.session.scalar(
        select(Participant.id).where(Participant.status == "queued")
        .order_by(Participant.queued_at, Participant.id).limit(1).with_for_update(skip_locked=True)
    )
    if next_id is None:
        raise ApiError("QUEUE_EMPTY", 409, {"queue_length": 0, "current": current})
    stmt = (
        update(Participant).where(Participant.id == next_id, Participant.status == "queued")
        .values(status="on_stage", called_at=func.now(), called_by=operator_id, updated_at=func.now())
        .returning(Participant.id)
    )
    updated = db.session.scalar(stmt)
    event = record_change("call", get_participant(updated), operator_id)
    commit_changes(*events, event)
    return {"current": event["participant"], "completed": completed}
