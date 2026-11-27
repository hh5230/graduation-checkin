from sqlalchemy import func

from ..errors import ApiError, invalid_fields, is_db_text
from ..models import serialize_participant
from . import commit_changes, record_change
from .participants import transition_by_identifier


def check_in(data, operator_id):
    entrance = data.get("entrance", "")
    if not is_db_text(entrance):
        raise invalid_fields(entrance="invalid")
    entrance = entrance.strip()
    if len(entrance) > 64:
        raise invalid_fields(entrance="too_long")
    participant, changed = transition_by_identifier(
        data, "registered", status="checked_in", checked_in_at=func.now(), checked_in_by=operator_id,
        checked_in_entrance=entrance or None,
    )
    if not changed:
        p = serialize_participant(participant)
        raise ApiError("ALREADY_CHECKED_IN", 409, {
            "checked_in_at": p["checked_in_at"], "checked_in_by": p["checked_in_by"],
            "checked_in_entrance": p["checked_in_entrance"], "participant": p,
        })
    event = record_change("check_in", participant, operator_id)
    commit_changes(event)
    return event["participant"]
