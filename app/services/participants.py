import re
import secrets

from sqlalchemy import func, or_, select, update

from ..errors import ApiError, invalid_fields, is_db_text
from ..extensions import db
from ..models import Participant, serialize_participant
from . import commit_changes, record_change

PROFILE_FIELDS = {"participant_code", "name", "email"}
STATUSES = {"registered", "checked_in", "queued", "on_stage", "completed"}
CODE = re.compile(r"[A-Za-z0-9_-]{1,32}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{16,64}")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def new_token():
    return secrets.token_urlsafe(24)


def profile_values(data, partial):
    errors = {key: "unexpected" for key in data.keys() - PROFILE_FIELDS}
    values = {}
    for field in sorted(PROFILE_FIELDS):
        if partial and field not in data:
            continue
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[field] = "required"
            continue
        if not is_db_text(value):
            errors[field] = "invalid"
            continue
        value = value.strip()
        if field == "participant_code":
            if not CODE.fullmatch(value):
                errors[field] = "invalid"
            value = value.upper()
        elif field == "name" and len(value) > 128:
            errors[field] = "too_long"
        elif field == "email":
            value = value.lower()
            if len(value) > 255 or not EMAIL.fullmatch(value):
                errors[field] = "invalid"
        values[field] = value
    if errors:
        raise invalid_fields(**errors)
    if not values:
        raise invalid_fields(body="required")
    return values


def check_uniqueness(values, exclude_id=None):
    conditions = []
    if "participant_code" in values:
        conditions.append(Participant.participant_code == values["participant_code"])
    if "email" in values:
        conditions.append(func.lower(Participant.email) == values["email"])
    if not conditions:
        return
    stmt = select(Participant.participant_code, Participant.email).where(or_(*conditions))
    if exclude_id is not None:
        stmt = stmt.where(Participant.id != exclude_id)
    for code, email in db.session.execute(stmt):
        if code == values.get("participant_code"):
            raise ApiError("DUPLICATE_CODE", 409, {"participant_code": code})
        raise ApiError("DUPLICATE_EMAIL", 409, {"email": email})


def get_participant(participant_id, *, for_update=False):
    if participant_id > 2**63 - 1:
        raise ApiError("NOT_FOUND", 404, {"participant_id": participant_id})
    stmt = select(Participant).where(Participant.id == participant_id)
    if for_update:
        stmt = stmt.with_for_update(of=Participant)
    p = db.session.scalar(stmt.execution_options(populate_existing=True))
    if p is None:
        raise ApiError("NOT_FOUND", 404, {"participant_id": participant_id})
    return p


def save_profile(p, action, operator_id, changed_fields):
    db.session.flush()
    event = record_change(action, p, operator_id, {"changed_fields": sorted(changed_fields)})
    result = serialize_participant(p, include_token=True)
    commit_changes(event)
    return result


def create_participant(data, operator_id):
    values = profile_values(data, partial=False)
    check_uniqueness(values)
    p = Participant(**values, qr_token=new_token())
    db.session.add(p)
    return save_profile(p, "create", operator_id, values.keys())


def update_participant(participant_id, data, operator_id):
    values = profile_values(data, partial=True)
    p = get_participant(participant_id, for_update=True)
    check_uniqueness(values, exclude_id=p.id)
    changed = [field for field, value in values.items() if getattr(p, field) != value]
    for field in changed:
        setattr(p, field, values[field])
    if changed:
        p.updated_at = func.now()
    return save_profile(p, "update", operator_id, changed)


def regenerate_qr(participant_id, operator_id):
    p = get_participant(participant_id, for_update=True)
    p.qr_token = new_token()
    p.updated_at = func.now()
    return save_profile(p, "regenerate_qr", operator_id, ["qr_token"])


def positive_integer(args, name, default, maximum=None):
    raw = args.get(name, str(default))
    if not re.fullmatch(r"[0-9]+", raw):
        raise invalid_fields(**{name: "invalid_integer"})
    try:
        value = int(raw)
    except ValueError:
        raise invalid_fields(**{name: "invalid_integer"}) from None
    if value < 1 or (maximum is not None and value > maximum):
        raise invalid_fields(**{name: "out_of_range"})
    return value


def search_condition(term):
    if not is_db_text(term):
        raise invalid_fields(q="invalid")
    # ILIKE with escaped wildcards keeps codes containing underscores literal.
    pattern = "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
    return or_(*(column.ilike(pattern, escape="!") for column in
                 (Participant.name, Participant.email, Participant.participant_code)))


def checkin_search(term):
    term = term.strip()
    if not term:
        raise invalid_fields(q="required")
    stmt = select(Participant).where(search_condition(term)).order_by(
        (Participant.participant_code == term.upper()).desc(), Participant.name, Participant.id
    ).limit(20)
    return [serialize_participant(p) for p in db.session.scalars(stmt)]


def participant_filters(args):
    conditions = []
    if args.get("status"):
        if args["status"] not in STATUSES:
            raise invalid_fields(status="invalid")
        conditions.append(Participant.status == args["status"])
    term = args.get("q", "").strip()
    if term:
        conditions.append(search_condition(term))
    return conditions


def qr_sheet_participants(args):
    stmt = select(Participant.id, Participant.name, Participant.participant_code).where(*participant_filters(args))
    return db.session.execute(stmt.order_by(Participant.id)).all()


def list_participants(args):
    page = positive_integer(args, "page", 1)
    per_page = positive_integer(args, "per_page", 20, maximum=100)
    conditions = participant_filters(args)
    total = db.session.scalar(select(func.count()).select_from(Participant).where(*conditions))
    offset = (page - 1) * per_page
    items = []
    if offset < total:
        stmt = select(Participant).where(*conditions).order_by(Participant.id).offset(offset).limit(per_page)
        items = [serialize_participant(p, include_token=True) for p in db.session.scalars(stmt)]
    return {"items": items, "total": total, "page": page, "per_page": per_page}


def lookup_condition(data):
    if ("token" in data) == ("code" in data):
        raise invalid_fields(token="provide_exactly_one_of_token_or_code")
    if "token" in data:
        raw = data["token"]
        token = raw.strip().removeprefix("GRAD:").strip() if isinstance(raw, str) else ""
        if not TOKEN.fullmatch(token):
            raise ApiError("INVALID_QR", 404, {"reason": "invalid_format"})
        return Participant.qr_token == token
    code = data["code"]
    if not is_db_text(code) or not code.strip():
        raise invalid_fields(code="invalid")
    return Participant.participant_code == code.strip().upper()


def lookup(data, *, for_update=False):
    stmt = select(Participant).where(lookup_condition(data)).execution_options(populate_existing=True)
    if for_update:
        stmt = stmt.with_for_update(of=Participant)
    p = db.session.scalar(stmt)
    if p is None:
        if "token" in data:
            raise ApiError("INVALID_QR", 404, {"reason": "unknown_token"})
        raise ApiError("PARTICIPANT_NOT_FOUND", 404, {"code": data["code"].strip().upper()})
    return p


def transition_by_identifier(data, from_status, **values):
    stmt = (
        update(Participant).where(lookup_condition(data), Participant.status == from_status)
        .values(**values, updated_at=func.now()).returning(Participant.id)
    )
    participant_id = db.session.scalar(stmt)
    if participant_id is None:
        # A create or check-in can make this row eligible between the UPDATE and
        # the diagnostic read. Hold the row while deciding whether to retry.
        p = lookup(data, for_update=True)
        if p.status != from_status:
            return p, False
        participant_id = db.session.scalars(stmt).one()
    return get_participant(participant_id), True
